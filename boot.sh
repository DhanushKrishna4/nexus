#!/bin/bash
# One-command boot for the Nexus stack after a RunPod restart.
# RunPod resets the container disk on stop/start, so this reinstalls the
# software layer (fast — no model re-download; models live on /workspace) and
# starts all services. Run:  bash /workspace/boot.sh
set -e

# Shared model env + service start/health functions (single source of truth).
NEXUS_DIR="${NEXUS_DIR:-/workspace/nexus}"
. "$NEXUS_DIR/services.sh"

echo "[1/6] System packages…"
# bubblewrap = optional strict sandbox for the code-interpreter export path.
command -v zstd tmux bwrap >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq zstd tmux bubblewrap; }

echo "[2/6] Ollama…"
if ! command -v ollama >/dev/null 2>&1; then
  curl -sL "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst" -o /tmp/o.tar.zst
  tar -C /usr/local --use-compress-program=unzstd -xf /tmp/o.tar.zst && rm -f /tmp/o.tar.zst
fi

echo "[3/6] Python deps…"
python3 -c "import open_webui" 2>/dev/null || pip install --ignore-installed blinker -q \
  chromadb ollama "uvicorn[standard]" httpx streamlit pymupdf python-docx openpyxl python-pptx pdfplumber matplotlib open-webui

echo "[4/6] Ollama + model suite…"
start_ollama
sleep 5
# Model suite (downloads once, then persists) — names from models.env.
for m in "$FAST_MODEL" "$REASONING_MODEL" "$CODE_MODEL" "$VISION_MODEL" \
         "$TABLE_MODEL" "$EMBED_MODEL" "$TASK_MODEL"; do
  echo "  pulling $m…"
  ollama pull "$m" 2>/dev/null || true
done

echo "[5/6] ChromaDB + Open WebUI…"
start_chroma
sleep 4
start_webui

echo "[warmup] Preloading the default chat model into VRAM…"
sleep 8
curl -s http://localhost:11434/api/generate -d "{\"model\":\"$FAST_MODEL\",\"prompt\":\"hi\",\"keep_alive\":-1,\"stream\":false}" >/dev/null 2>&1 || true
curl -s http://localhost:11434/api/generate -d "{\"model\":\"$TASK_MODEL\",\"prompt\":\"hi\",\"keep_alive\":-1,\"stream\":false}" >/dev/null 2>&1 || true

echo "[6/6] Supervisor (auto-restart watchdog)…"
tmux kill-session -t supervise 2>/dev/null || true
tmux new-session -d -s supervise "bash $NEXUS_DIR/supervise.sh"

echo ""
echo "Done. Open WebUI on :8080. Tunnel from your Mac (use the CURRENT ip/port):"
echo "  ssh -N -o ServerAliveInterval=30 -L 8080:localhost:8080 root@<IP> -p <PORT> -i ~/.ssh/id_ed25519"
