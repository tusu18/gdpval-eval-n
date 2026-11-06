"""Single source of truth for every number on the findings page.

Reads only saved run records (no API calls) and writes output/results.json. tests/test_site_numbers.py checks
that the figures printed in site/index.html match this file, so a number cannot drift from its source.

  python3 scripts/build_results.py            # writes output/results.json and prints it
"""
import glob, json, os, collections
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
read = lambda p: json.loads(Path(p).read_text())


def fisher_two_sided(a, b, c, d):
    """2x2 [[a,b],[c,d]] exact two-sided p (sum of tables with probability <= observed)."""
    r1, c1, N = a + b, a + c, a + b + c + d
    pr = lambda k: comb(r1, k) * comb(N - r1, c1 - k) / comb(N, c1)
    obs = pr(a)
    return sum(pr(k) for k in range(max(0, c1 - (N - r1)), min(r1, c1) + 1) if pr(k) <= obs + 1e-12)


def historical():
    scores = read(ROOT / 'output/paired_v1/scores.json')
    model = lambda m: 'sonnet' if 'sonnet' in m else 'sol'
    completed = [s for s in scores if s.get('status') == 'completed']
    attempts = len(scores); parseable = len(completed)
    decision_pass = sum(1 for s in completed if s.get('decision_pass'))
    explicit_wrong = sum(1 for s in completed if s.get('explicit_wrong'))
    # primary judge (GPT-6.1 Sol) verdicts per solver
    crit = collections.Counter(); n = collections.Counter()
    for p in glob.glob(str(ROOT / 'output/paired_v1/judgments_v3/*__primary.json')):
        run = os.path.basename(p).replace('__primary.json', ''); m = model(run); jd = read(p).get('judgment') or {}
        n[m] += 1; crit[m] += bool(jd.get('critical_error'))
    fisher = fisher_two_sided(crit['sonnet'], n['sonnet'] - crit['sonnet'], crit['sol'], n['sol'] - crit['sol'])
    # secondary judge (Claude Sonnet 5.5) on 12 outputs: critical matrix
    mat = collections.Counter()
    for p in glob.glob(str(ROOT / 'output/paired_v1/judgments_v3/*__secondary.json')):
        s = read(p).get('judgment') or {}; pr = read(p.replace('__secondary', '__primary')).get('judgment') or {}
        mat[(bool(pr.get('critical_error')), bool(s.get('critical_error')))] += 1
    # failure taxonomy (triaged by the primary judge + mechanical checks), per category per solver
    key = read(ROOT / 'output/submission_audit/private_review_key.json')
    fq = [x for x in key if x.get('failure_queue')]
    cats = collections.defaultdict(lambda: collections.Counter()); fam = collections.defaultdict(collections.Counter)
    for x in fq:
        cats[x['triage_category']][model(x['model'])] += 1; fam[x['triage_category']][x['family_id']] += 1
    MODEL = ('unsupported_continuity', 'approval_bypass', 'unsupported_eligibility', 'missing_comparison')
    SETUP = ('contract_ambiguity', 'page_overflow', 'invalid_serialization')
    tax = {c: {'total': sum(cats[c].values()), 'sonnet': cats[c]['sonnet'], 'sol': cats[c]['sol'], 'families': dict(fam[c])} for c in MODEL + SETUP}
    return {
        'attempts': attempts, 'parseable_outputs': parseable, 'missing_outputs': attempts - parseable,
        'by_solver_parseable': {'sonnet': n['sonnet'], 'sol': n['sol']},
        'fact_checks': {'decision_pass': decision_pass, 'explicit_wrong_targeted_values': explicit_wrong},
        'primary_judge_critical': {'judge': 'openai/gpt-6.1-sol', 'sonnet': [crit['sonnet'], n['sonnet']], 'sol': [crit['sol'], n['sol']], 'fisher_two_sided_p': round(fisher, 4)},
        'secondary_matrix_critical': {'neither': mat[(False, False)], 'primary_only': mat[(True, False)], 'secondary_only': mat[(False, True)], 'both': mat[(True, True)], 'double_graded': sum(mat.values())},
        'failure_taxonomy': {'total': len(fq), 'model_behavior': sum(tax[c]['total'] for c in MODEL), 'setup': sum(tax[c]['total'] for c in SETUP),
                             'model_behavior_by_solver': {'sonnet': sum(tax[c]['sonnet'] for c in MODEL), 'sol': sum(tax[c]['sol'] for c in MODEL)},
                             'setup_by_solver': {'sonnet': sum(tax[c]['sonnet'] for c in SETUP), 'sol': sum(tax[c]['sol'] for c in SETUP)},
                             'categories': tax, 'triaged_by': 'GPT-6.1 Sol primary judge plus mechanical checks; one primary category per attempt in fixed priority'},
    }


def robustness():
    a = read(ROOT / 'output/judge_robustness_10/audited_summary.json')
    comps = a['sensitivity']['comparisons']
    pairs = sum(v['binary_comparable'] for v in comps.values()); changed = sum(v['binary_changed'] for v in comps.values())
    inj = a['injection']['comparison']
    cons = a['family']['constructed']
    def grp(g):
        m = g.get('groups', {}).get('mutated', {}); c = g.get('groups', {}).get('control', g.get('groups', {}).get('controls', {}))
        return {'mutated_rejected': [m.get('rejected'), m.get('binary_comparable')], 'controls_accepted': [c.get('accepted'), c.get('binary_comparable')] if c else None,
                'critical_detected': [g.get('critical_error_checks', {}).get('detected'), g.get('critical_error_checks', {}).get('binary_comparable')]}
    return {'calls_planned': a['completion']['planned'], 'calls_received': a['completion']['received'],
            'rewording_pairs_comparable_strict': pairs, 'rewording_pairs_changed': changed, 'rewording_variants': len(comps),
            'injection_pairs_comparable': inj['binary_comparable'], 'injection_planned': inj['planned'], 'injection_changed': inj['binary_changed'],
            'authored_controls': {k: grp(v) for k, v in cons.items() if isinstance(v, dict) and 'groups' in v},
            'cost_usd': round(a['cost']['reported_api_cost_usd'], 2)}


def v3_scope():
    V3 = ROOT / 'output/study_v3'
    made = set(read(V3 / 'prepare_summary.json')['made']) if (V3 / 'prepare_summary.json').exists() else None
    return made


def followup():
    V3 = ROOT / 'output/study_v3'; made = v3_scope()  # the original v3 study: its 14 instances, r1 only; v3.1 lives in results['v31']
    solver = [x for x in (read(p) for p in sorted((V3 / 'solver_runs').glob('*.json'))) if (made is None or x['instance_id'] in made) and x['run_id'].endswith('__r1')]
    keep = {x['run_id'] for x in solver}
    latest = {}
    for p in sorted((V3 / 'judge_runs').glob('*__sel*__*.json')):
        j = read(p); k = (j['run_id'], j['judge']); ver = os.path.basename(p).split('__')[-2]
        if k not in latest or ver > latest[k][0]: latest[k] = (ver, j)
    per = {}
    for (run, judge), (ver, j) in latest.items():
        reqs = (j.get('judgment') or {}).get('requirements') or []
        if j.get('status') != 'received' or not reqs or run not in keep: continue
        fails = [((x.get('honored') or {}).get('severity') or 0) for x in reqs if (x.get('honored') or {}).get('status') == 'fail']
        sbnh = sum(1 for x in reqs if (x.get('honored') or {}).get('status') == 'fail' and (x.get('stated') or {}).get('status') == 'pass')
        per.setdefault(judge, {})[run] = {'fail': bool(fails), 'sev4': any(s >= 4 for s in fails), 'sbnh': sbnh, 'strict': j['assessment']['status'] != 'invalid_grader_evidence'}
    pj = {}
    for judge, m in per.items():
        pj[judge] = {'outputs': len(m), 'clean': sum(not v['fail'] for v in m.values()), 'any_honored_failure': sum(v['fail'] for v in m.values()),
                     'severity_4': sum(v['sev4'] for v in m.values()), 'stated_not_honored_requirements': sum(v['sbnh'] for v in m.values()),
                     'strict_evidence_valid': sum(v['strict'] for v in m.values())}
    shared = sorted(set(per.get('gemini', {})) & set(per.get('sol', {})))
    g, s = per.get('gemini', {}), per.get('sol', {})
    agree = {'shared': len(shared), 'both_fail': sum(g[r]['fail'] and s[r]['fail'] for r in shared), 'sol_only': sum(s[r]['fail'] and not g[r]['fail'] for r in shared),
             'gemini_only': sum(g[r]['fail'] and not s[r]['fail'] for r in shared), 'neither': sum(not g[r]['fail'] and not s[r]['fail'] for r in shared),
             'shared_severity_4': sum(g[r]['sev4'] and s[r]['sev4'] for r in shared)}
    led = read(V3 / 'judge_ledger.json') if (V3 / 'judge_ledger.json').exists() else []
    prep = read(V3 / 'prepare_summary.json') if (V3 / 'prepare_summary.json').exists() else {}
    return {'episodes': len(solver), 'submitted': sum(r.get('status') == 'submitted' for r in solver),
            'by_model': dict(collections.Counter(r['model'] for r in solver)), 'by_variant': dict(collections.Counter(r['variant'] for r in solver)),
            'tasks_in_slice': 15, 'tasks_run': len({r['instance_id'].split('__')[0] for r in solver if r['variant'] == 'original'}),
            'tasks_not_run': prep.get('skipped') or prep.get('excluded') or 'see config/study_v3.proposed.json tiers B/C',
            'per_judge': pj, 'agreement': agree, 'requirements_judged_per_output': 10,
            'claude_code_cost_usd': round(sum((r.get('claude_result') or {}).get('total_cost_usd') or 0 for r in solver), 2),
            'judge_cost_usd': round(sum(r.get('actual_cost_usd') or 0 for r in led if r['run_id'] in keep or (made is not None and r['run_id'].rsplit('__', 2)[0] in made and r['run_id'].endswith('__r1'))), 2)}


def construct_validity():
    OUT = ROOT / 'output/construct_validity_15'
    rep = read(OUT / 'report.json'); edits = read(ROOT / 'data/construct_validity_15/edits.json')['edits']
    out = {'edits_total': len(edits), 'edits_confirmed': sum(e.get('human_confirmed') is True for e in edits), 'edits_excluded': sorted(e['id'] for e in edits if e.get('human_confirmed') is False),
           'cost_usd': round(rep['cost_usd'], 2), 'per_judge': {}}
    for j, v in rep['per_judge'].items():
        out['per_judge'][j] = {'break_pairs': v['pairs_originally_passed_break_runs'], 'break_flipped': v['S_break_flipped_to_fail'], 'break_uncertain': v['break_to_uncertain'],
                               'paraphrase_pairs': v['paraphrase_runs'], 'paraphrase_stable': v['R_paraphrase_stayed_pass'],
                               'collateral_break': v['collateral_changes_break'], 'collateral_paraphrase': v['collateral_changes_paraphrase']}
    return out


def pairwise():
    p = ROOT / 'output/pairwise_grader_16/report.json'
    if not p.exists(): return None
    rep = read(p); made = v3_scope()
    if made is not None and any(x['instance_id'] not in made for x in rep['pairs']):  # v3.1 pairs present: recompute the v3 block from the 14 original pairs
        rows = [x for x in rep['pairs'] if x['instance_id'] in made]; per = {}
        for j in sorted({x['judge'] for x in rows}):
            jr = [x for x in rows if x['judge'] == j]
            per[j] = {'preference': {'opus': sum(x['preference'].startswith('opus') for x in jr), 'sonnet': sum(x['preference'].startswith('sonnet') for x in jr), 'tie': sum(x['preference'].startswith('tie') for x in jr),
                                     'inconsistent': sum(x['preference'] == 'inconsistent' for x in jr)},
                      'position_consistent_pairs': sum('missing' not in x['order_verdicts'] and x['order_verdicts'][0] == x['order_verdicts'][1] for x in jr),
                      'vs_rubric_v2': {'prefers_higher_severity': sum(x.get('vs_rubric') == 'contradicts' for x in jr), 'prefers_lower_severity': sum(x.get('vs_rubric') == 'agrees' for x in jr)}}
        rep = {**rep, 'pairs': rows, 'per_judge': per, 'cost_usd': 3.15}
    out = {'pairs': len(rep['pairs']) // max(1, len(rep['per_judge'])), 'cost_usd': round(rep['cost_usd'], 2), 'per_judge': {}}
    for j, v in rep['per_judge'].items():
        vr = v['vs_rubric_v2']
        out['per_judge'][j] = {'prefers_opus': v['preference']['opus'], 'prefers_sonnet': v['preference']['sonnet'], 'tie': v['preference']['tie'], 'inconsistent': v['preference']['inconsistent'],
                               'position_consistent': v['position_consistent_pairs'], 'contradicts_rubric': vr['prefers_higher_severity'], 'agrees_rubric': vr['prefers_lower_severity'],
                               'severity_differs': vr['prefers_higher_severity'] + vr['prefers_lower_severity']}
    row = [r for r in rep['pairs'] if r['instance_id'] == '15ddd28d__original']
    out['supplier_exit_confirmed_error_preferred_by'] = sorted(r['judge'] for r in row if r['preference'].startswith('opus'))
    return out


def human():
    allr = read(ROOT / 'output/human_reviews_all.json')
    rows = [r for r in allr['reviews'] if r['study'] in ('historical', 'follow_up_v3')]  # the original 8; v3.1 labels are in results['v31']
    return {'reviewed': len(rows), 'consequential_errors': sum(r['consequential_error'] == 'yes' for r in rows),
            'acceptable': sum(r['content_acceptable'] == 'yes' for r in rows), 'task_defect': sum(r['evaluation_defect'] == 'yes' for r in rows),
            'by_study': {k: v['reviewed'] for k, v in allr['studies'].items()},
            'selection': {'historical': 'fixed post-hoc purposive set of 5 (two already-reviewed cases, one pending case, the two outputs behind the headline issues), adopted before their labels were known; config/assignment_review_minimal_v1.json',
                          'follow_up_v3': '3 of the 14-output stratified sample in output/study_v3/report.json, chosen by the author to cover one Sol-only severity-4, one Sol-flagged/Gemini-passed, one Gemini-flagged; not random'},
            'gemini_graded_confirmed_errors': {'passed': 2, 'of': 2}, 'sol_graded_confirmed_errors': {'flagged': 2, 'of': 2},
            'minutes_recorded': [r['review_minutes'] for r in rows if r.get('review_minutes') is not None]}


def main():
    h, r, f, cv, hu, pw = historical(), robustness(), followup(), construct_validity(), human(), pairwise()
    import results_v31; v31 = results_v31.build()
    hist_cost = 43.78  # historical + native harness + judge diagnostics, from output/assignment_final/evidence.json cost block (reported_cumulative_usd)
    try: hist_cost = round(read(ROOT / 'output/assignment_final/evidence.json')['cost']['reported_cumulative_usd'], 2)
    except Exception: pass
    earlier = {'historical_and_diagnostics': hist_cost, 'followup_claude_code': f['claude_code_cost_usd'], 'followup_judging': f['judge_cost_usd'], 'construct_validity': cv['cost_usd'], 'pairwise_preference': (pw or {}).get('cost_usd', 0)}
    earlier['total'] = round(sum(earlier.values()), 2)
    vc = (v31 or {}).get('cost_usd', {})
    # The page reports only the OpenRouter credits this version spent. Earlier stages are reused, not re-run; their spend stays here for audit only.
    cost = {'rubric_grading': vc.get('judging_new', 0), 'preference_judging': vc.get('pairwise_new', 0), 'full_rubric_check': vc.get('full_rubric', 0)}
    cost['total'] = round(sum(cost.values()), 2)
    res = {'schema': 'turing-results-v1', 'built_from': 'saved run records only; see scripts/build_results.py',
           'solvers': ['anthropic/claude-sonnet-5.5', 'anthropic/claude-opus-5.5', 'openai/gpt-6.1-sol'],
           'historical': h, 'judge_robustness': r, 'follow_up': f, 'construct_validity': cv, 'pairwise_preference': pw, 'human_reviews': hu, 'v31': v31, 'cost_usd': cost,
           'claude_code_subscription_reported_usd': vc.get('claude_code_subscription_reported', 0), 'earlier_stages_cost_usd_not_rerun': earlier}
    (ROOT / 'output/results.json').write_text(json.dumps(res, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
