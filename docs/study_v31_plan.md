# Study v3.1 — pre-registered extension to 30 tasks

Registered before any v3.1 output existed. Machine-readable version: `config/study_v31.json`. Selection is mechanical: `scripts/select_slice_v31.py` → `data/gdpval_v31/selection_report.json`.

## Why

The first 15 tasks produced four claims: the documents state rules correctly and break them in operative sections; one judge (Sol) flags a strict superset of the other (Gemini); a preference judge prefers the higher-severity output where rubric severity differs; and Gemini passes human-confirmed errors that Sol catches. All four were formed on the same 15 tasks they were measured on. v3.1 tests them on 15 tasks the claims never saw, with every instrument unchanged.

## Slice (30 tasks, 6 occupations)

| Occupation | Sector | Why it is in |
|---|---|---|
| Buyers and Purchasing Agents | Manufacturing | original slice |
| Project Management Specialists | Professional, Scientific, Technical | original slice |
| Shipping, Receiving, and Inventory Clerks | Manufacturing | original slice |
| First-Line Supervisors of Production and Operating Workers | Manufacturing | 5/5 gold deliverables native Word/Excel |
| Order Clerks | Wholesale Trade | 5/5 gold deliverables native Word/Excel |
| Accountants and Auditors | Professional, Scientific, Technical | 4/5; only 4/5 occupation sharing a sector with the original slice |

The four tasks v3 skipped now run: two PowerPoint tasks (tier P) and two that require live web research (tier W, reported separately because no pinned source exists for the judge).

## Predictions (each reported whether it holds or fails)

- **P1** The failure class replicates: at least one human-confirmed consequential error in the 15 new tasks sits in an operative section of a deliverable that states the governing rule or figure correctly elsewhere.
- **P2** Strictness ordering holds: on the new tasks, Gemini-only flagged outputs ≤ 2.
- **P3** Preference and rubric disagree: in at least one new pair where rubric severity differs, the preference judge picks the higher-severity output.
- **P4** Gemini passes at least as many human-confirmed errors as Sol in the random sample.
- **P5** Preference judges prefer Opus in a majority of new pairs (what preference measures, not quality).

## Human review

- **Random sample:** 22 outputs from all 30 tasks × 2 solvers, stratified by occupation, seed 20261106, frozen right after solving and before any v3.1 judge result is opened. Packets contain request, sources and full output text only. Gives a prevalence estimate with a Wilson interval and judge sensitivity/specificity on a random sample.
- **Confound check:** the 5 unreviewed historical GPT-6.1 Sol outputs in the two families where Claude errors were confirmed. Tests whether "all 11 behaviour failures are Claude" reflects the Sol judge or the solver.
- **Second reviewer:** same kit; κ reported if done, stated as a limit if not.

## Unchanged instruments

Solver harness, flags and tier-A prompt byte-identical; judge prompt, requirement selection (cap 10), models and settings identical. Changes are limited to: tier P/W/D prompt sentences, pptx/pdf text extraction, a 240k-character reference budget per packet (no v3 packet exceeded it), and validator locators for the two new formats.

## Order of work

`night.sh 1` fetch, prepare, solve r1, freeze sample, write packets → label while `night.sh 2` judges and runs the preference comparison → `night.sh 3` repeats → `night.sh 4` full-rubric check on confirmed errors. Cumulative judge guards: $65 (r1), $135 (r2); pairwise $20; full rubric $30.

## Stop rules

No change to the tier-A prompt, judge prompt or requirement selection after any v3.1 output exists. Transport failures above 20% stop the run. The sample is frozen before judging. Every outcome is reported.
