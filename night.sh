#!/bin/bash
# Study v3.1 overnight runner. Every phase is resumable: re-running a phase skips finished work.
#   Judge phases (2, 3, 4, all) ask for your OpenRouter key at the start, hidden; it is kept in memory only.
#   (If OPENROUTER_API_KEY is already exported and valid, it is used without asking.)
#   bash night.sh 1     fetch references, prepare, solve r1 (Sonnet + Opus), freeze the random sample, write blind packets
#   bash night.sh 2     judge r1 (both judges), pairwise preference on all r1 pairs, report
#   bash night.sh 3     solve r2 repeats, judge r2, report
#   bash night.sh 2lean like 2, but Sol grades only the 22-output human sample (about $20 instead of $37)
#   bash night.sh 3g    grade r2 repeats with Gemini only; stops after $35 spent in this run; never regrades
#   bash night.sh solve2  solve r2 repeats only (no key needed; safe to run while phase 2 judges)
#   bash night.sh 4     full-rubric check on human-confirmed errors (after you have recorded labels)
#   bash night.sh all   1 then 2 then 3
#   bash night.sh key   only check that the key you paste is accepted
#   bash night.sh pack  zip every v3.1 result (no keys, no references) into output/delivery/v31_results.zip
# Logs: output/study_v3/logs/phase<N>.log. Keeps the Mac awake while running.
set -uo pipefail
cd "$(dirname "$0")"
export STUDY_CONFIG=config/study_v31.json STUDY_V3_TIMEOUT=3600
LOG=output/study_v3/logs; mkdir -p "$LOG"
WAKE=""; command -v caffeinate >/dev/null && WAKE="caffeinate -dims"
clean_key() {  # strip spaces, newlines and surrounding quotes a paste can carry
  local k="${1//[$' \t\r\n']/}"; k="${k#\"}"; k="${k%\"}"; k="${k#\'}"; k="${k%\'}"; printf '%s' "$k"
}
valid_key() {  # no regex bounds: macOS bash caps {m,n} at 255, so {32,256} silently never matched there
  local LC_ALL=C k="$1"
  [ ${#k} -ge 32 ] && [ ${#k} -le 256 ] || return 1
  case "$k" in *[!A-Za-z0-9_-]*) return 1 ;; esac
}
why_not() {  # describe a rejected key without printing it
  local LC_ALL=C k="$1" bad; bad="${k//[A-Za-z0-9_-]/}"
  printf '%s bytes, starts with %s, %s character(s) that are not letters, digits, - or _' "${#k}" "'${k:0:6}'" "${#bad}"
}
ask_key() {  # asks once per run, hidden; the key lives only in this process's memory, never on disk or in logs
  local k; k="$(clean_key "${OPENROUTER_API_KEY:-}")"
  if valid_key "$k"; then export OPENROUTER_API_KEY="$k"; return 0; fi
  [ -n "${OPENROUTER_API_KEY:-}" ] && echo "OPENROUTER_API_KEY in this terminal was rejected ($(why_not "$k")); asking instead."
  for i in 1 2 3; do
    if ! { IFS= read -rs -p "OpenRouter API key (hidden, not saved): " k </dev/tty 2>/dev/tty; } 2>/dev/null; then IFS= read -rs k || true; fi
    echo; k="$(clean_key "$k")"
    if valid_key "$k"; then export OPENROUTER_API_KEY="$k"; echo "Key accepted (${#k} characters)."; return 0; fi
    echo "Rejected: $(why_not "$k"). A key looks like sk-or-v1- followed by 64 letters and digits. Try again."
  done
  echo "No valid key after 3 tries; nothing was run."; exit 2
}
need_key() { valid_key "${OPENROUTER_API_KEY:-}" || { echo "No valid key in this process (run through bash night.sh, which asks for it)."; exit 2; }; }
run() { echo; echo ">>> $*"; $WAKE "$@"; }
stop() { echo; echo "STOPPED: $1 (finished work is kept; fix and re-run the same phase)"; return 1; }
solve_r() {  # $1 = repeat; exit 3 means the Claude Code usage limit was reached
  run python3 scripts/study_v3_pipeline.py solve --models sonnet opus --workers 3 --repeat "$1"; local rc=$?
  [ $rc -eq 3 ] && { stop "Claude Code usage limit reached; re-run after it resets"; return 1; }
  [ $rc -eq 0 ] || { stop "solver pass failed (exit $rc)"; return 1; }
  run python3 scripts/study_v3_pipeline.py solve --models sonnet opus --workers 2 --repeat "$1"; rc=$?   # retries no-output runs once
  [ $rc -eq 3 ] && { stop "Claude Code usage limit reached on the retry pass; re-run after it resets"; return 1; }
  return 0
}

judge_r() {  # $1 = cumulative spend guard, $2 = repeat. Exit 5 = OpenRouter 402 (credits / key limit), 4 = >20% of calls failed
  local CREDIT_MSG="OpenRouter says out of credits or the key hit its limit (HTTP 402). Add credits at openrouter.ai/settings/credits and raise or remove this key's limit at openrouter.ai/settings/keys, then re-run this phase"
  run python3 scripts/study_v3_pipeline.py judge --max-usd "$1" --workers "${JW:-1}" --repeat "$2"; local rc=$?
  [ $rc -eq 5 ] && { stop "$CREDIT_MSG"; return 1; }
  [ $rc -eq 0 ] || [ $rc -eq 4 ] || { stop "rubric judge crashed (exit $rc)"; return 1; }
  run python3 scripts/study_v3_pipeline.py judge --max-usd "$1" --workers 1 --repeat "$2"; rc=$?   # retries execution errors
  [ $rc -eq 5 ] && { stop "$CREDIT_MSG"; return 1; }
  [ $rc -eq 4 ] && { stop "more than 20% of rubric judge calls failed twice (errors above)"; return 1; }
  [ $rc -eq 0 ] || { stop "rubric judge crashed (exit $rc)"; return 1; }
  return 0
}
phase1() {
  run python3 scripts/fetch_references_v31.py || { echo "reference download failed; fix and re-run phase 1"; return 1; }
  run python3 scripts/study_v3_pipeline.py prepare || { stop "prepare failed"; return 1; }
  solve_r 1 || return 1
  [ -f output/study_v3/calibration_set_v31.json ] || run python3 scripts/human_review_kit.py select-random
  run python3 scripts/human_review_kit.py packets-random
  run python3 scripts/human_review_kit.py packets-hist-sol
  echo; echo "Phase 1 done. Blind packets: output/study_v3/review_v31/ (22) and output/study_v3/review_hist_sol/ (5). Do not open judge_runs/ until they are labeled."
}
phase2() {
  need_key
  judge_r 65 1 || return 1
  run python3 scripts/pairwise_grader_16.py build || { stop "pair build failed"; return 1; }
  run python3 scripts/pairwise_grader_16.py judge --max-usd 20 --workers 1 || { stop "preference judging stopped (402 = credits / key limit; see above)"; return 1; }
  run python3 scripts/pairwise_grader_16.py report > /dev/null
  run python3 scripts/study_v3_pipeline.py report > /dev/null
  echo "Phase 2 done."
}
phase3() {
  need_key
  solve_r 2 || return 1
  judge_r 135 2 || return 1
  run python3 scripts/study_v3_pipeline.py report > /dev/null
  echo "Phase 3 done."
}
phase4() {
  need_key
  run python3 scripts/full_rubric_17.py judge --max-usd 30 --workers 2 || { stop "full-rubric judging stopped (402 = credits / key limit; see above)"; return 1; }
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
pack() {
  rm -f output/delivery/v31_results.zip
  zip -qr output/delivery/v31_results.zip \
    output/study_v3/solver_runs output/study_v3/judge_runs output/study_v3/judge_ledger.json output/study_v3/report.json \
    output/study_v3/prepare_summary_v31.json output/study_v3/calibration_set_v31.json output/study_v3/human_reviews_v3*.json output/study_v3/human_reviews_hist_sol.json \
    output/pairwise_grader_16/report.json output/pairwise_grader_16/ledger.json output/pairwise_grader_16/manifest.json output/pairwise_grader_16/runs \
    output/full_rubric_17 data/study_v3/instances data/study_v3/requirements research/reference_manifest_v31.json output/study_v3/logs \
    -x '*/judge_packets/*' -x '*.DS_Store' 2>/dev/null
  find output/study_v3/claudecode -path '*/outputs/*' -type f -print | zip -q output/delivery/v31_results.zip -@
  ls -la output/delivery/v31_results.zip
}
case "${1:-}" in
  1) phase1 2>&1 | tee -a "$LOG/phase1.log" ;;
  2) ask_key; phase2 2>&1 | tee -a "$LOG/phase2.log" ;;
  3) ask_key; phase3 2>&1 | tee -a "$LOG/phase3.log" ;;
  4) ask_key; phase4 2>&1 | tee -a "$LOG/phase4.log" ;;
  key) ask_key; echo "Key check passed. Nothing else was run." ;;
  solve2) { solve_r 2 && echo "r2 solving done."; } 2>&1 | tee -a "$LOG/solve2.log" ;;
  2lean) ask_key; { need_key; run python3 scripts/study_v3_pipeline.py judge --max-usd 65 --workers 1 --repeat 1 --sample-only-for sol && run python3 scripts/pairwise_grader_16.py build && run python3 scripts/pairwise_grader_16.py judge --max-usd 20 --workers 1 && run python3 scripts/pairwise_grader_16.py report > /dev/null && run python3 scripts/study_v3_pipeline.py report > /dev/null && echo "Lean phase 2 done: Gemini on every r1 output, Sol on the 22-output human sample, preference on all pairs."; } 2>&1 | tee -a "$LOG/phase2lean.log" ;;
  3g) ask_key; { need_key; run python3 scripts/study_v3_pipeline.py judge --max-usd 999 --max-pass-usd 35 --workers 1 --repeat 2 --judges gemini && run python3 scripts/study_v3_pipeline.py report > /dev/null && echo "r2 graded by Gemini only."; } 2>&1 | tee -a "$LOG/phase3g.log" ;;
  all) ask_key; { phase1 && phase2 && phase3; } 2>&1 | tee -a "$LOG/all.log" ;;
  status) status ;;
  pack) pack ;;
  *) sed -n 2,10p "$0" ;;
esac
