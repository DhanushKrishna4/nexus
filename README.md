# Nexus — Private, self-hosted AI workbench

A **fully self-hosted** AI assistant for environments that can't send data to
cloud AI (privacy/compliance, regulated industries, air-gapped networks).
Everything runs on your own hardware on open-weight models — nothing is ever
sent to a third party.

Built on **[Open WebUI](https://github.com/open-webui/open-webui)** (a polished,
multi-user, ChatGPT-style frontend) with **Ollama** serving the models and
**ChromaDB** as the knowledge base. A custom **Auto (Smart Routing)** layer makes
it feel like one capable model that quietly dispatches each request to the best
specialist behind the scenes.

## Features

| Capability | What it does |
|---|---|
| **Smart routing** | Inspects each message and routes it: simple → fast model, deep analysis → a large reasoning model, coding → a coder model, images → a vision model. One assistant, no manual model-switching. |
| **Live reasoning** | Streams the reasoning model's chain-of-thought into a collapsible "Thinking" view (ChatGPT/Claude-style), so the UI is never frozen during long thinks. |
| **Document generation** | Word / Excel / PowerPoint export. **Hybrid:** simple files use fast deterministic builders; complex ones (charts, pivots, custom styling) are written by the coding model and executed in a **sandboxed** subprocess. |
| **PDF → Excel** | Extracts tables by rendering each page and reading it with the vision model. |
| **Document chat (RAG)** | Upload a document and ask about it, grounded in its full content. |
| **Blueprint Analyzer** | Reads instrument tags off an engineering diagram (P&ID) with the vision model and cross-references a failure-mode knowledge base. |

## Stack

`Python` · `Open WebUI` · `Ollama` · `ChromaDB` · open-weight LLMs
(Qwen3.5 / 3.6 family) · `bubblewrap` (sandboxing)

### Model suite

| Role | Model |
|---|---|
| Fast / daily chat (default) | `qwen3.5:35b` |
| Deep reasoning | `qwen3.5:122b` |
| Coding + export codegen | `qwen3.6:27b` |
| Vision (diagrams, tables) | `qwen3-vl:32b` |
| Embeddings / search | `qwen3-embedding:4b` |
| Background tasks | `qwen3.5:2b` |

Model names live in one place — [`models.env`](models.env) — read by both the
shell scripts and the Python, so the whole stack stays in sync.

## Architecture

```
  Browser ──▶ Open WebUI ──▶ Auto (Smart Routing) pipe
                  │              ├─ fast / reasoning / coding / vision models  (Ollama)
                  │              ├─ sandboxed code-interpreter  (document export)
                  │              └─ knowledge base               (ChromaDB)
```

- **Auto (Smart Routing)** is a custom Open WebUI *pipe function* — it does the
  routing, reasoning-stream handling, and document generation in one place
  (`openwebui_autorouter_function.py`).
- **Blueprint Analyzer** is a second pipe for engineering-diagram analysis.

## Running it

Needs a Linux host with a GPU, plus Ollama and Python 3.11+.

```bash
# 1. Install deps
pip install -r requirements.txt

# 2. Bring up Ollama + ChromaDB + Open WebUI and pull the model suite
bash boot.sh

# 3. Open the UI, create an admin account, then register the custom pipes
python3 bootstrap_functions.py     # adds Auto Routing + Blueprint Analyzer
```

`boot.sh` installs the stack, pulls the models, starts every service under a
supervisor that auto-restarts anything that dies, and warms the default model.
Model names, hosts, and other settings are environment-overridable — copy
`.env.example` to `.env` to customize.

> Deployment guides for specific targets: a cloud GPU box
> ([`DEPLOY_FRESH_H200.md`](DEPLOY_FRESH_H200.md)) and an on-prem workstation
> ([`DEPLOY_WORKSTATION.md`](DEPLOY_WORKSTATION.md)). Backup/restore and data
> durability: [`PERSISTENCE.md`](PERSISTENCE.md).

## Security — executing model-written code

The hybrid export feature runs **model-generated Python** to build complex
files, so it's sandboxed in layers (two always on, one opt-in):

| Layer | Default | What it does |
|---|---|---|
| Static denylist | on | Rejects scripts that touch the network, shell, `subprocess`, or absolute paths before they run. |
| Resource limits | on | Caps memory, CPU, and output size (kills runaway / OOM / fork-bomb scripts). |
| Strict sandbox | opt-in | No network + filesystem confined to a temp dir, via `bubblewrap` (`unshare -n` fallback). |

Tunable via the router's valves (`CODE_INTERPRETER`, `CODE_SANDBOX`,
`CODE_MEM_MB`, `CODE_TIMEOUT`).

## Testing

Routing decisions and the codegen denylist are pure functions — tested without a
GPU:

```bash
python3 test_router.py     # standalone PASS/FAIL summary
pytest test_router.py      # if you have pytest
```

## Privacy by design

Telemetry and analytics are disabled, authentication is on, and every model is
open-weight and self-hosted. No request leaves the machine.

## License

Copyright © 2026 Dhanush Krishna. **All rights reserved** — proprietary, source
available for viewing only. See [`LICENSE`](LICENSE).
