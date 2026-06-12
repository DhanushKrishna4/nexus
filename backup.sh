#!/bin/bash
# Back up the IRREPLACEABLE Nexus data (not the models — those re-download).
# Captures: Open WebUI DB (users, chats, functions, settings) + its uploads,
# the ChromaDB store, and the app code. Writes a timestamped tarball to
# /workspace/backups (which persists on the volume).
#
#   bash /workspace/backup.sh
#
# To also pull it to your Mac:
#   scp -P <PORT> -i ~/.ssh/id_ed25519 \
#     root@<IP>:/workspace/backups/<file>.tgz ~/Desktop/
set -e
TS=$(date +%Y%m%d-%H%M%S)
OUT=/workspace/backups
mkdir -p "$OUT"
ARCHIVE="$OUT/nexus-backup-$TS.tgz"

echo "Backing up to $ARCHIVE …"
tar -czf "$ARCHIVE" \
  -C /workspace \
  open-webui/webui.db \
  open-webui/uploads \
  chroma_db \
  nexus \
  boot.sh \
  2>/dev/null || true

# Keep only the 7 most recent backups.
ls -1t "$OUT"/nexus-backup-*.tgz 2>/dev/null | tail -n +8 | xargs -r rm -f

echo "Done. Size: $(du -h "$ARCHIVE" | cut -f1)"
echo "Backups on volume:"
ls -lh "$OUT"/nexus-backup-*.tgz 2>/dev/null | tail -7
