# GDPval-n: Seen, not scored

**Live site:** https://tusu18.github.io/gdpval-eval-n/ · **Methods:** https://tusu18.github.io/gdpval-eval-n/methods.html · **First stage:** https://tusu18.github.io/gdpval-eval-n/first-stage.html · Author: Tushar Singh

ClClaude Sonnet 5.5 and Claude Opus 5.5 on 30 GDPval gold tasks in six occupations, two attempts each (132 of 132 delivered). A pre-registered random sample of 22 outputs, frozen before this run's grading and checked against the source files: 7 carry a consequential error (95% CI 16–53%), 6 of them in the approval-heavy occupations. Read over the whole judgment, the GPT-6.1 judge names 5 of the 7 (95% CI 36–92%), but only 1 in a failed requirement; the other 4 appear only in its overall task verdict, with no requirement and no severity. The Gemini judge names 1. None of the 7 reaches severity 4 with either judge; under the grader's pre-registered rule (critical requirement or severity ≥ 4) the GPT-6.1 judge flags 5 of the 7 documents but also 7 of the 15 outputs where the review found no consequential error; at any failure it fails 12 of those 15, Gemini 9. The gap a dataset can close is the error tied to a requirement: a located, severity-graded label per failed requirement, with flags on outputs with no consequential error identified measured as carefully as misses. Labels were drafted by an AI reviewer from blind packets (outputs cut at 80,000 characters; 9 of 22 are longer) and checked by the author; one reviewer, no agreement statistic. A first stage (15 tasks, three models including GPT-6.1 as a solver, 60 + 28 attempts) has its own page. Judge flags on outputs with no consequential error identified on the 15 outputs where the review found no consequential error are classified too: 48 failed requirements, 21 of them one workbook's cost classification, 13 format literalism, 4 rubric defects.Every number on the site is asserted by a test against one file, `output/results.json`, which `scripts/build_results.py` rebuilds from the run records in this repo:

```sh
python3 scripts/consolidate_human_reviews.py && python3 scripts/build_results.py && python3 scripts/build_site.py && python3 -m pytest tests -q
# or, from a night.sh results pack:  bash scripts/ingest_v31.sh v31_results.zip
```

## Layout

| Path | Contents |
|---|---|
| `docs/` | The site as served by GitHub Pages: `index.html` (abstract, three decision rules, every confirmed error with what each judge flagged on it, flags on outputs with no consequential error identified classified, every-task drill-down, gaps, dataset record and training hypotheses), `first-stage.html` (the earlier 15-task study and its grader validation), `methods.html` (prompts and rules, generated from the code), `results.json`, `study_v31_plan.md` (pre-registration + deviations). The live pitch is delivered on the call, not on the site. |
| `site_src/` | The v3.1 page sections and their script; `scripts/build_site.py` splices them in with an embedded copy of `results.json`. Also `error_summaries_v31.json` (plain-language line per confirmed error), `judge_match_v31.json` (does the judge's failed requirement name the reviewer's error), `judge_locate_v31.json` (where in the whole judgment the judge names it), `honesty_flags_v31.json` (errors that misreport what was done or known) and `false_alarm_classes_v31.json` (why each judge false alarm happened), all AI-drafted site copy marked with whether the author has confirmed them. |
| `night.sh` | The v3.1 runner: solve, grade, preference, full-rubric, pack. Asks for the OpenRouter key at run time; never stores it. |
| `scripts/` | Run, grading, analysis and review tooling. Entry points below. |
| `config/` | Frozen run configs, including every budget amendment. |
| `tests/` | Grader, validator, transport and site-consistency tests. |
| `data/` | GDPval slice metadata (revision `11e7900`, selection rule fixed before outcomes), study-v3 instances and rubrics, construct-validity edits with reviewer confirmations. |
| `output/study_v3/` | Follow-up and v3.1 runs (28/28 and 132/132 delivered): solver runs, judge runs, ledger, every delivered file under `claudecode/<run>/outputs`, the frozen random sample, labels with provenance. |
| `output/full_rubric_17/` | Full-rubric check on confirmed errors: what the 10-requirement cap hides. |
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

## Cost (this version)

| Item | USD |
|---|---|
| Rubric grading (OpenRouter) | 31.38 |
| Preference judging (OpenRouter) | 8.81 |
| Full-rubric check (OpenRouter) | 11.38 |
| OpenRouter credits | 51.57 |
| Claude Code subscription usage for solving (reported by the CLI; not billed per call) | 98.16 |
| **All-in, this version** | **149.73** |

Review time: about 3 hours to check the 27 v3.1 labels.

## Limits, up front

v3.1 labels were drafted by an AI reviewer from blind packets and checked by the author against each packet (27/27 confirmed unchanged); one reviewer, no kappa; the drafting model is from the same developer as the Sol judge. The random sample was frozen before v3.1 grading, not before all grading: 7 of 22 outputs had follow-up judge files on disk (never opened by the reviewer); 5 of the 7 confirmed errors are among them. The judge-versus-reviewer comparison (same / related / different) was drafted by an AI assistant and is marked on the page until the author confirms it. 22-output sample, so rates have wide intervals. Sol graded only the random-sample outputs on the new tasks; 16 of 53 new grades saw a partial view of a data-dump output; none of the new grades passes the strict evidence check (the prompt's output format omits the locator field); repeats were produced but not graded. First stage: one reviewer, purposive sample, counts not rates; two harnesses not pooled; no training run. OpenAI's hosted GDPval grader was read-only when this was built, so its form was reproduced locally. Judge and full-rubric packets are not committed (large, reproducible).
