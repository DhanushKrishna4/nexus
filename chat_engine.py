"""
General-purpose chat assistant backed by the local Ollama model.

UI-agnostic: takes a conversation history and streams back the reply token by
token. Used by the "Assistant" tab in app.py, but equally callable from a CLI
or tests. Everything runs on the local (RunPod) model — no data leaves the box.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Iterator

import ollama

import config
import rag_engine


@lru_cache(maxsize=1)
def _client() -> ollama.Client:
    return ollama.Client(host=config.OLLAMA_HOST)


# --------------------------------------------------------------------------- #
# Model routing
# --------------------------------------------------------------------------- #
# Words/phrases that signal an analytical question better served by the
# reasoning model. Deliberately tuned toward this consultancy's work.
_REASONING_TRIGGERS = re.compile(
    r"\b("
    r"analy[sz]|assess|evaluat|compar|implication|risk|threat|root[\s-]?cause|"
    r"troubleshoot|diagnos|derive|calculat|prove|trade[\s-]?off|pros and cons|"
    r"step[\s-]?by[\s-]?step|reason|rationale|justif|design|architect|"
    r"recommend|gap|mitigat|consequence|why\b|how (?:would|could|should)"
    r")", re.IGNORECASE,
)


def needs_reasoning(query: str) -> bool:
    """Heuristic: does this question warrant the slower reasoning model?"""
    q = query.strip()
    if _REASONING_TRIGGERS.search(q):
        return True
    # Long or multi-part questions tend to need deliberation.
    return len(q) > 300 or q.count("?") >= 2


def choose_model(prompt: str, mode: str) -> str:
    """
    Resolve which chat model to use.

    mode is one of: "Auto", "General (fast)", "Deep reasoning".
    Auto routes per-question via needs_reasoning().
    """
    if mode == "Deep reasoning":
        return config.REASONING_MODEL
    if mode == "General (fast)":
        return config.CHAT_MODEL
    return config.REASONING_MODEL if needs_reasoning(prompt) else config.CHAT_MODEL


_RAG_GUIDANCE = (
    "Below are excerpts retrieved from the user's PRIVATE documents. "
    "If they are relevant to the question, base your answer on them and cite the "
    "source in square brackets exactly as given, including the page/location, "
    "e.g. [SiteB_FMEA.pdf · p.12]. If they are not relevant, ignore them and "
    "answer normally from your general knowledge. Do not invent document content "
    "that isn't in the excerpts."
)


_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"


def _strip_thinking(chunks: Iterator[str]) -> Iterator[str]:
    """
    Drop a leading <think>…</think> reasoning block from a token stream so
    reasoning models (e.g. QwQ) present the same way as the others: just the
    final answer. Auto-detects the tags, so it's a no-op for models that don't
    emit them. Tags may be split across chunks, so we buffer until we can decide.
    """
    buf = ""
    decided = False        # determined whether a <think> block is present?
    answering = False      # past any think block, now streaming the answer?
    answer_started = False  # emitted the first non-whitespace answer char yet?

    def emit(text: str):
        """Suppress leading whitespace until real answer content begins."""
        nonlocal answer_started
        if not answer_started:
            text = text.lstrip()
            if not text:
                return None
            answer_started = True
        return text

    for chunk in chunks:
        if answering:
            out = emit(chunk)
            if out:
                yield out
            continue
        buf += chunk
        if not decided:
            s = buf.lstrip()
            if s.startswith(_THINK_OPEN):
                decided = True          # thinking model; wait for the close tag
            elif len(s) >= len(_THINK_OPEN) or (s and not _THINK_OPEN.startswith(s)):
                decided = True           # no think block → stream normally
                answering = True
                out = emit(buf)
                buf = ""
                if out:
                    yield out
                continue
            else:
                continue                 # ambiguous (partial tag) → wait for more
        idx = buf.find(_THINK_CLOSE)
        if idx != -1:
            answering = True
            out = emit(buf[idx + len(_THINK_CLOSE):])
            buf = ""
            if out:
                yield out
    if not answering and buf.strip():
        out = emit(buf)                  # never closed / no think block → emit raw
        if out:
            yield out


def retrieve(query: str, k: int = 5) -> list[dict]:
    """Fetch the top-k relevant document passages for a query (or [] if none)."""
    return rag_engine.semantic_suggestions(query, n=k)


def rank_passages(query: str, passages: list[dict], k: int = 5) -> list[dict]:
    """
    Rank ad-hoc passages (e.g. from a file attached to the chat) by relevance to
    the query, returning the top-k. Each passage is a dict with at least
    'manual'; 'source'/'loc'/'tag' are passed through. Used for files attached
    directly to a conversation, so only the relevant parts enter the context.
    """
    import math
    import embeddings
    if not passages:
        return []
    texts = [p["manual"] for p in passages]
    try:
        vecs = embeddings.embed_texts([query] + texts)
    except Exception:  # noqa: BLE001
        return passages[:k]  # fall back to first-k if embedding unavailable
    qv, pvs = vecs[0], vecs[1:]

    def cos(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb + 1e-9)

    scored = sorted(zip(passages, pvs), key=lambda t: cos(qv, t[1]), reverse=True)
    out = []
    for p, pv in scored[:k]:
        out.append({**p, "distance": round(1.0 - cos(qv, pv), 3)})
    return out


def _context_message(passages: list[dict]) -> dict:
    block = "\n\n".join(
        f"[{i + 1}] (source: {rag_engine.format_citation(p['source'], p.get('loc'))}"
        f", tag: {p['tag']})\n{p['manual']}"
        for i, p in enumerate(passages)
    )
    return {"role": "system", "content": f"{_RAG_GUIDANCE}\n\n--- Excerpts ---\n{block}"}


def stream_reply(history: list[dict], model: str | None = None,
                 context: list[dict] | None = None) -> Iterator[str]:
    """
    Stream an assistant reply for a conversation.

    `history`  : list of {"role": "user"|"assistant", "content": str}.
    `model`    : overrides the default (e.g. the reasoning model for deep mode).
    `context`  : optional retrieved document passages to ground the answer in
                 (from retrieve()). When provided, the model is told to use them
                 if relevant and cite sources.
    Yields text chunks.
    """
    messages = [{"role": "system", "content": config.CHAT_SYSTEM_PROMPT}]
    if context:
        messages.append(_context_message(context))
    messages += history

    def _raw() -> Iterator[str]:
        for part in _client().chat(
            model=model or config.CHAT_MODEL, messages=messages, stream=True,
            keep_alive=config.KEEP_ALIVE,
        ):
            chunk = part.get("message", {}).get("content", "")
            if chunk:
                yield chunk

    # Strip reasoning models' <think>…</think> so all models present uniformly.
    yield from _strip_thinking(_raw())


def reply(history: list[dict], model: str | None = None,
          context: list[dict] | None = None) -> str:
    """Non-streaming convenience wrapper (for CLI / tests)."""
    return "".join(stream_reply(history, model=model, context=context))
