# Nexus AI — Local OT/Cybersecurity AI Workbench

A **fully private** AI assistant for an OT (Operational Technology) cybersecurity
consultancy. Everything runs on your own GPU box — **no data ever leaves the
machine**, which is a hard requirement for MNC clients who forbid cloud AI
(ChatGPT/Claude/etc.).

It's built on **[Open WebUI](https://github.com/open-webui/open-webui)** (a
polished, multi-user, ChatGPT-style frontend) backed by **Ollama** for model
serving and **ChromaDB** for the knowledge base. A custom "Auto (Smart Routing)"
pipe makes it feel like one smart model that does everything.

> **Privacy by design:** telemetry/analytics are disabled, auth is on, and the
> models are open-weight and self-hosted. Nothing is sent to any third party.

---

## What it does

| Capability | How |
|---|---|
| **Auto (Smart Routing)** | One model in the UI. It inspects each message and routes: simple → fast model, deep analysis → reasoning model, coding → coder model, images → vision model. |
| **Deep analysis** | IEC 62443 / NIST SP 800-82 gap assessments, risk/threat analysis, reasoning over standards. Streams a collapsible "Thinking" view. |
| **Blueprint Analyzer** | Reads instrument tags off a P&ID (vision model) and looks each one up in the failure-state knowledge base. |
| **Document generation** | Word / Excel / PowerPoint export, built into the router. **Hybrid:** simple files use fast deterministic builders; complex ones (charts, pivots, styling) are written by the coding model and run sandboxed (Claude-style). |
| **PDF → Excel** | Renders each PDF page and reads tables with the vision model for accuracy. |
| **Document chat (RAG)** | Upload a doc and ask about it; full-context so the model sees the whole thing. |

### The model suite (Qwen3.5 / 3.6, open-weight)

| Model | Role |
|---|---|
| `qwen3.5:35b` | Fast / daily driver (default) |
| `qwen3.5:122b` | Deep reasoning (needs an H200/141GB-class GPU, ~78GB weights) |
| `qwen3.6:27b` | Coding + hybrid export codegen |
| `qwen3-vl:32b` | Vision: P&ID reading, table extraction |
| `qwen3-embedding:4b` | Embeddings / semantic search |
| `qwen3.5:2b` | Housekeeping (titles, etc.) |

---

## Architecture

```
   Your Mac                          GPU server (H200 141GB)
 ┌───────────┐  SSH tunnel :8080   ┌──────────────────────────────────┐
 │  Browser  │◄───────────────────►│  Open WebUI  (the ChatGPT-style UI)│
 └───────────┘                     │     │  └─ Auto-router pipe function  │
                                   │     ├─ Ollama   (serves the models)  │
                                   │     └─ ChromaDB (the knowledge base) │
                                   │  All state on /workspace (persistent) │
                                   └──────────────────────────────────────┘
```

- **Your Mac runs nothing heavy** — just a browser and an SSH tunnel.
- **Everything lives on `/workspace`** so models, DB, and config survive a pod
  stop/start. (The container disk is ephemeral — nothing important goes there.)

> ⚠️ **Persistence caveat (RunPod):** a *Volume* disk survives stop/start but is
> destroyed on **terminate**. Back up before terminating, use a *network volume*
> for durability, or — the real production home — an **on-prem workstation**.
> Full details in [`PERSISTENCE.md`](PERSISTENCE.md) /
> [`DEPLOY_WORKSTATION.md`](DEPLOY_WORKSTATION.md).

---

## Quick start (fresh GPU box)

Full step-by-step in [`DEPLOY_FRESH_H200.md`](DEPLOY_FRESH_H200.md). In short:

```bash
# 1. Upload the project + boot script
scp -P <PORT> -i ~/.ssh/id_ed25519 ./* root@<IP>:/workspace/nexus/
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 \
  "cp /workspace/nexus/boot.sh /workspace/boot.sh && bash /workspace/boot.sh"
# boot.sh installs everything, pulls the model suite (~150GB, one time),
# and starts Ollama + ChromaDB + Open WebUI in tmux.

# 2. Tunnel + create your admin account
ssh -N -L 8080:localhost:8080 root@<IP> -p <PORT> -i ~/.ssh/id_ed25519
#   -> open http://localhost:8080 and sign up (first account = admin)

# 3. Restore the custom functions (Auto-router + Blueprint Analyzer)
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 \
  "DATA_DIR=/workspace/open-webui python3 /workspace/nexus/bootstrap_functions.py"
#   then restart Open WebUI so it loads them.
```

After a pod stop/start, just re-run `bash /workspace/boot.sh` and re-open the
tunnel — models are already on `/workspace`, so it's fast.

---

## Loading your real knowledge base

The Blueprint Analyzer / RAG ships with a few **mock** entries. To load real
failure-state manuals and standards:

```bash
# Put files in /workspace/input_docs on the server (PDF, Word, Excel, CSV, text,
# or scanned images — scanned docs are OCR'd by the vision model), then:
ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 \
  "cd /workspace/nexus && python3 ingest.py --reset"
```

`--reset` clears the demo data. The ingester extracts text, finds instrument
tags, and indexes each passage under the tag(s) it mentions.

---

## Configuration

All settings come from environment variables — copy `.env.example` to `.env` and
adjust, or rely on the defaults (which match a local SSH tunnel). Model names,
hosts, and the instrument-tag regex live in `config.py`; the Open WebUI runtime
env is set in `boot.sh`.

```bash
cp .env.example .env
```

---

## The files

| File | Purpose |
|------|---------|
| `boot.sh` | One-command install + start for a fresh/reset GPU box. |
| `services.sh` | Shared service start + health-check definitions (sourced by `boot.sh` and `supervise.sh`). |
| `supervise.sh` | Auto-restart watchdog — polls each service and restarts only the one that died. |
| `models.env` | **Single source of truth** for model names (read by bash *and* Python). |
| `openwebui_autorouter_function.py` | The **Auto (Smart Routing)** pipe: routing, `<think>` streaming, hybrid + sandboxed export, PDF→Excel. |
| `openwebui_blueprint_function.py` | The **Blueprint Analyzer** pipe (P&ID → tags → manuals). |
| `bootstrap_functions.py` | Re-inserts the two pipe functions into a fresh `webui.db`. |
| `config.py` | Central settings (models, hosts, tag pattern); env-overridable. |
| `ingest.py` | Loads real manuals into ChromaDB (run on the server). |
| `build_database.py` | Seeds the demo knowledge base. |
| `backup.sh` | Tarballs the irreplaceable data (DB, uploads, Chroma, code). |
| `test_router.py` | Unit tests for routing + codegen-denylist heuristics. |
| `rag_engine.py` / `chat_engine.py` | Vision OCR + retrieval / chat (legacy Streamlit path). |
| `app.py` | Legacy Streamlit UI (pre-Open WebUI; kept for reference). |
| `DEPLOY_FRESH_H200.md` | Fresh-pod rebuild checklist. |
| `DEPLOY_WORKSTATION.md` | On-prem workstation deployment (production). |
| `PERSISTENCE.md` | What survives what, storage tiers, backup/restore routine. |

## Testing

The routing decisions and the codegen safety denylist are pure functions with
no GPU/network dependency:

```bash
python3 test_router.py     # standalone PASS/FAIL summary
pytest test_router.py      # if you have pytest
```

These catch silent drift — a misroute sending work to the wrong model, or a
denylist gap that would let unsafe generated code run.

---

## Security — code execution (the hybrid export path)

The **hybrid export** feature runs **model-written Python** to build complex
files (charts, pivots, custom styling). That code is executed on the server, so
it's sandboxed in layers. Two are always on; one is opt-in.

| Layer | Always on? | What it does |
|---|---|---|
| **Static denylist** | ✅ | Rejects scripts that touch the network, shell, `subprocess`, or absolute file paths before they run. |
| **Resource limits** | ✅ | Caps memory, CPU seconds, and output size (kills runaway / fork-bomb / OOM scripts). |
| **Minimal env + timeout** | ✅ | Clean temp working dir, no inherited secrets, hard wall-clock timeout. |
| **Strict sandbox** | ⚙️ opt-in | **No network** + filesystem **confined to a temp dir**, via `bubblewrap` (falls back to `unshare -n` for network-only). |

**Trust model:** the denylist is heuristic (evadable) — it backstops the
subprocess limits, it doesn't replace them. For a **single-user, local, trusted**
box, `"basic"` (denylist + rlimits) is reasonable. For **shared or client-facing**
deployments, set strict mode.

**Configuring it** (Admin → Functions → Auto (Smart Routing) → valves):

| Valve | Default | Notes |
|---|---|---|
| `CODE_INTERPRETER` | `True` | Turn the whole codegen path off to disable code execution entirely. |
| `CODE_SANDBOX` | `basic` | Set to `strict` for no-network + confined-filesystem (needs `bubblewrap`; `boot.sh` installs it). |
| `CODE_MEM_MB` | `4096` | Per-run memory cap. |
| `CODE_TIMEOUT` | `90` | Per-run wall-clock cap (seconds). |

> Prefer `nsjail` or `firejail` over bubblewrap? Wire them into
> `_sandbox_prefix()` in `openwebui_autorouter_function.py`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Browser won't load `localhost:8080` | Is the SSH tunnel still running? Did `boot.sh` finish? |
| UI looks frozen on a reply | The reasoning model is "thinking" — the router streams a collapsible **Thinking** section; give it a moment. |
| "Auto (Smart Routing)" missing from model list | Run `bootstrap_functions.py`, then restart Open WebUI. |
| Model not found | `ssh ... "ollama list"` — confirm the suite is pulled. |
| Blueprint finds tags but no manuals | Expected until you load real manuals (`ingest.py --reset`). |
| Everything seems wiped after restart | If it's on `/workspace` it isn't — re-run `bash /workspace/boot.sh`. |

---

## Cost & availability note

H200-class GPUs are billed by the hour and on-demand capacity isn't reserved —
stopping a pod releases the GPU and it may not be free when you return. For
regular use, a reserved/savings plan or an on-prem workstation is the durable
answer. The 122B model in particular is workstation-class hardware.

---

## License / status

Copyright © 2026 Dhanush Krishna. **All rights reserved** — proprietary, source
available for viewing only. See [`LICENSE`](LICENSE). This is the author's own
work.
