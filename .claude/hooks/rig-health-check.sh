#!/usr/bin/env bash
# Rig post-install health check
# Installed to .claude/hooks/rig-health-check.sh by rig-stage.
#
# Runs automatically on the first session prompt after install/upgrade
# (when .rig-verified is absent). On full pass, writes .rig-verified
# so future session starts skip this check.
#
# Run manually at any time: bash .claude/hooks/rig-health-check.sh

set -uo pipefail

MARKER=".rig-verified"
PASS=0
FAIL=0

ok()   { echo "  ✓ $1"; PASS=$((PASS + 1)); }
fail() { echo "  ✗ $1"; FAIL=$((FAIL + 1)); }

check_file() {
  local desc="$1" path="$2"
  if [[ -f "$path" ]]; then ok "$desc"; else fail "$desc — $path not found"; fi
}

check_dir() {
  local desc="$1" path="$2"
  if [[ -d "$path" ]]; then ok "$desc"; else fail "$desc — $path not found"; fi
}

check_exec() {
  local desc="$1" path="$2"
  if [[ -x "$path" ]]; then ok "$desc"; else fail "$desc — $path not executable"; fi
}

check_contains() {
  local desc="$1" path="$2" needle="$3"
  if grep -qF "$needle" "$path" 2>/dev/null; then
    ok "$desc"
  else
    fail "$desc — '$needle' not found in $path"
  fi
}

check_not_contains() {
  local desc="$1" path="$2" needle="$3"
  if grep -qF "$needle" "$path" 2>/dev/null; then
    fail "$desc — '$needle' still present in $path"
  else
    ok "$desc"
  fi
}

echo "[rig] Running post-install health check..."
echo ""

# ── File existence ─────────────────────────────────────────────────────────────
echo "-- files --"
check_file "CLAUDE.md"                    "CLAUDE.md"
check_file "CONVENTIONS.md"               "CONVENTIONS.md"
check_file "AGENTS.md"                    "AGENTS.md"
check_file "settings.json"                ".claude/settings.json"
check_dir  "agents dir"                   ".claude/agents"
check_dir  "skills dir"                   ".claude/skills"
check_file "session-start.sh"             ".claude/hooks/session-start.sh"
check_file "session-end.sh"               ".claude/hooks/session-end.sh"
check_file "rig-health-check.sh"          ".claude/hooks/rig-health-check.sh"
check_file "pre-commit hook"              ".git/hooks/pre-commit"

# ── Executability ──────────────────────────────────────────────────────────────
echo ""
echo "-- permissions --"
check_exec "session-start.sh executable" ".claude/hooks/session-start.sh"
check_exec "session-end.sh executable"   ".claude/hooks/session-end.sh"
check_exec "pre-commit executable"       ".git/hooks/pre-commit"

# ── CLAUDE.md content ──────────────────────────────────────────────────────────
echo ""
echo "-- CLAUDE.md --"
check_contains     "@.codebase-context/repo_map.md"  "CLAUDE.md"  "@.codebase-context/repo_map.md"
check_contains     "@CONVENTIONS.md import"           "CLAUDE.md"  "@CONVENTIONS.md"
check_contains     "@AGENTS.md import"                "CLAUDE.md"  "@AGENTS.md"
check_contains     "mem_context in session protocol"  "CLAUDE.md"  "mem_context"
check_contains     "mem_save in session protocol"     "CLAUDE.md"  "mem_save"
check_not_contains "<Project Name> substituted"       "CLAUDE.md"  "<Project Name>"
check_not_contains "<language> substituted"           "CLAUDE.md"  "<language and primary tools>"

# ── settings.json content ──────────────────────────────────────────────────────
echo ""
echo "-- settings.json --"
check_contains "mcpServers configured"   ".claude/settings.json"  "mcpServers"
check_contains "memgram MCP registered" ".claude/settings.json"  "memgram"
check_contains "UserPromptSubmit hook"   ".claude/settings.json"  "UserPromptSubmit"
check_contains "Stop hook"               ".claude/settings.json"  "Stop"
check_contains "session-start.sh wired" ".claude/settings.json"  "session-start.sh"
check_contains "session-end.sh wired"   ".claude/settings.json"  "session-end.sh"

# ── .gitignore entries ─────────────────────────────────────────────────────────
echo ""
echo "-- .gitignore --"
check_contains "SCRATCHPAD.md gitignored"  ".gitignore"  "SCRATCHPAD.md"
check_contains ".rig-verified gitignored"  ".gitignore"  ".rig-verified"

# ── Agent and skill counts ─────────────────────────────────────────────────────
echo ""
echo "-- agents / skills --"
agent_count=$(find .claude/agents -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
skill_count=$(find .claude/skills -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$agent_count" -ge 9 ]]; then
  ok "agents installed ($agent_count)"
else
  fail "agents: expected >=9, got $agent_count"
fi
if [[ "$skill_count" -ge 10 ]]; then
  ok "skills installed ($skill_count)"
else
  fail "skills: expected >=10, got $skill_count"
fi

# ── Session hook behaviour ─────────────────────────────────────────────────────
echo ""
echo "-- session hooks --"
today=$(date +%Y-%m-%d)
export RIG_HEALTH_CHECK_ACTIVE=1
bash ".claude/hooks/session-start.sh" 2>/dev/null || true
if grep -qF "$today" SCRATCHPAD.md 2>/dev/null; then
  ok "session-start writes today's date to SCRATCHPAD.md"
else
  fail "session-start did not write today's date to SCRATCHPAD.md"
fi

# ── Result ─────────────────────────────────────────────────────────────────────
echo ""
echo "[rig] Health check: $PASS passed, $FAIL failed"

if [[ $FAIL -eq 0 ]]; then
  printf "RIG_VERIFIED=true\nTIMESTAMP=%s\nCHECKS=%d passed\n" \
    "$(date +%Y-%m-%dT%H:%M:%S)" "$PASS" > "$MARKER"
  echo "[rig] ✓ All checks passed — .rig-verified written (skipped on future session starts)"
  echo "[rig]   To re-run: rm .rig-verified && bash .claude/hooks/rig-health-check.sh"
else
  echo "[rig] ✗ $FAIL check(s) failed — fix then re-run: bash .claude/hooks/rig-health-check.sh"
  echo "[rig]   Or reinstall: rig-stage install --force"
  exit 1
fi
