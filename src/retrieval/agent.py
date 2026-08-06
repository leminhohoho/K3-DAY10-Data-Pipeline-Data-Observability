from __future__ import annotations

import re
import time
from typing import Any

from langchain.agents import create_agent
from langchain.tools import tool

from core.config import Settings
from retrieval.index import LocalEmbeddingIndex
from retrieval.llm import build_llm


# Free-tier LLM endpoints throttle aggressively; agent questions retry the
# transient statuses instead of losing the answer to one 429.
_AGENT_RETRY_ATTEMPTS = 3
_AGENT_RETRY_BACKOFF_SECONDS = 15.0
_AGENT_RETRY_MAX_DELAY_SECONDS = 60.0
_RETRYABLE_ERROR_MARKERS = (
    "429",
    "RESOURCE_EXHAUSTED",
    "500",
    "INTERNAL",
    "503",
    "UNAVAILABLE",
    "504",
    "DEADLINE_EXCEEDED",
)


def build_agent(settings: Settings, index: LocalEmbeddingIndex):
    @tool
    def semantic_search_papers(query: str, top_k: int = 4) -> str:
        """Search the local paper corpus with embeddings and return the most relevant papers."""
        results = index.search(query, top_k=top_k)
        lines = []
        for result in results:
            lines.append(
                f"paper_id: {result.paper_id}\n"
                f"title: {result.title}\n"
                f"score: {result.score:.4f}\n"
                f"{result.content}"
            )
        return "\n\n".join(lines)

    @tool
    def lookup_paper(paper_id_or_title: str) -> str:
        """Look up a paper by exact paper_id or exact title from the local corpus."""
        record = index.lookup(paper_id_or_title)
        if not record:
            return "No exact paper match found."
        return (
            f"paper_id: {record['paper_id']}\n"
            f"title: {record['title']}\n"
            f"{record['content']}"
        )

    llm = build_llm(settings=settings, temperature=0.0)
    return create_agent(
        model=llm,
        tools=[semantic_search_papers, lookup_paper],
        system_prompt=(
            "You answer questions about the indexed scholarly paper corpus sourced from Crossref. "
            "Use tools before answering factual questions. "
            "If the indexed corpus does not support the answer, say so clearly."
        ),
        name="paper_corpus_agent",
    )


def run_agent_question(agent: Any, question: str) -> str:
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    messages = result.get("messages", [])
    if not messages:
        return ""
    final_message = messages[-1]
    return getattr(final_message, "content", str(final_message))


def normalize_agent_text(value: Any) -> str:
    """Flatten a LangChain message payload, which may be text or content blocks."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for block in value:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(part for part in parts if part).strip()
    return str(value).strip()


def _retry_delay_seconds(error: Exception, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None when the failure is permanent."""
    message = str(error)
    if not any(marker in message for marker in _RETRYABLE_ERROR_MARKERS):
        return None
    hinted = re.search(r"'retryDelay': '(\d+(?:\.\d+)?)s'", message)
    delay = float(hinted.group(1)) + 1.0 if hinted else _AGENT_RETRY_BACKOFF_SECONDS * attempt
    return min(delay, _AGENT_RETRY_MAX_DELAY_SECONDS)


def answer_with_agent(agent: Any, question: str) -> tuple[str | None, str | None]:
    """Return (answer, error) for one agent question, retrying transient failures.

    A returned error string means every retry was exhausted (typically a hard
    quota limit); callers can then fall back to a deterministic answer instead
    of failing the whole run.
    """
    last_error: Exception | None = None
    for attempt in range(1, _AGENT_RETRY_ATTEMPTS + 1):
        try:
            return normalize_agent_text(run_agent_question(agent, question)), None
        except Exception as error:
            last_error = error
            delay = _retry_delay_seconds(error, attempt)
            if delay is None or attempt == _AGENT_RETRY_ATTEMPTS:
                break
            time.sleep(delay)
    return None, f"{type(last_error).__name__}: {last_error}"
