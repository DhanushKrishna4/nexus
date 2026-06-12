"""
Central configuration for the Nexus instrument-failure RAG app.

All connection details are read from environment variables so the same code
runs whether the heavy services (Ollama + ChromaDB) live on localhost via an
SSH tunnel to RunPod, or somewhere else entirely. Sensible defaults match the
RunPod SSH-tunnel setup (forwarded to localhost).
"""
from __future__ import annotations

import os

# --- Ollama (model names) --------------------------------------------------
# When tunnelled from RunPod:  ssh -N -L 11434:localhost:11434 ...
# Model names come from models.env (the single source of truth). When that file
# has been sourced into the environment, os.getenv picks it up; the literals
# below are the same values so this module also works standalone.
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
# Vision model reads small instrument tags off a P&ID (OCR) — the core
# Blueprint Analyzer use case.
VISION_MODEL: str = os.getenv("VISION_MODEL", "qwen3-vl:32b")

# --- Chat assistant (general-purpose, text) --------------------------------
# A strong generalist for the "Assistant" tab: drafting, Q&A, fast answers.
CHAT_MODEL: str = os.getenv("FAST_MODEL", "qwen3.5:35b")

# A reasoning model ("thinks" step-by-step before answering) for harder
# analytical work — gap assessments, risk analysis, reasoning over standards.
# Selectable as "Deep reasoning" mode, or chosen automatically in "Auto" mode.
REASONING_MODEL: str = os.getenv("REASONING_MODEL", "qwen3.5:122b")

# How long Ollama keeps a model resident in VRAM after use. Auto-routing relies
# on chat models staying hot so switching between them is instant (no reload).
# "-1" = keep loaded indefinitely; needs enough VRAM to hold every hot model at
# once (the full Qwen3.5/3.6 suite is ~145GB → H200-class). Lower it (e.g.
# "10m") on smaller GPUs where models must take turns.
# Ollama wants a number-of-seconds (int; -1 = forever) OR a unit string ("30m").
# Parse so a bare integer becomes int and "30m" stays a string.
_keep_alive_raw: str = os.getenv("OLLAMA_KEEP_ALIVE", "-1")
KEEP_ALIVE: "int | str" = (
    int(_keep_alive_raw) if _keep_alive_raw.lstrip("-").isdigit()
    else _keep_alive_raw
)

# --- Embeddings (semantic search quality) ----------------------------------
# The embedding model decides WHICH passages get retrieved — the ceiling on a
# RAG system's usefulness. qwen3-embedding is far stronger than ChromaDB's tiny
# default. NOTE: changing this requires re-indexing the database (the stored
# vectors must all come from the same model). See build_database.py / ingest.py.
EMBED_MODEL: str = os.getenv("EMBED_MODEL", "qwen3-embedding:4b")

CHAT_SYSTEM_PROMPT: str = os.getenv(
    "CHAT_SYSTEM_PROMPT",
    "You are a knowledgeable assistant for an OT (Operational Technology) "
    "cybersecurity consultancy. You help with security gap assessments, "
    "checklists, standards such as IEC 62443 and NIST SP 800-82, risk and "
    "threat analysis, industrial control systems (PLC/SCADA/DCS), and general "
    "professional and technical questions. Be precise, practical, and concise. "
    "When you are unsure or a question needs site-specific data you don't have, "
    "say so rather than guessing.",
)

# --- ChromaDB (vector store) ----------------------------------------------
# When tunnelled from RunPod:  ssh -N -L 8000:localhost:8000 ...
CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))
COLLECTION_NAME: str = os.getenv("COLLECTION_NAME", "instrument_failures")

# --- Access control (optional) ---------------------------------------------
# If APP_PASSWORD is set, the UI shows a password gate before anything loads.
# Leave it empty (default) for a frictionless local/dev experience; set it when
# the app is served on a shared office network so it isn't open to everyone.
#   e.g.  APP_PASSWORD=mysecret streamlit run app.py ...
APP_PASSWORD: str = os.getenv("APP_PASSWORD", "")

# --- Tag extraction --------------------------------------------------------
# Matches ISA-style instrument tags such as: T-101, V-104, P-102A, PT-101,
# LT-104, FT-105, TI-201, PSV-300, TIC-1050.
#   1-4 uppercase letters (function code), hyphen, 3-4 digit loop number,
#   optional trailing letter (A/B/... for redundant/parallel items).
TAG_PATTERN: str = r"\b[A-Z]{1,4}-\d{3,4}[A-Z]?\b"

VISION_PROMPT: str = (
    "Look closely at the text in this engineering diagram (P&ID). "
    "Extract and list every alphanumeric instrument tag you can read clearly, "
    "such as T-101, V-104, P-102A, PT-101, LT-104, FT-105, and the two-letter "
    "instrument codes inside the circles (PI, TI, LT, FT). "
    "Respond with just the tags, comma-separated. Do not describe the image."
)
