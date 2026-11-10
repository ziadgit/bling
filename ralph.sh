#!/usr/bin/env bash
# ralph.sh — time-boxed Ralph loop. Reference: https://ghuntley.com/ralph/
#
# WARNING: --dangerously-skip-permissions lets the agent run ANY tool (bash, file writes,
# network) with zero confirmation. Only run it in this repo. Ctrl-C stops it.
#
#   ./ralph.sh                    # 27-minute build: drains fix_plan.md, one item per iteration
#   DEADLINE_MIN=40 ./ralph.sh    # different time box
#   RALPH_MODEL=claude-opus-5-5 ./ralph.sh
#
# Stops when: fix_plan.md has no unchecked items, the wall clock runs out (a running iteration
# is killed at the deadline), or MAX_ITERATIONS is reached.

set -u
set -o pipefail
set -m   # job control: each background job gets its own process group, so we can kill it whole

DEADLINE_MIN="${DEADLINE_MIN:-27}"
MIN_ITER_SEC="${MIN_ITER_SEC:-90}"      # don't start an iteration with less time than this
MAX_ITERATIONS="${MAX_ITERATIONS:-0}"   # 0 = unlimited (the deadline still applies)
LOG_DIR="${LOG_DIR:-logs}"
MODEL="${RALPH_MODEL:-}"
PROMPT_FILE="${PROMPT_FILE:-PROMPT.md}"

cd "$(dirname "$0")"
mkdir -p "$LOG_DIR"
[ -f "$PROMPT_FILE" ] || { echo "$PROMPT_FILE not found in $(pwd)" >&2; exit 1; }
command -v claude >/dev/null || { echo "claude CLI not on PATH" >&2; exit 1; }

START=$(date +%s)
END=$((START + DEADLINE_MIN * 60))
START_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "")
ITER=0
PID=""
WD=""

remaining() { echo $((END - $(date +%s))); }
pending() { grep -c '^- \[ \]' fix_plan.md 2>/dev/null || true; }

summary() {
  local elapsed=$(( $(date +%s) - START ))
  echo
  echo "── Ralph finished: $ITER iteration(s) in $((elapsed / 60))m$((elapsed % 60))s ──"
  echo "fix_plan: $(grep -c '^- \[x\]' fix_plan.md 2>/dev/null || true) done, $(pending) pending"
  [ -n "$START_COMMIT" ] && git --no-pager log --oneline "$START_COMMIT"..HEAD
  if [ -n "$(git status --porcelain)" ]; then
    echo "Uncommitted changes left by an interrupted iteration (git status):"
    git status --short
  fi
}

stop_now() {
  [ -n "$PID" ] && kill -TERM -"$PID" 2>/dev/null
  [ -n "$WD" ] && kill -TERM -"$WD" 2>/dev/null
  summary
  exit 0
}
trap stop_now INT TERM

CLAUDE_ARGS=(--print --dangerously-skip-permissions)
[ -n "$MODEL" ] && CLAUDE_ARGS+=(--model "$MODEL")

echo "── Ralph starting in $(pwd) ──"
echo "deadline: ${DEADLINE_MIN} min (until $(date -r "$END" '+%H:%M:%S'))   logs → $LOG_DIR/"
[ -n "$MODEL" ] && echo "model → $MODEL"
echo

while :; do
  if [ "$(pending)" -eq 0 ]; then echo "fix_plan.md is fully checked off."; break; fi
  R=$(remaining)
  if [ "$R" -lt "$MIN_ITER_SEC" ]; then echo "Time's up (${R}s left)."; break; fi
  if [ "$MAX_ITERATIONS" != 0 ] && [ "$ITER" -ge "$MAX_ITERATIONS" ]; then
    echo "Reached MAX_ITERATIONS=$MAX_ITERATIONS."; break
  fi

  ITER=$((ITER + 1))
  LOG_FILE="$LOG_DIR/iter-$(printf '%03d' "$ITER")-$(date +%Y%m%d-%H%M%S).log"
  echo "── iteration $ITER  $(date '+%H:%M:%S')  ${R}s left  $(pending) pending  log: $LOG_FILE ──"

  ( cat "$PROMPT_FILE" | claude "${CLAUDE_ARGS[@]}" 2>&1 | tee "$LOG_FILE" ) &
  PID=$!
  ( sleep "$R"; echo; echo "── deadline hit, stopping iteration $ITER ──"; kill -TERM -"$PID" 2>/dev/null ) &
  WD=$!

  wait "$PID"
  RC=$?
  kill -TERM -"$WD" 2>/dev/null
  wait "$WD" 2>/dev/null
  PID=""; WD=""
  echo
  echo "── iteration $ITER done (rc=$RC) ──"
  echo
done

summary
