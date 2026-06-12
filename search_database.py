"""
Quick CLI sanity-check for the failure-state lookup, no vision model involved.

Usage:
    python search_database.py PT-101
    python search_database.py            # defaults to PT-101
"""
from __future__ import annotations

import sys

import rag_engine


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "PT-101"
    print(f"Searching private manuals for: {tag}…\n")

    hit = rag_engine.lookup_failure_state(tag)
    if hit is None:
        print(f"No exact manual found for '{tag}'.")
        suggestions = rag_engine.semantic_suggestions(tag, n=3)
        if suggestions:
            print("\nClosest related passages (semantic, not exact):")
            for s in suggestions:
                print(f"  • [{s['tag']}] (dist {s['distance']}) {s['manual'][:80]}…")
    else:
        print(f"--- Failure State ({hit['match']} match, source: {hit['source']}) ---")
        print(hit["manual"])


if __name__ == "__main__":
    main()
