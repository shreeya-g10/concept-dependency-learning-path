#!/usr/bin/env bash
# RQ1 night 1 on the benchmarks: discovery_only (--pairs, given direction) on all 5
# graphs, then the 5 baseline_prompt calls. qwen2.5:7b-instruct only.
#
# Run in a plain terminal OUTSIDE Claude Code, from the repo root:
#     caffeinate -i ./scripts/rq1_night1.sh
#
# - Resumes from the LLM cache (.cache/llm): re-running repeats only the calls not made.
# - Prints seconds per call after the first 20 NEW calls (cache hits write no file),
#   so a slow machine (e.g. memory pressure, ~51 s/call) shows up early. Stop with Ctrl-C.
# - Logs everything to outputs/rq1/night1.log; a failed graph is logged and skipped.
set -o pipefail
cd "$(dirname "$0")/.." || exit 1

PY=.venv/bin/python
LOG=outputs/rq1/night1.log
MODEL=qwen2.5:7b-instruct
COURSES="al_cpl_data_mining al_cpl_geometry al_cpl_physics al_cpl_precalculus university_course"
mkdir -p outputs/rq1 .cache/llm
log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

for c in $COURSES; do
  [ -f "outputs/benchmarks/$c/sample_pairs.csv" ] || {
    log "missing outputs/benchmarks/$c/sample_pairs.csv: run python -m cdlp.benchmarks.sample"
    exit 1
  }
done
for m in $(ollama ps | awk 'NR>1{print $1}'); do
  [ "$m" != "$MODEL" ] && ollama stop "$m" && log "unloaded $m (one model at a time)"
done

MARK=$(mktemp)  # new cache files are newer than this
log "night 1 start (model $MODEL); log: $LOG"
(
  start=$(date +%s)
  while sleep 10; do
    n=$(find .cache/llm -name '*.json' -newer "$MARK" | wc -l | tr -d ' ')
    if [ "$n" -ge 20 ]; then
      log "first $n new calls: $(( ($(date +%s) - start) / n )) s per call (~10 s expected; ~51 s means memory pressure)"
      break
    fi
  done
) &
WATCH=$!
trap 'kill $WATCH 2>/dev/null; rm -f "$MARK"' EXIT

run() {  # run <label> <course> <args...>
  local label=$1 c=$2; shift 2
  local t; t=$(date +%s)
  log "$label $c: start"
  "$PY" -m cdlp.discovery --concepts "outputs/benchmarks/$c/sample_concepts.json" \
      --out-dir "outputs/rq1/$c" "$@" 2>&1 \
      | { grep -v -e "frozen importlib" -e "Deprecation" || true; } | tee -a "$LOG"
  local status=${PIPESTATUS[0]}  # the python process, not the log filter
  log "$label $c: exit $status after $(( $(date +%s) - t )) s"
}

for c in $COURSES; do
  run discovery_only "$c" --pairs "outputs/benchmarks/$c/sample_pairs.csv" \
      --pairs-direction given --stats "outputs/rq1/$c/discovery_only.stats.json"
done
for c in $COURSES; do
  run baseline_prompt "$c" --baseline-only --num-ctx 16384 \
      --stats "outputs/rq1/$c/baseline_prompt.stats.json"
done

ollama stop "$MODEL"
log "night 1 end: $(ls outputs/rq1/*/relationships.json 2>/dev/null | wc -l | tr -d ' ')/5 discovery, $(ls outputs/rq1/*/relationships_baseline.json 2>/dev/null | wc -l | tr -d ' ')/5 baseline"
