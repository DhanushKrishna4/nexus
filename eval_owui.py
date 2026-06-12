"""
Evaluation harness for the Open WebUI / Ollama stack.

Two layers:
  1. Routing & intent  — checks the Auto router sends each prompt to the right
     model and detects export requests. Pure logic, runs anywhere (offline).
  2. Live answers      — sends prompts to the models via Ollama and grades the
     replies (keyword coverage + hallucination-refusal). Needs the server.

Usage (on the server, or with the Ollama port tunnelled):
    python3 eval_owui.py            # routing checks + live answer checks
    python3 eval_owui.py --routing-only
    python3 eval_owui.py --ollama http://localhost:11434
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

import openwebui_autorouter_function as R

# --- Routing test cases: prompt -> expected lane ---------------------------
_ROUTING = {
    "whats the capital of france": "fast",
    "write a python function to parse csv": "code",
    "analyze the risk if PT-101 fails": "reason",
    "compare IEC 62443 zones vs NIST": "reason",
    "convert this to an excel file": "export:excel",
    "make this a word document": "export:word",
    "export the report as powerpoint": "export:pptx",
    "what is excel": "fast",
}

# --- Live answer test cases ------------------------------------------------
_ANSWERS = [
    {"q": "In one sentence, what is the purpose of IEC 62443 zones?",
     "model": "qwen2.5:72b", "keywords": ["segment", "zone"]},
    {"q": "What does our Site-Z 2019 pentest report conclude? "
          "If you don't have it, say so.",
     "model": "qwen2.5:72b", "refusal": True},
]
_REFUSAL = ["don't have", "do not have", "no information", "not available",
            "cannot", "couldn't", "no record", "unable", "don't know"]


def _lane(prompt: str) -> str:
    fmt = R._export_format(prompt)
    if fmt:
        return f"export:{fmt}"
    if R._is_coding(prompt):
        return "code"
    if R._needs_reasoning(prompt):
        return "reason"
    return "fast"


def run_routing() -> bool:
    print("== Routing & intent ==")
    ok = True
    for prompt, exp in _ROUTING.items():
        got = _lane(prompt)
        good = got == exp
        ok &= good
        print(f"  [{'OK ' if good else 'XX '}] {got:13} {prompt}")
    return ok


def run_live(ollama: str) -> bool:
    print("\n== Live answers ==")
    ok = True
    for c in _ANSWERS:
        try:
            r = httpx.post(f"{ollama}/api/chat", timeout=300, json={
                "model": c["model"],
                "messages": [{"role": "user", "content": c["q"]}],
                "stream": False, "keep_alive": -1})
            ans = r.json().get("message", {}).get("content", "")
        except Exception as e:  # noqa: BLE001
            print(f"  [XX ] {c['q'][:40]} -> error: {e}")
            ok = False
            continue
        a = ans.lower()
        if c.get("refusal"):
            good = any(s in a for s in _REFUSAL)
            label = "refused" if good else "HALLUCINATED"
        else:
            hits = [k for k in c["keywords"] if k.lower() in a]
            good = len(hits) == len(c["keywords"])
            label = f"{len(hits)}/{len(c['keywords'])} keywords"
        ok &= good
        print(f"  [{'OK ' if good else 'XX '}] {label:14} {c['q'][:45]}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--routing-only", action="store_true")
    ap.add_argument("--ollama", default="http://localhost:11434")
    args = ap.parse_args()

    ok = run_routing()
    if not args.routing_only:
        ok &= run_live(args.ollama)
    print("\n" + ("✅ ALL PASS" if ok else "❌ SOME FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
