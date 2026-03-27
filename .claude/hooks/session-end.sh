#!/usr/bin/env bash
# Rig session-end reminder
# Installed to .claude/hooks/session-end.sh by rig-stage.
# Fires on the Stop event (when Claude finishes responding).
# Reminds to call mem_session_end if no session_end was saved today.

today=$(date +%Y-%m-%d)
db=".claude/memgram.db"

if [[ ! -f "$db" ]] || ! command -v sqlite3 &>/dev/null; then
  echo ""
  echo "[rig] Call mem_session_end(\"<one-line summary of unsaved work>\") before finishing."
  exit 0
fi

count=$(sqlite3 "$db" \
  "SELECT COUNT(*) FROM observations WHERE type='session_end' AND date(created_at)='$today';" \
  2>/dev/null || echo "0")

if [[ "$count" -eq 0 ]]; then
  echo ""
  echo "[rig] No session memory saved today. Call mem_session_end(\"<summary of unsaved findings>\") before finishing."
fi
