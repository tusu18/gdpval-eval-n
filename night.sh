#!/bin/bash
# Study v3.1 overnight runner. Every phase is resumable: re-running a phase skips finished work.
#   export OPENROUTER_API_KEY=...         (judge phases only; never written to disk)
#   bash night.sh 1     fetch references, prepare, solve r1 (Sonnet + Opus), freeze the random sample, write blind packets
#   bash night.sh 2     judge r1 (both judges), pairwise preference on all r1 pairs, report
#   bash night.sh 3     solve r2 repeats, judge r2, report
#   bash night.sh 4     full-rubric check on human-confirmed errors (after you have recorded labels)
#   bash night.sh all   1 then 2 then 3
# Logs: output/study_v3/logs/phase<N>.log. Keeps the Mac awake while running.
set -uo pipefail
cd "$(dirname "$0")"
export STUDY_CONFIG=config/study_v31.json STUDY_V3_TIMEOUT=3600
LOG=output/study_v3/logs; mkdir -p "$LOG"
WAKE=""; command -v caffeinate >/dev/null && WAKE="caffeinate -dimsu"
need_key() { [ -n "${OPENROUTER_API_KEY:-}" ] || { echo "Set OPENROUTER_API_KEY first (export OPENROUTER_API_KEY=...)"; exit 2; }; }
run() { echo; echo ">>> $*"; $WAKE "$@"; }

phase1() {
  run python3 scripts/fetch_references_v31.py || { echo "reference download failed; fix and re-run phase 1"; return 1; }
  run python3 scripts/study_v3_pipeline.py prepare
  run python3 scripts/study_v3_pipeline.py solve --models sonnet opus --workers 3 --repeat 1
  run python3 scripts/study_v3_pipeline.py solve --models sonnet opus --workers 2 --repeat 1   # retries timeouts and no-output runs once
  [ -f output/study_v3/calibration_set_v31.json ] || run python3 scripts/human_review_kit.py select-random
  run python3 scripts/human_review_kit.py packets-random
  run python3 scripts/human_review_kit.py packets-hist-sol
  echo; echo "Phase 1 done. Blind packets: output/study_v3/review_v31/ (22) and output/study_v3/review_hist_sol/ (5). Do not open judge_runs/ until they are labeled."
}
phase2() {
  need_key
  run python3 scripts/study_v3_pipeline.py judge --max-usd 65 --workers 3
  run python3 scripts/study_v3_pipeline.py judge --max-usd 65 --workers 2   # retries execution errors
  run python3 scripts/pairwise_grader_16.py build
  run python3 scripts/pairwise_grader_16.py judge --max-usd 20 --workers 2
  run python3 scripts/pairwise_grader_16.py report > /dev/null
  run python3 scripts/study_v3_pipeline.py report > /dev/null
  echo "Phase 2 done."
}
phase3() {
  need_key
  run python3 scripts/study_v3_pipeline.py solve --models sonnet opus --workers 3 --repeat 2
  run python3 scripts/study_v3_pipeline.py judge --max-usd 135 --workers 3
  run python3 scripts/study_v3_pipeline.py report > /dev/null
  echo "Phase 3 done."
}
phase4() {
  need_key
  run python3 scripts/full_rubric_17.py judge --max-usd 30 --workers 2
  run python3 scripts/full_rubric_17.py report > /dev/null
  echo "Phase 4 done."
}
status() {
  python3 - <<'EOF'
import json, glob, collections
s = collections.Counter(); m = collections.Counter()
for f in glob.glob('output/study_v3/solver_runs/*.json'):
    r = json.load(open(f)); s[(r['run_id'].rsplit('__', 1)[-1], r.get('status'))] += 1
for f in glob.glob('output/study_v3/judge_runs/*__sel*__*.json'):
    m[json.load(open(f)).get('status')] += 1
led = json.load(open('output/study_v3/judge_ledger.json')) if glob.glob('output/study_v3/judge_ledger.json') else []
print('solver runs:', dict(s)); print('judge runs:', dict(m)); print('judge spend so far: $%.2f' % sum(x.get('actual_cost_usd') or 0 for x in led))
EOF
}
case "${1:-}" in
  1) phase1 2>&1 | tee -a "$LOG/phase1.log" ;;
  2) phase2 2>&1 | tee -a "$LOG/phase2.log" ;;
  3) phase3 2>&1 | tee -a "$LOG/phase3.log" ;;
  4) phase4 2>&1 | tee -a "$LOG/phase4.log" ;;
  all) need_key; { phase1 && phase2 && phase3; } 2>&1 | tee -a "$LOG/all.log" ;;
  status) status ;;
  *) sed -n 2,10p "$0" ;;
esac
