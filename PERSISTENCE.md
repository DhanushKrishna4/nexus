# Persistence & durability — where your data really lives

The #1 fragility of this project is the **"pod terminated → rebuild from
scratch"** churn. This doc explains exactly what survives what, and how to make
the deployment durable. **Read this before you `terminate` anything.**

## What's irreplaceable vs. re-downloadable

| Data | Where | Replaceable? |
|---|---|---|
| Model weights (~150GB) | `/workspace/ollama_models` | ✅ Re-downloads via `boot.sh` (slow, but free). |
| **Open WebUI DB** (users, chats, **the pipe functions**, settings) | `/workspace/open-webui/webui.db` | ❌ **Irreplaceable** — back it up. |
| **Uploaded files** | `/workspace/open-webui/uploads` | ❌ Irreplaceable. |
| **ChromaDB knowledge base** | `/workspace/chroma_db` | ⚠️ Re-buildable from source docs *if* you kept them. |
| App code | `/workspace/nexus` + `/workspace/boot.sh` | ✅ It's in this repo. |

So a backup only needs the DB + uploads + Chroma store + code — that's exactly
what [`backup.sh`](backup.sh) captures (a few MB, not the 150GB of models).

## The three storage tiers (RunPod)

| Tier | Survives stop/start | Survives **terminate** | Upfront cost | Use when |
|---|:---:|:---:|---|---|
| **Container disk** | ❌ | ❌ | none | never store anything here |
| **Volume disk** (current) | ✅ | ❌ | none | a single dev pod you won't terminate |
| **Network volume** | ✅ | ✅ (portable across pods) | yes (pre-paid) | you want durability + GPU flexibility |

The current setup uses a **Volume disk** — fine until the pod is *terminated*,
which **destroys it**. If you find yourself rebuilding often, the
**Network volume** pays for itself in saved time.

## The production answer: on-prem workstation

RunPod is the **temporary dev box**. The real home for this — especially the
122B model, which is workstation-class — is a **company/on-prem workstation**:
no GPU lottery, no hourly billing, no terminate-and-rebuild, and the data never
leaves the building (the whole point). See
[`DEPLOY_WORKSTATION.md`](DEPLOY_WORKSTATION.md).

## Recommended routine

1. **Back up regularly** (especially before any risky pod operation):
   ```bash
   ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 "bash /workspace/backup.sh"
   ```
   Keeps the last 7 tarballs in `/workspace/backups`. Pull one to your Mac:
   ```bash
   scp -P <PORT> -i ~/.ssh/id_ed25519 root@<IP>:/workspace/backups/<file>.tgz ~/Desktop/
   ```

2. **Automate it** — run the backup from the supervisor or a cron, e.g. hourly:
   ```bash
   ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 \
     '(crontab -l 2>/dev/null; echo "0 * * * * bash /workspace/backup.sh") | crontab -'
   ```

3. **Restore** onto a fresh pod (after `boot.sh` has recreated the dirs):
   ```bash
   tar -xzf nexus-backup-<TS>.tgz -C /workspace
   # then restart Open WebUI so it picks up the restored DB
   ```

4. **Migrate to a network volume / workstation** when the churn gets old — copy
   `/workspace` (or just the backup tarball) to the new persistent storage.

> Bottom line: **never `terminate` a Volume-disk pod without a current backup.**
> Stop is safe; terminate is forever.
