#!/bin/bash
# Auto-restart watchdog for the Nexus stack. Polls Ollama, ChromaDB, and Open
# WebUI; restarts ONLY the one that died (not the whole stack). Runs in its own
# tmux session, launched by boot.sh. Logs to /workspace/supervise.log.
#
# Tunables (env):
#   SUPERVISE_INTERVAL   seconds between checks            (default 30)
#   SUPERVISE_THRESHOLD  consecutive failures before restart (default 2)
#   SUPERVISE_GRACE      seconds to wait before first check (default 90)

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$DIR/services.sh"

INTERVAL="${SUPERVISE_INTERVAL:-30}"
THRESHOLD="${SUPERVISE_THRESHOLD:-2}"
GRACE="${SUPERVISE_GRACE:-90}"

log() { echo "[$(date '+%F %T')] $*" >> /workspace/supervise.log; }

# Consecutive-failure counters (restart only after THRESHOLD in a row, so a slow
# start or a brief blip doesn't trigger a needless restart).
declare -A fails=( [ollama]=0 [chroma]=0 [webui]=0 )

check() {  # check <name> <health_fn> <start_fn>
  local name="$1" hfn="$2" sfn="$3"
  if "$hfn"; then
    [ "${fails[$name]}" -gt 0 ] && log "$name recovered"
    fails[$name]=0
  else
    fails[$name]=$(( fails[$name] + 1 ))
    log "$name health check failed (${fails[$name]}/${THRESHOLD})"
    if [ "${fails[$name]}" -ge "$THRESHOLD" ]; then
      log "$name DOWN -> restarting"
      "$sfn"
      fails[$name]=0
    fi
  fi
}

log "supervisor started (interval=${INTERVAL}s threshold=${THRESHOLD} grace=${GRACE}s)"
sleep "$GRACE"
while true; do
  check ollama health_ollama start_ollama
  check chroma health_chroma start_chroma
  check webui  health_webui  start_webui
  sleep "$INTERVAL"
done
