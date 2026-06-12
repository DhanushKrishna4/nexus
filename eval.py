"""
Evaluation harness for the Nexus workbench.

Measures whether the system actually works — before you trust it with client
work — and lets you catch regressions when you change a model, embedder, or
prompt. Three checks:

  1. Retrieval     — does semantic search surface the right source for a
                     question? (Fast, no chat model needed — ideal for comparing
                     embedders.)
  2. Answer        — does the generated answer contain the expected facts?
  3. Hallucination — for a question with NO relevant document, does the system
                     correctly decline instead of inventing an answer?

Runs against the live services, so do it on the server (or a CPU pod — the
embeddings model runs fine on CPU; only answer-eval needs the chat model and is
slow on CPU).

Usage
-----
    python eval.py                      # full eval (retrieval + answers)
    python eval.py --retrieval-only     # fast; great for embedder bake-off
    python eval.py --model qwq:32b      # eval a specific chat model
    python eval.py --cases mine.json    # your own test set

Embedder bake-off
-----------------
    EMBED_MODEL=bge-m3            python eval.py --retrieval-only
    EMBED_MODEL=mxbai-embed-large python eval.py --retrieval-only
    # (re-index the DB with each embedder first; compare the retrieval scores)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config

_REFUSAL_SIGNALS = [
    "don't have", "do not have", "no information", "not available",
    "cannot find", "couldn't find", "could not find", "no relevant",
    "not in the", "don't know", "do not know", "no record", "unable to",
    "isn't in", "is not in", "no mention",
]


# --------------------------------------------------------------------------- #
# Grading (pure functions — unit-testable without any server)
# --------------------------------------------------------------------------- #
def grade_keywords(answer: str, keywords: list[str]) -> tuple[float, list[str]]:
    """Return (coverage 0..1, list of missing keywords)."""
    a = (answer or "").lower()
    missing = [k for k in keywords if k.lower() not in a]
    coverage = 1.0 - (len(missing) / len(keywords)) if keywords else 1.0
    return coverage, missing


def grade_refusal(answer: str) -> bool:
    """True if the answer correctly signals it has no information."""
    a = (answer or "").lower()
    return any(s in a for s in _REFUSAL_SIGNALS)


def retrieval_hit(hits: list[dict], expect_tag: str | None,
                  expect_source: str | None) -> int | None:
    """Rank (1-based) of the first hit matching the expectation, or None."""
    for rank, h in enumerate(hits, 1):
        if expect_tag and h.get("tag") == expect_tag:
            return rank
        if expect_source and h.get("source") == expect_source:
            return rank
    return None


# --------------------------------------------------------------------------- #
# Runners
# --------------------------------------------------------------------------- #
def run(cases: list[dict], retrieval_only: bool, model: str | None,
        kw_threshold: float) -> bool:
    import chat_engine  # imported here so --help works without services

    n_ret = n_ret_ok = 0
    n_ans = n_ans_ok = 0
    rows = []

    for c in cases:
        q = c["question"]
        row = {"id": c["id"], "retrieval": "-", "answer": "-"}

        # 1) Retrieval check (when an expected source/tag is given and RAG used)
        hits = []
        if c.get("use_rag", True) and (c.get("expect_tag") or c.get("expect_source")):
            hits = chat_engine.retrieve(q, k=5)
            rank = retrieval_hit(hits, c.get("expect_tag"), c.get("expect_source"))
            n_ret += 1
            ok = rank is not None
            n_ret_ok += ok
            row["retrieval"] = f"✓ @{rank}" if ok else "✗ miss"
        elif c.get("use_rag", True):
            hits = chat_engine.retrieve(q, k=5)  # for grounding the answer

        # 2) Answer check (skipped in retrieval-only mode)
        if not retrieval_only:
            context = hits if c.get("use_rag", True) else []
            answer = chat_engine.reply([{"role": "user", "content": q}],
                                       model=model, context=context)
            if c.get("expect_refusal"):
                n_ans += 1
                ok = grade_refusal(answer)
                n_ans_ok += ok
                row["answer"] = "✓ refused" if ok else "✗ hallucinated"
            elif c.get("expect_keywords"):
                n_ans += 1
                cov, missing = grade_keywords(answer, c["expect_keywords"])
                ok = cov >= kw_threshold
                n_ans_ok += ok
                row["answer"] = (f"✓ {cov:.0%}" if ok
                                 else f"✗ {cov:.0%} miss={','.join(missing)}")
        rows.append(row)

    # ---- report ----
    print(f"\nEmbedder: {config.EMBED_MODEL}   Chat model: "
          f"{model or config.CHAT_MODEL}\n")
    print(f"{'case':<22}{'retrieval':<14}{'answer'}")
    print("-" * 60)
    for r in rows:
        print(f"{r['id']:<22}{r['retrieval']:<14}{r['answer']}")
    print("-" * 60)
    if n_ret:
        print(f"Retrieval: {n_ret_ok}/{n_ret} found the right source "
              f"({n_ret_ok / n_ret:.0%})")
    if n_ans:
        print(f"Answers  : {n_ans_ok}/{n_ans} passed ({n_ans_ok / n_ans:.0%})")

    passed = (n_ret_ok == n_ret) and (n_ans_ok == n_ans)
    print("\n" + ("✅ ALL PASS" if passed else "❌ SOME FAILED"))
    return passed


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate the Nexus workbench.")
    ap.add_argument("--cases", default="eval_cases.json",
                    help="Test-case JSON file.")
    ap.add_argument("--retrieval-only", action="store_true",
                    help="Only test retrieval (fast; no chat model).")
    ap.add_argument("--model", default=None,
                    help="Chat model to evaluate (default: config.CHAT_MODEL).")
    ap.add_argument("--kw-threshold", type=float, default=0.6,
                    help="Fraction of expected keywords required to pass.")
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text())
    ok = run(cases, args.retrieval_only, args.model, args.kw_threshold)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
