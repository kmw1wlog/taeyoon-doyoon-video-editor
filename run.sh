#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
child=""
stopping=0
stop() {
  stopping=1
  if [[ -n "$child" ]]; then kill -TERM "$child" 2>/dev/null || true; fi
}
trap stop INT TERM
cooldown=2
while (( ! stopping )); do
  python3 server.py &
  child=$!
  wait "$child"
  code=$?
  child=""
  if (( stopping )); then break; fi
  printf 'Editor stopped (exit %s). Restarting in %s seconds.\n' "$code" "$cooldown" >&2
  sleep "$cooldown"
  if (( cooldown < 60 )); then cooldown=$((cooldown * 2)); fi
done
