"""Every number printed on the findings page must come from output/results.json.

Run:  python3 -m pytest tests/test_site_numbers.py -q
Rebuild results first with scripts/build_results.py. Each check names the figure and the exact string the page must contain.
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = json.loads((ROOT / 'output/results.json').read_text())
_cands = [ROOT / 'docs/index.html', ROOT / 'site/findings/index.html']
INDEX = next(p for p in _cands if p.exists()).read_text(encoding='utf-8')
STAGE1 = (ROOT / 'docs/first-stage.html').read_text(encoding='utf-8') if (ROOT / 'docs/first-stage.html').exists() else ''
PAGE = INDEX + '\n' + STAGE1  # first-stage figures live on their own page; v3.1 figures on the findings page


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
    yield 'byline spend', f"${c['total']:.2f} credits + ${c['claude_code_subscription_usage']:.2f} subscription usage"
    yield 'cost row', f"<span class=\"mono\">${c['rubric_grading']:.2f}</span> rubric grading + <span class=\"mono\">${c['preference_judging']:.2f}</span> preference judging + <span class=\"mono\">${c['full_rubric_check']:.2f}</span> full-rubric check = ${c['total']:.2f} OpenRouter credits, plus <span class=\"mono\">${c['claude_code_subscription_usage']:.2f}</span> of Claude Code subscription usage for solving (reported by the CLI; not billed per call): <b>${c['all_in_this_version']:.2f}</b> all-in"
    yield 'cost chart title', f"Where this version's ${c['all_in_this_version']:.2f} went"
    yield 'human reviews with errors', f"Of {hu['reviewed']} outputs reviewed in full, {hu['consequential_errors']} carry"
    yield 'gemini legend', f"Gemini 4 Argon, {g['outputs']} outputs"
    yield 'sol legend', f"GPT-6.1 Sol, {s['outputs']} outputs"
    yield 'gemini chart data', f"n:{g['outputs']},v:[{g['clean']},{g['any_honored_failure']},{g['severity_4']}]"
    yield 'sol chart data', f"n:{s['outputs']},v:[{s['clean']},{s['any_honored_failure']},{s['severity_4']}]"
    yield 'gemini table row', f"<td class=\"n\">{g['outputs']}</td><td class=\"n\">{g['clean']}</td><td class=\"n\">{g['any_honored_failure']}</td><td class=\"n\">{g['severity_4']}</td><td class=\"n\">{g['stated_not_honored_requirements']}</td>"
    yield 'sol table row', f"<td class=\"n\">{s['outputs']}</td><td class=\"n\">{s['clean']}</td><td class=\"n\">{s['any_honored_failure']}</td><td class=\"n\">{s['severity_4']}</td><td class=\"n\">{s['stated_not_honored_requirements']}</td>"
    yield 'agreement chart data', f"[['Both judges failed it',{a['both_fail']}],['Sol only',{a['sol_only']}],['Gemini only',{a['gemini_only']}],['Neither',{a['neither']}]]"
    yield 'agreement title', f"on the {a['shared']} outputs both judges graded"
    yield 'strict validity', f"strict quote validity {g['strict_evidence_valid']}/{g['outputs']} (Gemini) and {s['strict_evidence_valid']}/{s['outputs']} (GPT-6.1)"
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
    c = RES['cost_usd']
    assert abs(c['rubric_grading'] + c['preference_judging'] + c['full_rubric_check'] - c['total']) < 0.011
    assert abs(c['total'] + c['claude_code_subscription_usage'] - c['all_in_this_version']) < 0.011


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
            f"This run: {stated} of {n} confirmed errors state the rule correctly elsewhere",
            f"All {len(hist)} first-stage confirmed errors came from the conflicting ({hist.count('conflict')}) or recoverable-gap ({hist.count('recovery')}) conditions",
            f"conflict variants: {len(clab)} output labeled, {'no error' if all(r['consequential_error'] == 'no' for r in clab) else 'error'}",
            f"the GPT-6.1 judge fails {j['any_fail']['sol']['fp']} of the {neg} outputs with no consequential error, Gemini {j['any_fail']['gemini']['fp']} of {neg}",
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
    lw = v['located_whole_judgment']; named, scored, gnamed = lw['named_anywhere']['sol'], lw['named_in_requirement']['sol'], lw['named_anywhere']['gemini']
    assert lw['errors'] == n and lw['named_in_requirement']['gemini'] == scored and j['sev4']['sol']['tp'] == j['sev4']['gemini']['tp'] == 0
    ca, cr = [round(x * 100) for x in lw['wilson95_named_anywhere']['sol']], [round(x * 100) for x in lw['wilson95_named_in_requirement']['sol']]
    yield 'kpi located', f"{named} of {n}</div><div class=\"l\">of those errors the GPT-6.1 judge names in its verdict; its scored requirements record {scored}, none at severity 4 (Gemini judge: {gnamed} of {n})"
    yield 'box claim', f"The GPT-6.1 judge names {named} of the {n} consequential errors in its written verdict, but its scored requirements record {scored} and rate none at severity 4; the Gemini judge names {gnamed}."
    yield 'box n', f"{rs['selected']} deliverables drawn at random from 132 (30 GDPval tasks, 6 occupations, Claude Sonnet 5.5 and Opus 5.5), reviewed from packets of source and output text: {n} carry an error someone would act on."
    yield 'box ci', f"Error rate {round(100 * n / rs['labeled'])}% ({ci[0]}–{ci[1]}%). Named by the GPT-6.1 judge: {named} of {n} ({ca[0]}–{ca[1]}%); scored: {scored} of {n} ({cr[0]}–{cr[1]}%)."
    yield 'finding 2 num', f"{named} / {n}<small>errors the GPT-6.1 judge names; {scored} is scored"
    yield 'kpi false alarms', f"{j['any_fail']['sol']['fp']} of {neg}</div><div class=\"l\">deliverables without a consequential error that the GPT-6.1 judge still fails on some requirement (Gemini {j['any_fail']['gemini']['fp']} of {neg})"
    yield 'kpi cost', f"${c['all_in_this_version']:.2f}</div><div class=\"l\">all-in for this version: ${c['total']:.2f} OpenRouter credits for grading plus ${c['claude_code_subscription_usage']:.2f} of Claude Code subscription usage"
    tw = rs['excluding_tier_w']; ciw = [round(x * 100) for x in tw['wilson95']]
    assert rs['by_tier']['W']['labeled'] == 3 and tw['prevalence'][1] == rs['labeled'] - 3
    yield 'tier W finding', f"so the native-file figure is {tw['prevalence'][0]} of {tw['prevalence'][1]} (CI {ciw[0]}–{ciw[1]}%)"
    yield 'tier W limits', f"and {tw['prevalence'][0]} of {tw['prevalence'][1]} (CI {ciw[0]}–{ciw[1]}%) on native-file tasks only"
    pr = v['preference_by_set']['R']
    yield 'pairs finding', f"On the {pr['gemini']['pairs']} new-occupation Sonnet-vs-Opus pairs, judged GDPval-style in both presentation orders, Gemini returns a position-consistent verdict on {pr['gemini']['position_consistent']} and picks Opus in {pr['gemini']['prefers_opus_consistent']} of them; the GPT-6.1 judge is consistent on {pr['sol']['position_consistent']} and picks Opus in {pr['sol']['prefers_opus_consistent']}"
    yield 'pairs number', f"{pr['gemini']['prefers_opus_consistent']} / {pr['gemini']['position_consistent']}<small>consistent new-occupation pairs"
    fa = v['false_alarms']; assert fa['complete'] and fa['requirement_failures'] == 48 and fa['output_judge_cases'] == 21
    yield 'record spec false alarms', f"Reference-specific figures caused {fa['by_category']['ref_figure']} of {fa['requirement_failures']} false alarms"
    bc = fa['by_category']
    yield 'abstract cost', f"Cost: ${c['all_in_this_version']:.2f}.</p>"
    yield 'abstract prevalence', f"a seeded random sample of {rs['selected']} was reviewed from packets of source and output text. {n} carry a consequential error."
    yield 'abstract located', f"The GPT-6.1 judge names {named} in its verdict but scores {scored}; Gemini names {gnamed}; neither rates any at severity 4"
    yield 'finding 1 solvers', f"(Sonnet {rs['by_solver']['sonnet'][0]} of {rs['by_solver']['sonnet'][1]}, Opus {rs['by_solver']['opus'][0]} of {rs['by_solver']['opus'][1]}; the packet cut {rs['packet_cut']['outputs_cut']} long spreadsheets"
    yield 'finding 2 grader rule', f"the GPT-6.1 judge flags {j['crit']['sol']['tp']} of the {n} documents but also fails {j['crit']['sol']['fp']} of {neg} clean outputs; at any failed requirement, {j['any_fail']['sol']['tp']} and {j['any_fail']['sol']['fp']}"
    bj = lw['by_judge']
    yield 'part 3 located row', f"the GPT-6.1 judge names {named} of {n} ({bj['sol'].get('requirement', 0)} in a failed requirement, {bj['sol'].get('verdict', 0)} in the overall verdict only), the Gemini judge {gnamed} of {n} plus {bj['gemini'].get('related', 0)} related"
    yield 'record located', f"A failed requirement named the reviewer's error in {scored} of {n}; the GPT-6.1 judge's verdict named {named}; severity reached 4 in {j['sev4']['sol']['tp']} of {n}"
    yield 'training baseline', f"({scored} of {n} in a scored requirement; {named} of {n} in the GPT-6.1 judge's verdict text)"
    pc = rs['packet_cut']; assert pc['all_spreadsheets'] and not pc['marker'] and pc['cut_with_error'] + pc['cut_without_error'] == pc['outputs_cut']
    yield 'limits packet cut', f"In {pc['outputs_cut']} of the {pc['of']} sampled outputs, one workbook exceeded the packet limit."
    yield 'limits packet detail', f"The packet cut each output at {pc['output_cap_chars']:,} characters and each source at {pc['source_cap_chars']:,}, with no marker; all {pc['outputs_cut']} are spreadsheets, the largest {pc['largest_chars']:,} characters, and the {pc['cut_without_error']} without a confirmed error are among the {neg} labeled clean, so the {j['any_fail']['sol']['fp']}-of-{neg} false-alarm count rests partly on excerpts."
    yield 'part 1 packet cap', f"(outputs cut at {pc['output_cap_chars']:,} characters)"
    hs, hci, tax = v['historical_sol_confound'], v['historical_sol_solver_ci95'], RES['historical']['failure_taxonomy']; pjc = RES['historical']['primary_judge_critical']
    assert hs['consequential_yes'] == 0 and tax['model_behavior_by_solver']['sol'] == 0
    yield 'gpt solver triage', f"Its {RES['historical']['by_solver_parseable']['sol']} parseable outputs account for {tax['model_behavior_by_solver']['sol']} of the {tax['model_behavior']} model-behavior failures in the triage, and the {hs['labeled']} of them read in full for this run's confound check carry no consequential error (95% CI {round(hci[0] * 100)}–{round(hci[1] * 100)}%)"
    yield 'gpt solver self-preference', f"Its own judge flagged {pjc['sol'][0]} of its {pjc['sol'][1]} outputs against {pjc['sonnet'][0]} of {pjc['sonnet'][1]} Claude outputs (Fisher p = {pjc['fisher_two_sided_p']:.4f})"
    parts = [st.get('partial_output') for t in v['tasks'] if t['set'] in ('R', 'S') for sv in t['solvers'].values() for st in (sv.get('judges') or {}).values()]  # new outputs only
    yield 'reward truncation', f"{sum(1 for x in parts if x)} of {len(parts)} new grades saw a budgeted view of a large spreadsheet; one \"Top 5\" summary workbook ran to {pc['largest_chars']:,} characters"
    fr = v['full_rubric']; assert all(x.endswith('|gemini') for x in fr['capped_missed_full_found'])
    yield 'reward cap', f"on the {fr['errors_complete']} confirmed errors re-judged against the full rubric, the Gemini judge passed the capped ten but failed the full rubric in {len(fr['capped_missed_full_found'])} cases"
    yield 'reward hedge', f"{bc['hedge_as_commitment']} of the {fa['requirement_failures']} false alarms were labeled assumptions the judges read as commitments"
    yield 'part 3 grader rule', f"under the grader's rule {j['crit']['sol']['fp']} and {j['crit']['gemini']['fp']}"
    yield 'limits freeze', "7 of the 22 outputs came from the earlier follow-up run"


def test_v31_page_figures_match_results():
    missing = [(name, s) for name, s in v31_checks() if s not in INDEX]
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
    for bad in ('pitch.html', 'h-pitch', 'The pilot I would sell', 'Why Turing', 'i-fam', 'Full pitch page', 'frozen before any grading', 'acceptable outputs Sol', 'Codex', 'Earlier-stage spend', 'earlier_stages_cost'):
        assert bad not in PAGE, bad
    assert not (ROOT / 'docs/pitch.html').exists()
    assert 'earlier_stages_cost_usd_not_rerun' not in RES
    assert 'Codex' not in (ROOT / 'docs/methods.html').read_text(encoding='utf-8')


def test_false_alarm_classification_covers_every_failure():
    """Every honored failure a judge recorded on a clean random-sample output has exactly one category, and every row refers to a real failure."""
    v = RES['v31']; fa = v['false_alarms']
    cal = json.loads((ROOT / 'output/study_v3/calibration_set_v31.json').read_text())
    labels = {r['run_id']: r for r in json.loads((ROOT / 'output/study_v3/human_reviews_v3.json').read_text())['reviews']}
    clean = {r for r in cal['selected'] if labels[r]['consequential_error'] == 'no'}
    seen = set()
    for t in v['tasks']:
        for m, sv in t['solvers'].items():
            if sv['run_id'] not in clean: continue
            for j, st in (sv.get('judges') or {}).items():
                for f in st['fails']: seen.add((sv['run_id'], j, f['id']))
    # tasks rows keep only the top 3 fails per judge; the classification must cover at least those and total 48
    have = {(r['run_id'], r['judge'], r['req']) for r in fa['rows']}
    assert seen <= have, sorted(seen - have)[:5]
    assert len(have) == fa['requirement_failures'] == fa['expected_requirement_failures']
    assert all(r['category'] in fa['categories'] for r in fa['rows'])
    assert sum(fa['by_category'].values()) == fa['requirement_failures']


def test_whole_judgment_reading_is_complete_and_consistent():
    """Every confirmed error in the random sample has a 'where' for each judge; counts match the rows; same-in-requirement matches the older reading."""
    v = RES['v31']; lw = v['located_whole_judgment']; rows = [r for r in v['hand_taxonomy']['rows'] if r['in_random_sample']]
    ok = {'requirement', 'verdict', 'related', 'missed'}
    for r in rows:
        for j in ('sol', 'gemini'):
            loc = (r.get('locate') or {}).get(j) or {}
            assert loc.get('where') in ok and loc.get('quote'), (r['run_id'], j)
            if loc['where'] == 'requirement':
                assert (r['match'].get(j) or {}).get('match') == 'same', (r['run_id'], j)
        assert r.get('short'), r['run_id']
    for j in ('sol', 'gemini'):
        assert sum(lw['by_judge'][j].values()) == lw['errors'] == len(rows)


def test_honesty_flags_point_at_confirmed_errors():
    v = RES['v31']; hb = v['honesty']; conf = {r['run_id'] for r in v['hand_taxonomy']['rows']}
    assert hb['rows'] and set(hb['rows']) <= conf
    assert all(x['kind'] in hb['values'] for x in hb['rows'].values())


def test_sizing_is_reproducible():
    import label_sizing
    S = RES['v31']['label_sizing']
    for r in S['rows']:
        n, k = label_sizing.errors_needed(r['baseline_recall'][0] / r['baseline_recall'][1], r['target_recall'])
        assert (n, k) == (r['errors_needed'], r['critical_count'])
