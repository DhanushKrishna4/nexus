# Fresh deploy on an H200 (122B suite) — checklist

A new pod has **empty storage**, so this is a from-scratch rebuild. The model
download (~130GB incl. the 122B) is the long part — make sure you have credit
(H200 ≈ $4.39/hr; budget at least a couple hours).

## 1. Deploy the pod (RunPod)
- GPU: **H200 SXM** (141GB)
- **Volume Disk: 170 GB** ← important; the 122B suite won't fit less
- Template: the standard PyTorch/Ubuntu one you've used
- Once running → copy the **SSH over exposed TCP** details (`root@<IP> -p <PORT>`)

## 2. Upload the project + run boot
From your Mac (Dhanush runs, or hand the IP/PORT to Claude):
```bash
scp -P <PORT> -i ~/.ssh/id_ed25519 \
  /Users/dhanush/Desktop/Nexus\ LLM/* root@<IP>:/workspace/nexus/
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 "cp /workspace/nexus/boot.sh /workspace/boot.sh && bash /workspace/boot.sh"
```
`boot.sh` installs the software, pulls the whole 122B suite (~130GB — slow part),
and starts Ollama + ChromaDB + Open WebUI.

## 3. Create your admin account
Tunnel + browser:
```bash
ssh -N -o ServerAliveInterval=30 -L 8080:localhost:8080 root@<IP> -p <PORT> -i ~/.ssh/id_ed25519
```
→ http://localhost:8080 → **sign up** (first account = admin).

## 4. Restore the functions (one command)
```bash
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 \
  "DATA_DIR=/workspace/open-webui python3 /workspace/nexus/bootstrap_functions.py"
```
This re-inserts **Auto (Smart Routing)** + **Blueprint Analyzer** and sets the
default model. Then restart Open WebUI so it loads them:
```bash
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 \
  "tmux kill-session -t webui; bash /workspace/boot.sh"
```
*(If bootstrap fails for any reason, fall back to the manual path: Admin Panel →
Functions → Import `openwebui_autorouter_function.py` and
`openwebui_blueprint_function.py` → enable each.)*

## 5. Seed the demo knowledge base (optional)
```bash
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 \
  "cd /workspace/nexus && python3 build_database.py"
```

## Done — what you get
- **Auto (Smart Routing)** model: fast/daily → `qwen3.5:35b`, deep analysis →
  `qwen3.5:122b`, coding → `qwen3.6:27b`, images → `qwen3-vl:32b`, plus built-in
  Word/Excel/PowerPoint export and PDF→Excel.
- **Blueprint Analyzer** model for P&IDs.
- Telemetry off, "Nexus AI" branding, full-context docs, fast uploads.

## What you LOSE vs the old pod
- Chat history (old pod's) — gone.
- That's it. Everything else rebuilds from the staged files.
