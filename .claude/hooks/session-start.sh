#!/usr/bin/env bash
# Rig session-start hook
# Installed to .claude/hooks/session-start.sh by rig-stage.
# Fires before each UserPromptSubmit — all operations are idempotent.

# 0. Post-install health check — runs once after install/upgrade, then skipped
# RIG_HEALTH_CHECK_ACTIVE guard prevents re-entry when the health check calls
# session-start.sh internally to test SCRATCHPAD.md writing behaviour.
if [[ ! -f ".rig-verified" ]] && [[ -x ".claude/hooks/rig-health-check.sh" ]] \
   && [[ "${RIG_HEALTH_CHECK_ACTIVE:-}" != "1" ]]; then
  bash ".claude/hooks/rig-health-check.sh" || true
fi

# 1. Sync remote session files (non-fatal — repo may have no remote or no network)
git pull --ff-only --quiet 2>/dev/null || true

# 2. Write dated session header to SCRATCHPAD.md (idempotent)
today=$(date +%Y-%m-%d)
if grep -qF '<session date>' SCRATCHPAD.md 2>/dev/null; then
  # Fresh template from install — substitute the date placeholder in-place
  sed -i "s|<session date>|$today|" SCRATCHPAD.md
elif ! grep -qF "$today" SCRATCHPAD.md 2>/dev/null; then
  # Existing scratchpad, new calendar day — append a new session block
  printf '\n---\n\n# Session %s\n\n## Working Notes\n\n' "$today" >> SCRATCHPAD.md
fi
