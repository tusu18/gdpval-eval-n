"""Every number printed on the findings page must come from output/results.json.

Run:  python3 -m pytest tests/test_site_numbers.py -q
Rebuild results first with scripts/build_results.py. Each check names the figure and the exact string the page must contain.
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = json.loads((ROOT / 'output/results.json').read_text())
_cands = [ROOT / 'docs/index.html', ROOT / 'site/findings/index.html']
PAGE = next(p for p in _cands if p.exists()).read_text(encoding='utf-8')


def checks():
    h, f, cv, hu, c, r = RES['historical'], RES['follow_up'], RES['construct_validity'], RES['human_reviews'], RES['cost_usd'], RES['judge_robustness']
    g, s, a = f['per_judge']['gemini'], f['per_judge']['sol'], f['agreement']
    tax = h['failure_taxonomy']; cat = tax['categories']
    pj = h['primary_judge_critical']; m = h['secondary_matrix_critical']
    cg, cs = cv['per_judge']['gemini'], cv['per_judge']['sol']
    yield 'fact checks card', f"{h['fact_checks']['decision_pass']} / {h['parseable_outputs']}"
    yield 'setup share card', f"{tax['setup']} / {tax['total']}"
    yield 'shared severity-4 card', f"{a['shared_severity_4']} / {a['shared']}"
    yield 'byline attempts', f"{h['attempts']} + {f['episodes']} attempts"
    yield 'byline reviews', f"{hu['reviewed']} human reviews"
    yield 'byline spend', f"${c['total']:.2f} OpenRouter credits"
    yield 'cost row', f"<span class=\"mono\">${c['rubric_grading']:.2f}</span> rubric grading + <span class=\"mono\">${c['preference_judging']:.2f}</span> preference judging + <span class=\"mono\">${c['full_rubric_check']:.2f}</span> full-rubric check"
    yield 'human reviews with errors', f"Of {hu['reviewed']} outputs reviewed in full, {hu['consequential_errors']} carry"
    yield 'gemini legend', f"Gemini 4 Argon, {g['outputs']} outputs"
    yield 'sol legend', f"GPT-6.1 Sol, {s['outputs']} outputs"
    yield 'gemini chart data', f"n:{g['outputs']},v:[{g['clean']},{g['any_honored_failure']},{g['severity_4']}]"
    yield 'sol chart data', f"n:{s['outputs']},v:[{s['clean']},{s['any_honored_failure']},{s['severity_4']}]"
    yield 'gemini table row', f"<td class=\"n\">{g['outputs']}</td><td class=\"n\">{g['clean']}</td><td class=\"n\">{g['any_honored_failure']}</td><td class=\"n\">{g['severity_4']}</td><td class=\"n\">{g['stated_not_honored_requirements']}</td>"
    yield 'sol table row', f"<td class=\"n\">{s['outputs']}</td><td class=\"n\">{s['clean']}</td><td class=\"n\">{s['any_honored_failure']}</td><td class=\"n\">{s['severity_4']}</td><td class=\"n\">{s['stated_not_honored_requirements']}</td>"
    yield 'agreement chart data', f"[['Both judges failed it',{a['both_fail']}],['Sol only',{a['sol_only']}],['Gemini only',{a['gemini_only']}],['Neither',{a['neither']}]]"
    yield 'agreement title', f"on the {a['shared']} outputs both judges graded"
    yield 'strict validity', f"strict quote validity {g['strict_evidence_valid']}/{g['outputs']} (Gemini) and {s['strict_evidence_valid']}/{s['outputs']} (Sol)"
    yield 'episodes', f"<b>{f['episodes']} episodes</b>, {f['submitted']} delivered"
    yield 'taxonomy filter model', f"Model behavior, {tax['model_behavior']}"
    yield 'taxonomy filter setup', f"Task or harness, {tax['setup']}"
    yield 'taxonomy solver split', f"all {tax['model_behavior_by_solver']['sonnet']} model-behavior failures are Claude Sonnet outputs"
    for cid, label in (('unsupported_continuity', 'Plan asserts unsupported resources'), ('approval_bypass', 'Exception weakens a mandatory approval'), ('unsupported_eligibility', 'Unverified eligibility stated as settled'),
                       ('missing_comparison', 'Requested comparison incomplete'), ('contract_ambiguity', 'Deliverable contract conflicts with reference'), ('page_overflow', 'Rendered document over the page limit'), ('final_answer', 'Final answer not parseable')):
        k = 'invalid_serialization' if cid == 'final_answer' else cid
        yield f'taxonomy row {k}', f"<td>{label}</td><td class=\"n\">{cat[k]['total']}</td><td class=\"n small\">{cat[k]['sonnet']} / {cat[k]['sol']}</td>"
    yield 'continuity one task', f"{cat['unsupported_continuity']['total']} of the {tax['model_behavior']} model-behavior failures are one task"
    yield 'self-preference', f"Sol flagged {pj['sonnet'][0]} of {pj['sonnet'][1]} Claude outputs and {pj['sol'][0]} of {pj['sol'][1]} of its own (Fisher p = {pj['fisher_two_sided_p']:.4f})"
    yield 'rewording pairs', f"0 verdict changes in {r['rewording_pairs_comparable_strict']} strictly comparable paired rewordings" if r['rewording_pairs_changed'] == 0 else f"{r['rewording_pairs_changed']} verdict changes in {r['rewording_pairs_comparable_strict']}"
    yield 'injection', f"{r['injection_changed']} of {r['injection_pairs_comparable']} comparable injection pairs flipped"
    yield 'cv gemini', f"Gemini: {cg['break_flipped']}/{cg['break_pairs']} breaks flipped to honored-fail, {cg['paraphrase_stable']}/{cg['paraphrase_pairs']} paraphrases stayed pass, {cg['collateral_paraphrase']} collateral changes under paraphrase"
    yield 'cv sol', f"Sol: {cs['break_flipped']}/{cs['break_pairs']} flipped ({cs['break_uncertain']} uncertain), {cs['paraphrase_stable']}/{cs['paraphrase_pairs']} stayed pass, {cs['collateral_paraphrase']} collateral changes under paraphrase"
    yield 'cv confirmed', f"the reviewer confirmed {cv['edits_confirmed']} breaks as real violations and excluded {len(cv['edits_excluded'])}"
    pw = RES.get('pairwise_preference')
    if pw:
        pg, ps = pw['per_judge']['gemini'], pw['per_judge']['sol']
        yield 'pairwise preference', f"(Gemini {pg['prefers_opus']}/{pw['pairs']}, Sol {ps['prefers_opus']}/{pw['pairs']})"
        yield 'pairwise contradicts rubric', f"contradicted Sol's rubric verdict in {ps['contradicts_rubric']} of {ps['severity_differs']} pairs"
        yield 'pairwise position', f"Position consistency: Sol {ps['position_consistent']}/{pw['pairs']}, Gemini {pg['position_consistent']}/{pw['pairs']}"
    yield 'secondary matrix', f"agree on {m['neither'] + m['both']} of {m['double_graded']}"


def test_every_number_matches_results():
    missing = [(name, s) for name, s in checks() if s not in PAGE]
    assert not missing, 'page figures not matching results.json:\n' + '\n'.join(f'  {n}: {s!r}' for n, s in missing)


def test_results_internal_consistency():
    f = RES['follow_up']; a = f['agreement']; tax = RES['historical']['failure_taxonomy']
    assert a['both_fail'] + a['sol_only'] + a['gemini_only'] + a['neither'] == a['shared']
    for j, v in f['per_judge'].items(): assert v['clean'] + v['any_honored_failure'] == v['outputs'], j
    assert tax['model_behavior'] + tax['setup'] == tax['total']
    assert sum(v['total'] for v in tax['categories'].values()) == tax['total']
    assert abs(sum(v for k, v in RES['cost_usd'].items() if k != 'total') - RES['cost_usd']['total']) < 0.011


def test_embedded_site_data_is_results_json():
    """The page renders the v3.1 sections from an embedded copy of results.json; it must be the current one."""
    page = (ROOT / 'docs/index.html').read_text(encoding='utf-8')
    m = re.search(r'<script type="application/json" id="site-data">(.*?)</script>', page, re.S)
    assert m, 'site-data block missing: run scripts/build_site.py'
    assert json.loads(m.group(1).replace('<\\/', '</')) == RES, 'embedded data is stale: run scripts/build_site.py'
    assert json.loads((ROOT / 'docs/results.json').read_text()) == RES, 'docs/results.json is stale: run scripts/build_site.py'


def test_methods_page_is_current():
    """methods.html quotes prompts and rules from the code; regenerate it when the code changes."""
    import build_methods
    assert (ROOT / 'docs/methods.html').read_text() == build_methods.page(), 'methods.html is stale: run scripts/build_methods.py'


def test_v31_cost_total_not_double_counted():
    import json, pathlib
    c = json.loads(pathlib.Path(__file__).resolve().parents[1].joinpath('output/results.json').read_text())['v31']['cost_usd']
    parts = c['judging_new'] + c['pairwise_new'] + c['full_rubric'] + c['claude_code_r1_new'] + c['claude_code_r2']
    assert abs(c['total'] - parts) < 0.02
    assert abs(c['openrouter_credits_this_version'] - (c['judging_new'] + c['pairwise_new'] + c['full_rubric'])) < 0.02


def test_dataset_evidence_tags_match_results():
    v = RES['v31']; rs = v['random_sample']; j = v['judge_vs_human']['random_sample']; rows = v['hand_taxonomy']['rows']
    n = rs['consequential_yes']; neg = j['any_fail']['sol']['fp'] + j['any_fail']['sol']['tn']
    stated = sum(1 for r in rows if r['in_random_sample'] and r['stated_elsewhere'] == 'yes')
    stated_r = sum(1 for r in rows if r['in_R'] and r['stated_elsewhere'] == 'yes')
    tax = RES['historical']['failure_taxonomy']
    hr = json.loads((ROOT / 'output/human_reviews_all.json').read_text()); hr = hr if isinstance(hr, list) else hr.get('reviews') or hr.get('rows')
    hist = [r['run_id'].split('__')[1] for r in hr if r['study'] == 'historical' and r['consequential_error'] == 'yes']
    clab = [r for r in hr if any(r['run_id'].startswith(c + '__') for c in v['set_members']['C'])]
    want = [f"{j['sev4']['sol']['tp']} of {n} at severity 4, both judges" if j['sev4']['sol']['tp'] == j['sev4']['gemini']['tp'] else None,
            f"v3.1: {stated} of {n} confirmed errors state the rule correctly elsewhere",
            f"All {len(hist)} first-stage confirmed errors came from the conflicting ({hist.count('conflict')}) or recoverable-gap ({hist.count('recovery')}) conditions",
            f"conflict variants: {len(clab)} output labeled, {'no error' if all(r['consequential_error'] == 'no' for r in clab) else 'error'}",
            f"Sol fails {j['any_fail']['sol']['fp']} of the {neg} outputs with no consequential error, Gemini {j['any_fail']['gemini']['fp']} of {neg}",
            f"task defect on {rs['task_defect_yes']} of {rs['selected']} sampled outputs",
            f"{tax['setup']} of {tax['total']} machine-sorted failures were setup"]
    assert None not in want and stated_r == 0 and len(hist) == hist.count('conflict') + hist.count('recovery') and not v['predictions']['P1']['holds']
    missing = [w for w in want if w not in PAGE]
    assert not missing, missing


def test_every_confirmed_error_has_a_plain_line():
    rows = RES['v31']['hand_taxonomy']['rows']
    assert rows and all(r.get('plain') for r in rows), [r['run_id'] for r in rows if not r.get('plain')]
    notes = {r['run_id']: r.get('reviewer_note') or '' for r in json.loads((ROOT / 'output/study_v3/human_reviews_v3.json').read_text())['reviews']}
    for r in rows:  # every figure in a plain line must appear in the reviewer note it paraphrases
        for num in re.findall(r'\d+(?:\.\d+)?', r['plain']):
            assert num in notes[r['run_id']] or num in (r.get('location') or ''), (r['run_id'], num)


def v31_checks():
    """Every v3.1 figure printed in the hand-written parts of the page (hero, abstract, findings, Part 3)."""
    v = RES['v31']; rs = v['random_sample']; j = v['judge_vs_human']['random_sample']; c = RES['cost_usd']; loc = v['hand_taxonomy']['located']
    n = rs['consequential_yes']; neg = j['any_fail']['sol']['fp'] + j['any_fail']['sol']['tn']; ci = [round(x * 100) for x in rs['wilson95']]
    by = rs['by_occupation']; old = [by['Buyers and Purchasing Agents'], by['Shipping, Receiving, and Inventory Clerks'], by['Project Management Specialists']]
    old_err, old_n = sum(x[0] for x in old), sum(x[1] for x in old); new_err, new_n = n - old_err, rs['labeled'] - old_n
    preds = sum(1 for p in v['predictions'].values() if p['holds'] is True); same = loc['sol']['same']
    assert same == loc['gemini']['same'] and loc['sol']['related'] == loc['gemini']['related'] == 1
    yield 'kpi prevalence', f"{rs['prevalence'][0]} of {rs['prevalence'][1]}</div><div class=\"l\">random-sample deliverables carry an error someone would act on (95% CI {ci[0]}–{ci[1]}%)"
    yield 'kpi located', f"{same} of {n}</div><div class=\"l\">of those errors a judge actually located"
    yield 'kpi sev4', f"{j['sev4']['sol']['tp']} of {n}</div><div class=\"l\">reach severity 4"
    yield 'kpi false alarms', f"{j['any_fail']['sol']['fp']} of {neg}</div><div class=\"l\">deliverables without a consequential error that Sol still fails on some requirement (Gemini {j['any_fail']['gemini']['fp']} of {neg})"
    yield 'kpi predictions', f"{preds} of 5</div>"
    yield 'kpi cost', f"${c['total']:.2f}</div><div class=\"l\">OpenRouter credits for this version"
    yield 'abstract prevalence', f"{n} carry a consequential error ({round(100 * n / rs['labeled'])}%, 95% CI {ci[0]}–{ci[1]}%), {old_err} of them in purchasing, shipping and project work ({old_err} of {old_n}) against {new_err} of {new_n}"
    yield 'abstract any-fail', f"The judges fail those {n} documents (Sol {j['any_fail']['sol']['tp']}, Gemini {j['any_fail']['gemini']['tp']}) but name the reviewer's error in {same}"
    yield 'abstract grader rule', f"under the grader's pre-registered rule Sol flags {j['crit']['sol']['tp']} and also fails {j['crit']['sol']['fp']} of the {neg} deliverables without an error; at any failed requirement Sol fails {j['any_fail']['sol']['fp']} of {neg} and Gemini {j['any_fail']['gemini']['fp']}"
    yield 'abstract predictions', f"{preds} of 5 pre-registered predictions held"
    yield 'finding 1 solvers', f"(Sonnet {rs['by_solver']['sonnet'][0]} of {rs['by_solver']['sonnet'][1]}, Opus {rs['by_solver']['opus'][0]} of {rs['by_solver']['opus'][1]})"
    yield 'finding 2 grader rule', f"Sol catches {j['crit']['sol']['tp']} but also fails {j['crit']['sol']['fp']} of {neg} clean outputs; at any failed requirement, {j['any_fail']['sol']['tp']} and {j['any_fail']['sol']['fp']}"
    yield 'part 3 located row', f"same error {same}, related 1, different or nothing {n - same - 1}, for each judge"
    yield 'part 3 grader rule', f"under the grader's rule {j['crit']['sol']['fp']} and {j['crit']['gemini']['fp']}"
    yield 'limits freeze', "7 of the 22 outputs came from the earlier follow-up run"


def test_v31_page_figures_match_results():
    missing = [(name, s) for name, s in v31_checks() if s not in PAGE]
    assert not missing, 'v3.1 page figures not matching results.json:\n' + '\n'.join(f'  {n}: {s!r}' for n, s in missing)
    cal = json.loads((ROOT / 'output/study_v3/calibration_set_v31.json').read_text())
    assert len(cal['selected_with_existing_v3_judge_runs']) == 7 and len(cal['selected']) == 22


def test_three_decision_rules_are_consistent():
    """sev4 implies crit implies any_fail, per judge; crit on each confirmed error matches the grader's pre-registered rule."""
    v = RES['v31']
    for which in ('random_sample', 'all_follow_up_labels'):
        J = v['judge_vs_human'][which]
        for jname in ('gemini', 'sol'):
            s4, cr, af = J['sev4'][jname], J['crit'][jname], J['any_fail'][jname]
            assert s4['tp'] <= cr['tp'] <= af['tp'] and s4['fp'] <= cr['fp'] <= af['fp']
            assert s4['tp'] + s4['fn'] == cr['tp'] + cr['fn'] == af['tp'] + af['fn']
    for r in v['hand_taxonomy']['rows']:
        for jname, st in r['judges'].items():
            if st: assert st['crit'] == any(f['critical'] or f['severity'] >= 4 for f in st['fails'])
            assert (r['match'].get(jname) or {}).get('match') in ('same', 'related', 'different', 'none'), r['run_id']


def test_pitch_material_is_off_the_findings_page():
    for bad in ('pitch.html', 'h-pitch', 'The pilot I would sell', 'Why Turing', 'i-fam', 'Full pitch page', 'frozen before any grading', 'acceptable outputs Sol'):
        assert bad not in PAGE, bad
    assert not (ROOT / 'docs/pitch.html').exists()
