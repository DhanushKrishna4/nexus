"""
Head-to-head model comparison (Phase 1: qwen3.5:35b vs qwen2.5:72b).

Runs the same questions through both models via Ollama and produces a side-by-side
report: objective scores (hallucination-refusal, keyword coverage) + speed
(tokens/sec, latency), plus both full answers so you can judge quality yourself.

Run on the server (or with the Ollama port tunnelled):
    python3 compare_models.py
    python3 compare_models.py --a qwen3.5:35b --b qwen2.5:72b
    python3 compare_models.py --cases my_questions.json --out report.md

Your own questions (recommended) — a JSON list like:
    [{"q": "...", "keywords": ["x","y"]},        # graded on keyword coverage
     {"q": "...", "refusal": true},               # should decline (no such doc)
     {"q": "..."}]                                # open-ended, judged by you
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

import httpx

# Generic OT/cybersec set — replace with your real questions via --cases.
DEFAULT_CASES = [
    {"q": "In one sentence, what is the purpose of IEC 62443 zones and conduits?",
     "keywords": ["segment", "zone"]},
    {"q": "Our internal 'Site-Z 2019' penetration test — what did it conclude? "
          "If you don't have that document, say so.",
     "refusal": True},
    {"q": "Draft a one-paragraph executive summary for an OT security gap "
          "assessment of a water-treatment SCADA system."},
    {"q": "A pressure transmitter PT-101 fails low. Reason through the likely "
          "control-system consequence."},
    {"q": "List five NIST SP 800-82 recommended controls for remote access to "
          "an industrial control system."},
]
_REFUSAL = ["don't have", "do not have", "no information", "not available",
            "cannot", "couldn't", "no record", "unable", "don't know", "no access"]
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(t: str) -> str:
    return _THINK.sub("", t or "").strip()


def ask(ollama: str, model: str, q: str) -> dict:
    t0 = time.time()
    r = httpx.post(f"{ollama}/api/chat", timeout=900, json={
        "model": model, "messages": [{"role": "user", "content": q}],
        "stream": False, "keep_alive": -1})
    d = r.json()
    ans = _strip_think(d.get("message", {}).get("content", ""))
    tok = d.get("eval_count", 0) or 0
    dur = (d.get("eval_duration", 0) or 0) / 1e9
    return {"answer": ans, "wall": time.time() - t0,
            "tok_s": (tok / dur) if dur else 0.0, "tokens": tok}


def grade(ans: str, case: dict) -> str:
    a = ans.lower()
    if case.get("refusal"):
        return "✓ refused" if any(s in a for s in _REFUSAL) else "✗ HALLUCINATED"
    kw = case.get("keywords")
    if kw:
        hits = [k for k in kw if k.lower() in a]
        return f"{len(hits)}/{len(kw)} keywords"
    return "(judge quality)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="qwen3.5:35b")
    ap.add_argument("--b", default="qwen2.5:72b")
    ap.add_argument("--cases", default=None)
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--out", default="model_comparison.md")
    args = ap.parse_args()

    cases = (json.load(open(args.cases)) if args.cases else DEFAULT_CASES)
    lines = [f"# Model comparison: `{args.a}`  vs  `{args.b}`\n"]
    a_speed, b_speed = [], []

    for i, c in enumerate(cases, 1):
        q = c["q"]
        print(f"[{i}/{len(cases)}] {q[:60]}…")
        ra, rb = ask(args.ollama, args.a, q), ask(args.ollama, args.b, q)
        a_speed.append(ra["tok_s"])
        b_speed.append(rb["tok_s"])
        lines += [
            f"\n## {i}. {q}",
            f"\n**{args.a}** — {grade(ra['answer'], c)} · "
            f"{ra['tok_s']:.0f} tok/s · {ra['wall']:.1f}s\n",
            f"> {ra['answer'][:1500]}\n",
            f"\n**{args.b}** — {grade(rb['answer'], c)} · "
            f"{rb['tok_s']:.0f} tok/s · {rb['wall']:.1f}s\n",
            f"> {rb['answer'][:1500]}\n",
            "\n---",
        ]

    def avg(x):
        return sum(x) / len(x) if x else 0
    summary = (f"\n## Speed summary\n"
               f"- `{args.a}`: {avg(a_speed):.0f} tok/s avg\n"
               f"- `{args.b}`: {avg(b_speed):.0f} tok/s avg\n"
               f"- `{args.a}` is ~{avg(a_speed)/max(avg(b_speed),1):.1f}× the speed\n")
    lines.append(summary)

    report = "\n".join(lines)
    open(args.out, "w").write(report)
    print(summary)
    print(f"\nFull side-by-side written to: {args.out}")
    print("→ Read it and judge the open-ended answers yourself (quality is "
          "your call).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
