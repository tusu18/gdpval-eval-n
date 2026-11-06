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
