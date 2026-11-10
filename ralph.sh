#!/usr/bin/env bash
# ralph.sh — the Ralph loop. Reference: https://ghuntley.com/ralph/
#
# WARNING: --dangerously-skip-permissions means the agent runs ANY tool
# (bash, file writes, network) with zero confirmation. Only run in a repo
# you're prepared to let an autonomous agent rewrite. Ctrl-C to stop.
#
# Bling runs in two phases, same runner, different prompt file:
#   spec phase   →  PROMPT_FILE=PROMPT.spec.md ./ralph.sh   # writes specs/, then fix_plan.md
#   build phase  →  ./ralph.sh                              # drains fix_plan.md (default PROMPT.md)

set -u
set -o pipefail

ITER=0
MAX_ITERATIONS="${MAX_ITERATIONS:-0}"   # 0 = unlimited
SLEEP_BETWEEN="${SLEEP_BETWEEN:-2}"
LOG_DIR="${LOG_DIR:-logs}"
MODEL="${RALPH_MODEL:-}"                # e.g. RALPH_MODEL=claude-opus-4-8
PROMPT_FILE="${PROMPT_FILE:-PROMPT.md}" # PROMPT.spec.md for the spec phase

cd "$(dirname "$0")"
mkdir -p "$LOG_DIR"

[ -f "$PROMPT_FILE" ] || { echo "$PROMPT_FILE not found in $(pwd)" >&2; exit 1; }
command -v claude >/dev/null || { echo "claude CLI not on PATH" >&2; exit 1; }

trap 'echo; echo "── Ralph stopped at iteration $ITER ──"; exit 0' INT TERM

echo "── Ralph starting in $(pwd) ──"
echo "PROMPT_FILE=$PROMPT_FILE"
echo "MAX_ITERATIONS=$MAX_ITERATIONS (0 = unlimited)"
echo "SLEEP_BETWEEN=${SLEEP_BETWEEN}s   logs → $LOG_DIR/"
[ -n "$MODEL" ] && echo "model → $MODEL"
echo

CLAUDE_ARGS=(--print --dangerously-skip-permissions)
[ -n "$MODEL" ] && CLAUDE_ARGS+=(--model "$MODEL")

while :; do
  ITER=$((ITER + 1))
  TS=$(date +%Y%m%d-%H%M%S)
  LOG_FILE="$LOG_DIR/iter-$(printf '%05d' "$ITER")-$TS.log"
  echo "── iteration $ITER  $(date '+%H:%M:%S')  log: $LOG_FILE ──"

  cat "$PROMPT_FILE" | claude "${CLAUDE_ARGS[@]}" 2>&1 | tee "$LOG_FILE"
  RC=${PIPESTATUS[1]}
  echo
  echo "── iteration $ITER done (rc=$RC) ──"
  echo

  if [ "$MAX_ITERATIONS" != 0 ] && [ "$ITER" -ge "$MAX_ITERATIONS" ]; then
    echo "Reached MAX_ITERATIONS=$MAX_ITERATIONS. Exiting."
    exit 0
  fi
  sleep "$SLEEP_BETWEEN"
done
