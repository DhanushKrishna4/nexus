#!/bin/bash
# Shared service definitions for the Nexus stack. Sourced by BOTH boot.sh (the
# initial start) and supervise.sh (the auto-restart watchdog), so there is one
# definition of how each service starts and how to tell if it's healthy.
#
# Not meant to be run directly — `source services.sh`, then call the functions.

export OLLAMA_MODELS=/workspace/ollama_models

# --- Single source of truth for model names (models.env) -------------------
MODELS_ENV="${MODELS_ENV:-/workspace/nexus/models.env}"
[ -f "$MODELS_ENV" ] && { set -a; . "$MODELS_ENV"; set +a; }
: "${FAST_MODEL:=qwen3.5:35b}"
: "${REASONING_MODEL:=qwen3.5:122b}"
: "${CODE_MODEL:=qwen3.6:27b}"
: "${VISION_MODEL:=qwen3-vl:32b}"
: "${TABLE_MODEL:=qwen3-vl:32b}"
: "${EMBED_MODEL:=qwen3-embedding:4b}"
: "${TASK_MODEL:=qwen3.5:2b}"

# --- Start functions (each runs the service in its own tmux session) --------
start_ollama() {
  tmux kill-session -t ollama 2>/dev/null || true
  # OLLAMA_FLASH_ATTENTION: faster, lower-memory attention (quality-neutral).
  tmux new-session -d -s ollama \
    "OLLAMA_MODELS=/workspace/ollama_models OLLAMA_FLASH_ATTENTION=1 ollama serve 2>&1 | tee /workspace/ollama.log"
}

start_chroma() {
  tmux kill-session -t chroma 2>/dev/null || true
  tmux new-session -d -s chroma \
    "chroma run --host 0.0.0.0 --port 8000 --path /workspace/chroma_db 2>&1 | tee /workspace/chroma.log"
}

start_webui() {
  tmux kill-session -t webui 2>/dev/null || true
  # Privacy: no telemetry. Branding: WEBUI_NAME. RAG: full-context. Model-name
  # vars are exported so the router pipe's valves default to the same suite.
  tmux new-session -d -s webui "\
    DATA_DIR=/workspace/open-webui \
    OLLAMA_BASE_URL=http://localhost:11434 \
    WEBUI_AUTH=True \
    WEBUI_NAME='Nexus AI' \
    ANONYMIZED_TELEMETRY=False \
    SCARF_NO_ANALYTICS=true \
    DO_NOT_TRACK=true \
    RAG_EMBEDDING_ENGINE=ollama \
    RAG_EMBEDDING_MODEL=$EMBED_MODEL \
    RAG_OLLAMA_BASE_URL=http://localhost:11434 \
    RAG_FULL_CONTEXT=True \
    BYPASS_EMBEDDING_AND_RETRIEVAL=True \
    DEFAULT_MODELS=auto_smart_routing.auto-router \
    TASK_MODEL=$TASK_MODEL \
    FAST_MODEL=$FAST_MODEL \
    REASONING_MODEL=$REASONING_MODEL \
    CODE_MODEL=$CODE_MODEL \
    VISION_MODEL=$VISION_MODEL \
    TABLE_MODEL=$TABLE_MODEL \
    ENABLE_TAGS_GENERATION=False \
    ENABLE_AUTOCOMPLETE_GENERATION=False \
    ENABLE_FOLLOW_UP_GENERATION=False \
    open-webui serve --port 8080 2>&1 | tee /workspace/openwebui.log"
}

# --- Health checks (return 0 = healthy, non-zero = down) --------------------
health_ollama() { curl -sf -o /dev/null --max-time 5 http://localhost:11434/api/tags; }
# chroma: any HTTP response on the port = alive (endpoint path varies by version).
health_chroma() { curl -s  -o /dev/null --max-time 5 http://localhost:8000/api/v2/heartbeat \
               || curl -s  -o /dev/null --max-time 5 http://localhost:8000/api/v1/heartbeat; }
health_webui()  { [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://localhost:8080/health)" = "200" ]; }
