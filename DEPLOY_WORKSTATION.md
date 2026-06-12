# Deploying Nexus on a Workstation

This guide is for installing the Nexus workbench on an on-prem **workstation**
(the company deployment), as opposed to the RunPod dev box. Everything runs
locally on the machine — no cloud, no SSH tunnel. That's the point: client data
never leaves the workstation.

---

## 1. Hardware requirement (read first)

The workbench uses four models, but **Ollama loads them on demand and unloads
idle ones** — so you don't need them all in VRAM at once. The sizing constraint
is the **largest** model, `qwen2.5:72b`, which needs roughly **48 GB of VRAM**
(4-bit).

| Models | Approx VRAM (loaded) | Disk |
|--------|----------------------|------|
| `qwen2.5:72b`   — chat       | ~48 GB | ~47 GB |
| `qwq:32b`       — reasoning  | ~20 GB | ~20 GB |
| `qwen2.5vl:7b`  — vision     | ~6 GB  | ~6 GB |
| `bge-m3`        — embeddings | ~1 GB  | ~1 GB |

| Workstation GPU | Works? | Notes |
|-----------------|--------|-------|
| A100 / H100 80GB | ✅ Ideal | Holds 72B + vision + embeddings together; loads QwQ on demand. |
| RTX 6000 Ada / A6000 48GB | ✅ OK | Runs each model fine; switches between the big ones on demand (brief reload). |
| 2× 24GB (e.g. 2× RTX 4090) | ✅ OK | Ollama splits large models across both GPUs. |
| Single 24GB | ⚠️ Limited | Use smaller models — see below. |

**To use smaller models** (if VRAM is limited), set env vars — no code change:
```
CHAT_MODEL=qwen2.5:14b        # ~10GB  (or qwen2.5:7b ~5GB)
REASONING_MODEL=qwq:32b       # or drop to the same smaller chat model
```

### Auto-routing mode (important VRAM note)
The Assistant's **"Auto"** mode picks the fast vs. reasoning model per question.
For it to feel instant, **both chat models must stay resident in VRAM at once**
(otherwise every switch reloads a model — slow). That's controlled by:
```
OLLAMA_KEEP_ALIVE=-1          # keep models loaded indefinitely (default)
```

- **80 GB (A100/H100):** the full 72B + QwQ + vision + embed stack (~75 GB)
  stays hot → **Auto works smoothly. Recommended for Auto.**
- **48 GB:** use the 32B chat stack so both big models fit hot:
  ```
  CHAT_MODEL=qwen2.5:32b
  REASONING_MODEL=qwq:32b      # ~47GB total resident — fits 48GB
  ```
- **Under 48 GB:** don't keep both loaded — set `OLLAMA_KEEP_ALIVE=10m` and
  use the **manual** mode selector (General / Deep reasoning) instead of Auto,
  so models take turns without thrashing.

---

## 2. Install the prerequisites

**Both OSes need:** [Ollama](https://ollama.com/download) and Python 3.10+.

> ⚠️ **Use a recent Ollama (v0.4.0 or newer; latest is best).** The vision model
> relies on a model architecture that older Ollama builds don't support — an
> out-of-date Ollama will fail to load it with an error like
> `unknown model architecture`. Always install from the official link above;
> don't use an old bundled/distro package. Check with: `ollama --version`.

### Windows
1. Install **Ollama for Windows** (installer from the link above; it runs as a
   background service automatically).
2. Install **Python** from python.org (tick "Add to PATH").
3. Open *Command Prompt* in the project folder and run:
   ```
   pip install -r requirements.txt
   ```

### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh     # installs + starts ollama
sudo apt-get install -y python3-pip
pip install -r requirements.txt
```

---

## 3. First run

From the project folder:

- **Windows:** double-click `run_local.bat` (or run it in a terminal)
- **Linux/macOS:** `./run_local.sh`

The script will, on first run, download the two models (~53 GB total, one time),
start ChromaDB and the app, then open on **http://localhost:8501**.

### Load the failure-state data
The blueprint tool ships with 3 demo manuals. To load real ones:
1. Put your documents (PDF/Word/Excel/CSV/text/images) in an `input_docs` folder
   next to the app.
2. Run:
   ```
   python ingest.py --reset
   ```
   (`--reset` replaces the demo data with your real content.)

To just (re)seed the demo data instead: `python build_database.py`.

---

## 4. Auto-start on boot (so users don't run commands)

### Linux (systemd)
Edit `nexus.service` (`User=`, `WorkingDirectory=`), then:
```bash
sudo cp nexus.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nexus
```
The app now starts automatically whenever the workstation boots.

### Windows (Task Scheduler)
Create a task that runs `run_local.bat` "At log on" (or "At startup" with the
user's credentials). Or drop a shortcut to `run_local.bat` in the Startup folder
(`shell:startup`).

---

## 5. Letting other people on the office network use it

By default the app listens only on the workstation itself. To let colleagues
reach it from their own machines:

1. Serve on all interfaces — edit the last line of `run_local.sh` / `run_local.bat`
   to add `--server.address 0.0.0.0`:
   ```
   streamlit run app.py --server.address 0.0.0.0 --server.port 8501
   ```
2. Open port **8501** in the workstation firewall.
3. Colleagues open **http://WORKSTATION-IP:8501** in their browser.

⚠️ **If you expose it on the network, set a password** so it isn't open to the
whole office:
```
APP_PASSWORD=somethingstrong        # Windows: set it as an environment variable
                                    # Linux: add Environment=APP_PASSWORD=... to nexus.service
```
With `APP_PASSWORD` set, the app shows a login gate. Unset = no gate (fine for a
single-user workstation).

---

## 6. Files reference

See `README.md` for what each Python file does. The workstation-specific files
are: `run_local.sh`, `run_local.bat`, `nexus.service`, and this guide.
(The RunPod-specific `start.sh` / `server_setup.sh` are for the dev box and can
be ignored on a workstation.)
