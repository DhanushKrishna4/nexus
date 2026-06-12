#!/bin/bash
# ===========================================================================
# Nexus server setup / disaster recovery.
#
# Run this ON A RUNPOD POD to build the whole stack from scratch onto the
# persistent /workspace volume. Safe to re-run; it skips what already exists.
#
#   bash server_setup.sh
#
# After it finishes, start everything with:  bash /workspace/start.sh
# ===========================================================================
set -e
export OLLAMA_MODELS=/workspace/ollama_models

echo "== 1. System packages =="
apt-get update -qq
apt-get install -y -qq zstd tmux

echo "== 2. Ollama =="
# NOTE: the official install script (ollama.com/install.sh) intermittently 404s
# on some pods, so we install the release tarball directly.
if ! command -v ollama >/dev/null 2>&1; then
  curl -L "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst" \
       -o /tmp/ollama.tar.zst
  tar -C /usr/local --use-compress-program=unzstd -xf /tmp/ollama.tar.zst
  rm -f /tmp/ollama.tar.zst
fi
ollama --version

echo "== 3. Python deps =="
pip install -q --ignore-installed blinker \
  streamlit ollama chromadb "uvicorn[standard]" httpx pillow \
  pymupdf python-docx openpyxl

echo "== 4. Directories on the persistent volume =="
mkdir -p /workspace/ollama_models /workspace/chroma_db \
         /workspace/nexus /workspace/input_docs

echo "== 5. Start Ollama (needed to pull models) =="
tmux kill-session -t ollama 2>/dev/null || true
tmux new-session -d -s ollama \
  "OLLAMA_MODELS=/workspace/ollama_models ollama serve 2>&1 | tee /workspace/ollama.log"
sleep 5

echo "== 6. Pull models (one-time) =="
ollama pull qwen2.5vl:7b     # vision  (blueprint OCR)
ollama pull qwen2.5:72b      # chat    (general assistant, ~47GB)
ollama pull qwq:32b          # reasoning (deep-analysis mode, ~20GB)
ollama pull bge-m3           # embeddings (semantic search quality, ~1GB)

echo "== 7. Seed the demo database (skip if you'll ingest real manuals) =="
tmux kill-session -t chroma 2>/dev/null || true
tmux new-session -d -s chroma \
  "chroma run --host 0.0.0.0 --port 8000 --path /workspace/chroma_db 2>&1 | tee /workspace/chroma.log"
sleep 5
if [ -f /workspace/nexus/build_database.py ]; then
  (cd /workspace/nexus && python3 build_database.py) || true
fi

echo ""
echo "== Done. =="
echo "Make sure the app code is in /workspace/nexus (scp it up if needed),"
echo "then run:  bash /workspace/start.sh"
