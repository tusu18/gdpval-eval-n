# Right facts, wrong plan — a GDPval evaluation for the Turing field-engineer take-home

**Live site:** https://tusu18.github.io/gdpval-eval-n/ · **Pitch page:** https://tusu18.github.io/gdpval-eval-n/pitch.html · Author: Tushar Singh

Three frontier models (Claude Sonnet 5.5, Claude Opus 5.5, GPT-6.1 Sol) on all 15 GDPval gold tasks in three occupations. Every parseable deliverable passed fact checks; 4 of 8 outputs read in full carry a consequential error in the clause or table someone acts on. Fact-level grading cannot see this. A dataset that grades the finished document can.

Every number on the site is asserted by a test against one file, `output/results.json`, which `scripts/build_results.py` rebuilds from the run records in this repo:

```sh
python3 scripts/consolidate_human_reviews.py && python3 scripts/build_results.py && python3 -m pytest tests/test_site_numbers.py -q
```

## Layout

| Path | Contents |
|---|---|
| `docs/` | The site as served by GitHub Pages: `index.html` (findings, charts, pilot calculator), `pitch.html` (two lab pitches + hard Q&A), `results.json`. |
| `scripts/` | Run, grading, analysis and review tooling. Entry points below. |
| `config/` | Frozen run configs, including every budget amendment. |
| `tests/` | Grader, validator, transport and site-consistency tests. |
| `data/` | GDPval slice metadata (revision `11e7900`, selection rule fixed before outcomes), study-v3 instances and rubrics, construct-validity edits with reviewer confirmations. |
| `output/study_v3/` | Follow-up run (28/28 delivered): solver runs, judge runs, ledger, every delivered file under `claudecode/<run>/outputs`, blind review packets, human labels. |
| `output/judge_robustness_10/` | 144-call judge diagnostics: rewordings, authored controls, injection, cross-family. |
| `output/construct_validity_15/` | Planted-error test: 40 judge runs, report, reviewer-confirmed edits. |
| `output/pairwise_grader_16/` | GDPval-style pairwise preference judge vs rubric v2 on the same 14 pairs: 56 runs, report. |
| `output/paired_v1/`, `output/assignment_final/`, `output/submission_audit/` | Historical 60-attempt study: scores, primary/secondary judgments, evidence record, triage key. |
| `reviews/assignment_final/` | The five historical blind human reviews, imported by hash. |
| `output/human_reviews_all.json` | All 8 full-output human reviews, both studies side by side, never pooled. |

## Entry points

```sh
# follow-up run: Claude Code CLI as solver, OpenRouter judges (key via env var or getpass; never stored)
python3 scripts/study_v3_pipeline.py prepare
python3 scripts/study_v3_pipeline.py solve --models sonnet opus            # --repeat 2 for a second independent attempt
python3 scripts/study_v3_pipeline.py judge --max-usd 10
python3 scripts/study_v3_pipeline.py report

# rubric v2 grader: stated + honored per requirement, severity 1-5, locator-tolerant quote validator
python3 scripts/evidence_grader_v2.py <packet.json> <judgment.json>

# construct validity (break / paraphrase edits on judge-passed requirements; edits human-confirmed before results are read)
python3 scripts/construct_validity_15.py build && python3 scripts/construct_validity_15.py judge --max-usd 12 --workers 1 && python3 scripts/construct_validity_15.py report

# GDPval-style pairwise preference judge vs rubric v2
python3 scripts/pairwise_grader_16.py build && python3 scripts/pairwise_grader_16.py judge --max-usd 16 --workers 1 && python3 scripts/pairwise_grader_16.py report

# blind human review kit: frozen stratified sample, packets without judge text, label recording, second-reviewer kappa
python3 scripts/human_review_kit.py select && python3 scripts/human_review_kit.py packets
python3 scripts/human_review_kit.py kappa --a output/study_v3/human_reviews_v3.json --b output/study_v3/human_reviews_v3_<reviewer>.json

# judge robustness batch and historical evidence record
python3 scripts/run_judge_robustness_10.py && python3 scripts/analyze_judge_robustness_10.py
python3 scripts/assignment_evidence.py
python3 -m pytest tests -q
```

## How grading works

1. Mechanical checks on a structured audit record and workbook values; rendered page counts.
2. Rubric v2: for each requirement a **stated** check and an **honored** check across every operative section, severity 1–5, exact quotes verified by `validate_judgment`. Consequential = honored fail on a critical requirement or severity ≥ 4. No weighted score.
3. Judges Gemini 4 Argon and GPT-6.1 Sol. In the follow-up run neither shares a family with a solver; in the historical run Sol was both a solver and the primary judge, which is why the self-preference check exists. Reported per judge, any-judge and all-judges; never AND-combined.
4. Blind human review: verdict before any judge text. 8 full-output reviews, 4 consequential errors confirmed, one reviewer.
5. Grader validation: 0 verdict changes in 43 strictly comparable rewordings; 0 of 7 injection pairs flipped; 7/7 reviewer-confirmed planted violations caught by Gemini with 0 collateral under paraphrase (Sol 5/6, 6 collateral); a GDPval-style preference judge on the same pairs prefers the leaderboard winner 12/14 and prefers the human-confirmed consequential error.

Author labels, prior judge labels and human labels never enter a judge request. No API keys are stored in this repo.

## Cost

| Stage | USD |
|---|---|
| Historical study + native harness + judge robustness (144 calls) | 44.16 |
| Follow-up run: Claude Code solvers (CLI-reported) | 16.26 |
| Follow-up run: judging | 17.43 |
| Construct-validity test (40 calls) | 7.20 |
| Pairwise preference comparison (56 calls) | 3.15 |
| **Total API** | **88.20** |

Not included: 38 unresolved charge records in the historical stages (5 in the robustness batch) and human review time (5–8 min per full-output label, unmetered).

## Limits, up front

One reviewer; purposive sample, counts not rates; grader sensitivity to planted errors shown, false-accept rate on real errors still rests on 2-of-2 / 0-of-2; 10 of 27–66 rubric items judged per output; strict quote validity 7/28 and 10/28; two harnesses not pooled; no training run; OpenAI's hosted GDPval grader was read-only (deprecated) when this was built, so its form was reproduced locally rather than called. Pairwise and construct-validity packets are not committed (large, reproducible with each script's `build`).
