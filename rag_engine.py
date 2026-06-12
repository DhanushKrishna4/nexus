"""
Core RAG logic for the Nexus instrument-failure assistant.

Two responsibilities, both UI-agnostic so they can be driven from Streamlit,
a CLI, or tests:

    1. read_tags_from_image()  -> ask the vision model to OCR instrument tags
    2. lookup_failure_state()  -> retrieve the matching failure manual from Chroma

Design note
-----------
The Mac/client side talks to ChromaDB over its plain REST API via `httpx`
rather than importing the heavy `chromadb` package. On this machine the
`chromadb` client import hangs (native deps under Python 3.13) and, worse, it
would try to download a local embedding model just to read a record. Since our
primary lookup is an exact metadata match on the instrument tag — pure
filtering, no embeddings — a thin HTTP client is both more reliable and the
right architecture for a remote, tunnelled database.

Seeding the database (which *does* need embeddings) stays in build_database.py
and is meant to run server-side on RunPod.
"""
from __future__ import annotations

import re
from functools import lru_cache

import httpx
import ollama

import config

_CHROMA_V2 = (
    f"http://{config.CHROMA_HOST}:{config.CHROMA_PORT}"
    "/api/v2/tenants/default_tenant/databases/default_database"
)
_TIMEOUT = httpx.Timeout(15.0)


# --------------------------------------------------------------------------- #
# Clients
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _ollama_client() -> ollama.Client:
    return ollama.Client(host=config.OLLAMA_HOST)


@lru_cache(maxsize=1)
def _collection_id() -> str:
    """Resolve the collection's UUID from its human-readable name (cached)."""
    resp = httpx.get(f"{_CHROMA_V2}/collections", timeout=_TIMEOUT)
    resp.raise_for_status()
    for col in resp.json():
        if col["name"] == config.COLLECTION_NAME:
            return col["id"]
    raise RuntimeError(
        f"Collection '{config.COLLECTION_NAME}' not found on the ChromaDB server."
    )


def chroma_doc_count() -> int:
    """Used by the UI's connection test."""
    resp = httpx.get(
        f"{_CHROMA_V2}/collections/{_collection_id()}/count", timeout=_TIMEOUT
    )
    resp.raise_for_status()
    return int(resp.json())


# --------------------------------------------------------------------------- #
# Vision: image -> instrument tags
# --------------------------------------------------------------------------- #
def read_tags_from_image(image: str | bytes) -> tuple[str, list[str]]:
    """
    Run the vision model on an image and pull out instrument tags.

    `image` may be a file path (str) or raw image bytes.
    Returns (raw_model_text, ordered_unique_tags).
    """
    response = _ollama_client().chat(
        model=config.VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": config.VISION_PROMPT,
                "images": [image],
            }
        ],
        keep_alive=config.KEEP_ALIVE,
    )
    raw_text = response["message"]["content"]

    found = re.findall(config.TAG_PATTERN, raw_text.upper())

    # De-duplicate while preserving first-seen order.
    seen: set[str] = set()
    tags = [t for t in found if not (t in seen or seen.add(t))]
    return raw_text, tags


# --------------------------------------------------------------------------- #
# Retrieval: tag -> failure-state manual
# --------------------------------------------------------------------------- #
def _get_where(where: dict) -> tuple[list[str], list[dict]]:
    """Return (documents, metadatas) for an exact metadata filter."""
    resp = httpx.post(
        f"{_CHROMA_V2}/collections/{_collection_id()}/get",
        json={"where": where, "include": ["documents", "metadatas"]},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return (data.get("documents") or [], data.get("metadatas") or [])


# Characters the OCR step commonly confuses, by position type. We ONLY correct
# within a position (a letter slot stays a letter, a digit slot stays a digit),
# so we never turn one valid instrument tag into a *different* valid tag.
# e.g. the digit-slot 'O' -> '0' fixes 'PT-1O1' -> 'PT-101', but 'T-101' is
# never rewritten to 'PT-101' because that changes the letter prefix.
_DIGIT_FIX = str.maketrans({"O": "0", "Q": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})
# Loose match: the numeric block may contain OCR letter-confusions (e.g. 'O'
# for '0'); the function-code prefix and the trailing suffix letter are kept
# as-is so a correction never turns one valid tag into a different one.
_TAG_RE = re.compile(r"^([A-Z]{1,4})-([A-Z0-9]{3,4})([A-Z]?)$")


def _ocr_normalize(tag: str) -> str:
    """
    Fix OCR digit/letter confusion *within the numeric block only*.

    The letter prefix and suffix are left untouched, so a correction can never
    turn one valid tag into a different one (e.g. 'T-101' stays 'T-101'; only
    digit-slot glyphs like 'PT-1O1' become 'PT-101').
    """
    m = _TAG_RE.match(tag.upper())
    if not m:
        return tag.upper()
    prefix, mid, suffix = m.groups()
    return f"{prefix}-{mid.translate(_DIGIT_FIX)}{suffix}"


def format_citation(source: str | None, loc: str | None) -> str:
    """Human-readable citation, e.g. 'SiteB_FMEA.pdf · p.12' or just the file."""
    source = source or "—"
    return f"{source} · {loc}" if loc else source


def lookup_failure_state(tag: str) -> dict | None:
    """
    Retrieve the failure-state manual for a single instrument tag (exact match).

    An instrument tag is a precise identifier, so a miss returns None rather
    than guess. We retry once with OCR-confusion correction applied to the
    *digits* (e.g. 'PT-1O1' -> 'PT-101'), which never rewrites a tag into a
    different valid one (a tank 'T-101' is never matched to transmitter
    'PT-101').

    Returns {"manual", "matched_tag", "source"} or None.
    """
    for candidate, kind in ((tag, "exact"), (_ocr_normalize(tag), "ocr-corrected")):
        if kind == "ocr-corrected" and candidate == tag:
            continue
        docs, metas = _get_where({"tag": candidate})
        if docs:
            meta = metas[0] if metas else {}
            return {
                "manual": docs[0],
                "matched_tag": candidate,
                "source": meta.get("source", "—"),
                "loc": meta.get("loc", ""),
                "match": kind,
            }
    return None


# --------------------------------------------------------------------------- #
# Semantic search (closest-meaning fallback when there's no exact tag match)
# --------------------------------------------------------------------------- #
def semantic_suggestions(query: str, n: int = 3) -> list[dict]:
    """
    Closest-meaning passages for a free-text query (or an unmatched tag).

    We embed the query with the same model used to index the documents
    (config.EMBED_MODEL via Ollama) and query ChromaDB over REST. Results are
    clearly NOT exact matches — returned as ranked suggestions with a distance
    score so the UI can present them as "related", never as the authoritative
    manual. Returns [] if anything is unavailable (degrades gracefully).
    """
    import embeddings  # local import keeps module load light
    try:
        qvec = embeddings.embed_one(query)
    except Exception:  # noqa: BLE001
        return []
    try:
        resp = httpx.post(
            f"{_CHROMA_V2}/collections/{_collection_id()}/query",
            json={"query_embeddings": [qvec], "n_results": n,
                  "include": ["documents", "metadatas", "distances"]},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        res = resp.json()
    except Exception:  # noqa: BLE001
        return []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    out = []
    for doc, meta, dist in zip(docs, metas, dists):
        out.append({
            "manual": doc,
            "tag": (meta or {}).get("tag", "—"),
            "source": (meta or {}).get("source", "—"),
            "loc": (meta or {}).get("loc", ""),
            "distance": round(float(dist), 3),
        })
    return out


def analyze_image(image: str | bytes) -> dict:
    """
    Full pipeline: OCR an image, then look up every tag found.

    For each tag we do an exact lookup; when that misses, we attach semantic
    suggestions (clearly labelled, never substituted for an exact answer).

    Returns:
        {
          "raw_text": str,
          "tags": [str, ...],
          "results": [
            {"tag": str,
             "manual": str | None,        # exact match text, or None
             "source": str | None,
             "match": str | None,         # "exact" | "ocr-corrected"
             "suggestions": [ {...}, ... ] # only when manual is None
            }, ...
          ],
        }
    """
    raw_text, tags = read_tags_from_image(image)
    results = []
    for tag in tags:
        hit = lookup_failure_state(tag)
        if hit:
            results.append({
                "tag": tag, "manual": hit["manual"],
                "source": hit["source"], "loc": hit.get("loc", ""),
                "match": hit["match"], "suggestions": [],
            })
        else:
            results.append({
                "tag": tag, "manual": None, "source": None, "loc": "",
                "match": None, "suggestions": semantic_suggestions(tag, n=3),
            })
    return {"raw_text": raw_text, "tags": tags, "results": results}
