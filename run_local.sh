#!/bin/bash
# ===========================================================================
# Run the Nexus workbench on a LOCAL workstation (Linux/macOS).
# Everything runs on localhost — no RunPod, no SSH tunnel.
#
#   ./run_local.sh
#
# Then open http://localhost:8501 in a browser on this machine.
# Prerequisite: Ollama installed (https://ollama.com/download).
# ===========================================================================
set -e
cd "$(dirname "$0")"

CHROMA_DB_DIR="${CHROMA_DB_DIR:-./chroma_db}"

echo "[1/4] Ensuring Ollama is running…"
if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  ollama serve >/tmp/nexus-ollama.log 2>&1 &
  sleep 4
fi

echo "[2/4] Ensuring models are present (downloads once)…"
ollama pull qwen2.5vl:7b     # vision
ollama pull qwen2.5:72b      # chat
ollama pull qwq:32b          # reasoning ("Deep reasoning" mode)
ollama pull bge-m3           # embeddings (semantic search)

echo "[3/4] Ensuring ChromaDB is running…"
if ! curl -sf http://localhost:8000/api/v2/heartbeat >/dev/null 2>&1; then
  chroma run --host localhost --port 8000 --path "$CHROMA_DB_DIR" \
    >/tmp/nexus-chroma.log 2>&1 &
  sleep 4
fi

echo "[4/4] Starting the app on http://localhost:8501 …"
exec streamlit run app.py --server.port 8501
