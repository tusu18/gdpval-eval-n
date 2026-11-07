"""Study v3.1 block for output/results.json (imported by build_results.py). Saved records only; no API calls.

Sets (config/study_v31.json): O = the 11 original-variant v3 tasks; R = 15 tasks in the 3 new occupations (out of sample);
S = the 4 previously skipped tasks (tiers P and W); F = all 30 original-variant tasks; C = the 3 conflict variants.
Judge 'flags' an output when any requirement is honored-fail with severity >= 4 (sev4); 'any_fail' when any honored fail.
Human positive = consequential_error 'yes'; 'uncertain' labels are reported and left out of rate denominators.
"""
import collections, json, math, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / 'output/study_v3'; INST = ROOT / 'data/study_v3/instances'; REQ = ROOT / 'data/study_v3/requirements'
read = lambda p: json.loads(Path(p).read_text())
JUDGES = ('gemini', 'sol')


def wilson(k, n, z=1.96):
    if not n: return None
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 3), round(min(1, c + h), 3)]


def judge_index():
    latest = {}
    for p in sorted((V3 / 'judge_runs').glob('*__sel*__*.json')):
        j = read(p); k = (j['run_id'], j['judge']); ver = os.path.basename(p).split('__')[-2]
        if k not in latest or ver > latest[k][0]: latest[k] = (ver, j)
    out = {}
    for (run, judge), (ver, j) in latest.items():
        reqs = (j.get('judgment') or {}).get('requirements') or []
        if j.get('status') != 'received' or not reqs: continue
        fails = []
        for x in reqs:
            h = x.get('honored') or {}
            if h.get('status') == 'fail':
                ev = [e for e in (h.get('evidence') or []) if isinstance(e, dict) and e.get('output_quote')]
                fails.append({'id': str(x.get('id')), 'severity': int(h.get('severity') or 0), 'stated_pass': (x.get('stated') or {}).get('status') == 'pass',
                              'consequence': str(h.get('consequence') or '')[:240], 'output_quote': str(ev[0]['output_quote'])[:220] if ev else ''})
        sev = [f['severity'] for f in fails]
        out[(run, judge)] = {'any_fail': bool(fails), 'sev4': any(s >= 4 for s in sev), 'max_severity': max(sev) if sev else 0, 'n_fail': len(fails),
                             'sbnh': sum(f['stated_pass'] for f in fails), 'strict': (j.get('assessment') or {}).get('status') != 'invalid_grader_evidence',
                             'fails': sorted(fails, key=lambda f: -f['severity']),
                             'partial_output': bool((j.get('artifact_budget') or {}).get('applied'))}  # v3.1 output budget: judge saw part of the file
    return out


def per_judge(stats, runs):
    out = {}
    for j in JUDGES:
        m = [stats[(r, j)] for r in runs if (r, j) in stats]
        out[j] = {'outputs': len(m), 'clean': sum(not v['any_fail'] for v in m), 'any_honored_failure': sum(v['any_fail'] for v in m),
                  'severity_4': sum(v['sev4'] for v in m), 'stated_not_honored_requirements': sum(v['sbnh'] for v in m), 'strict_evidence_valid': sum(v['strict'] for v in m)}
    shared = [r for r in runs if (r, 'gemini') in stats and (r, 'sol') in stats]
    g = lambda r: stats[(r, 'gemini')]; s = lambda r: stats[(r, 'sol')]
    agree = {'shared': len(shared), 'both_fail': sum(g(r)['any_fail'] and s(r)['any_fail'] for r in shared), 'sol_only': sum(s(r)['any_fail'] and not g(r)['any_fail'] for r in shared),
             'gemini_only': sum(g(r)['any_fail'] and not s(r)['any_fail'] for r in shared), 'neither': sum(not g(r)['any_fail'] and not s(r)['any_fail'] for r in shared),
             'shared_severity_4': sum(g(r)['sev4'] and s(r)['sev4'] for r in shared)}
    return out, agree


def confusion(labels, stats, key):
    out = {}
    for j in JUDGES:
        c = collections.Counter(); misses = []; alarms = []
        for run, lab in labels.items():
            if (run, j) not in stats or lab['consequential_error'] not in ('yes', 'no'): continue
            h = lab['consequential_error'] == 'yes'; jf = stats[(run, j)][key]
            c[('tp' if jf else 'fn') if h else ('fp' if jf else 'tn')] += 1
            if h and not jf: misses.append(run)
            if jf and not h: alarms.append(run)
        tp, fn, fp, tn = c['tp'], c['fn'], c['fp'], c['tn']
        out[j] = {'tp': tp, 'fn': fn, 'fp': fp, 'tn': tn, 'sensitivity': [tp, tp + fn], 'specificity': [tn, tn + fp], 'missed': misses, 'false_alarms': alarms}
    return out


def ai_drafted(label):
    return bool(label.get('label_author')) or 'automated' in (label.get('review_method') or '').lower()


def is_human(label):
    """A label is human if a person wrote it, or a person verified an AI draft case by case with the kit's
    verify command (which records who, when, minutes and whether the draft was confirmed or corrected)."""
    return not ai_drafted(label) or bool(label.get('verified_by') and label.get('verified_at'))


def build():
    prep31 = V3 / 'prepare_summary_v31.json'
    if not prep31.exists(): return None
    cfg = read(ROOT / 'config/study_v31.json'); new_occ = set(cfg['occupations']['new'])
    inst = {f.stem: read(f) for f in INST.glob('*.json')}
    v3_made = set(read(V3 / 'prepare_summary.json')['made']) if (V3 / 'prepare_summary.json').exists() else set()
    runs = {r['run_id']: r for r in (read(p) for p in sorted((V3 / 'solver_runs').glob('*.json')))}
    rep = lambda rid: int(rid.rsplit('__r', 1)[-1])
    orig = [i for i, d in inst.items() if d['variant'] == 'original']
    sets = {'O': sorted(i for i in orig if i in v3_made), 'R': sorted(i for i in orig if inst[i]['occupation'] in new_occ),
            'S': sorted(i for i in orig if inst[i].get('tier') in ('P', 'W')), 'F': sorted(orig), 'C': sorted(i for i, d in inst.items() if d['variant'] == 'conflict')}
    stats = judge_index()
    def r1(iids): return [r for r, x in runs.items() if x['instance_id'] in iids and rep(r) == 1 and x.get('status') == 'submitted']
    delivery = {}
    for name, iids in sets.items():
        rr = [x for r, x in runs.items() if x['instance_id'] in iids and rep(r) == 1]
        delivery[name] = {'instances': len(iids), 'episodes': len(rr), 'submitted': sum(x.get('status') == 'submitted' for x in rr), 'status': dict(collections.Counter(x.get('status') for x in rr))}
    by_set = {}
    for name, iids in sets.items():
        pj, ag = per_judge(stats, r1(set(iids))); by_set[name] = {'per_judge': pj, 'agreement': ag}
    by_occ = {}
    for occ in sorted({inst[i]['occupation'] for i in orig}):
        rr = r1({i for i in orig if inst[i]['occupation'] == occ})
        by_occ[occ] = {m: {j: {'outputs': sum(1 for r in rr if runs[r]['model'] == m and (r, j) in stats), 'any_fail': sum(1 for r in rr if runs[r]['model'] == m and stats.get((r, j), {}).get('any_fail')),
                               'sev4': sum(1 for r in rr if runs[r]['model'] == m and stats.get((r, j), {}).get('sev4'))} for j in JUDGES} for m in ('sonnet', 'opus')}
    # human labels
    all_labels = {r['run_id']: r for r in read(V3 / 'human_reviews_v3.json')['reviews']} if (V3 / 'human_reviews_v3.json').exists() else {}
    labels = {k: v for k, v in all_labels.items() if is_human(v)}  # AI-drafted labels count only once a person has verified them
    ai_drafts = {k: v for k, v in all_labels.items() if not is_human(v)}
    sample = read(V3 / 'calibration_set_v31.json')['selected'] if (V3 / 'calibration_set_v31.json').exists() else []
    rs_labels = {r: labels[r] for r in sample if r in labels}
    yes = sum(l['consequential_error'] == 'yes' for l in rs_labels.values()); no = sum(l['consequential_error'] == 'no' for l in rs_labels.values())
    unc = sum(l['consequential_error'] == 'uncertain' for l in rs_labels.values())
    random_sample = {'selected': len(sample), 'labeled': len(rs_labels), 'ai_drafts_unverified': sum(1 for r in sample if r in ai_drafts),
                     'verified_ai_drafts': sum(1 for r in rs_labels if ai_drafted(rs_labels[r])), 'consequential_yes': yes, 'consequential_no': no, 'uncertain': unc,
                     'prevalence': [yes, yes + no], 'wilson95': wilson(yes, yes + no), 'acceptable_yes': sum(l['content_acceptable'] == 'yes' for l in rs_labels.values()),
                     'task_defect_yes': sum(l['evaluation_defect'] == 'yes' for l in rs_labels.values()),
                     'by_occupation': {occ: [sum(1 for r, l in rs_labels.items() if inst[runs[r]['instance_id']]['occupation'] == occ and l['consequential_error'] == 'yes'),
                                             sum(1 for r in rs_labels if inst[runs[r]['instance_id']]['occupation'] == occ)] for occ in sorted({inst[i]['occupation'] for i in orig})},
                     'by_solver': {m: [sum(1 for r, l in rs_labels.items() if runs[r]['model'] == m and l['consequential_error'] == 'yes'), sum(1 for r in rs_labels if runs[r]['model'] == m)] for m in ('sonnet', 'opus')},
                     'minutes': [l['review_minutes'] for l in rs_labels.values() if l.get('review_minutes') is not None]}
    judge_vs_human = {'random_sample': {'sev4': confusion(rs_labels, stats, 'sev4'), 'any_fail': confusion(rs_labels, stats, 'any_fail')},
                      'all_follow_up_labels': {'sev4': confusion(labels, stats, 'sev4'), 'any_fail': confusion(labels, stats, 'any_fail')}}
    taxonomy = collections.Counter(); tax_rows = []
    es = ROOT / 'site_src/error_summaries_v31.json'; plain = read(es) if es.exists() else {}
    for r, l in labels.items():
        if l['consequential_error'] != 'yes': continue
        cat = l.get('category') or 'uncategorized'; taxonomy[cat] += 1
        tax_rows.append({'run_id': r, 'occupation': inst[runs[r]['instance_id']]['occupation'] if r in runs else None, 'model': runs.get(r, {}).get('model'), 'category': cat,
                         'location': l.get('location'), 'stated_elsewhere': l.get('stated_elsewhere'), 'in_random_sample': r in rs_labels, 'in_R': r in r1(set(sets['R'])), 'plain': (plain.get('summaries') or {}).get(r)})
    hs = V3 / 'human_reviews_hist_sol.json'
    hist_sol = None
    if hs.exists():
        hl = [l for l in read(hs)['reviews'] if is_human(l)]
        hist_sol = {'labeled': len(hl), 'consequential_yes': sum(l['consequential_error'] == 'yes' for l in hl), 'acceptable_yes': sum(l['content_acceptable'] == 'yes' for l in hl),
                    'rows': [{k: l.get(k) for k in ('run_id', 'content_acceptable', 'consequential_error', 'category', 'location', 'stated_elsewhere')} for l in hl]}
    # preference vs rubric by set
    pw = None; pwp = ROOT / 'output/pairwise_grader_16/report.json'
    if pwp.exists():
        prep = read(pwp); pw = {}
        for name in ('O', 'R', 'S'):
            rows = [x for x in prep['pairs'] if x['instance_id'] in sets[name]]; pw[name] = {}
            for j in JUDGES:
                jr = [x for x in rows if x['judge'] == j]
                cons = [x for x in jr if 'missing' not in x['order_verdicts'] and x['order_verdicts'][0] == x['order_verdicts'][1]]
                pw[name][j] = {'pairs': len(jr), 'position_consistent': len(cons), 'prefers_opus': sum(x['preference'].startswith('opus') for x in jr),
                               'prefers_sonnet': sum(x['preference'].startswith('sonnet') for x in jr), 'inconsistent': sum(x['preference'] == 'inconsistent' for x in jr),
                               'prefers_opus_consistent': sum(x['preference'] == 'opus' for x in cons), 'contradicts_rubric': sum(x.get('vs_rubric') == 'contradicts' for x in jr),
                               'severity_differs': sum(x.get('vs_rubric') in ('contradicts', 'agrees') for x in jr),
                               'contradiction_pairs': [x['instance_id'] for x in jr if x.get('vs_rubric') == 'contradicts']}
        pw['cost_usd_total'] = round(prep.get('cost_usd', 0), 2)
    # repeats
    repeats = {}
    for j in JUDGES:
        pairs = []
        for r, x in runs.items():
            if rep(r) != 1: continue
            r2 = r.rsplit('__r', 1)[0] + '__r2'
            if (r, j) in stats and (r2, j) in stats: pairs.append((stats[(r, j)], stats[(r2, j)]))
        repeats[j] = {'pairs': len(pairs), 'any_fail_agree': sum(a['any_fail'] == b['any_fail'] for a, b in pairs), 'sev4_agree': sum(a['sev4'] == b['sev4'] for a, b in pairs),
                      'both_sev4': sum(a['sev4'] and b['sev4'] for a, b in pairs), 'either_sev4': sum(a['sev4'] or b['sev4'] for a, b in pairs)}
    fr = read(ROOT / 'output/full_rubric_17/report.json') if (ROOT / 'output/full_rubric_17/report.json').exists() else None
    if fr:
        done = [r for r in fr['rows'] if r.get('coverage', 'complete') == 'complete']
        full_rubric = {'rows': fr['rows'], 'compared': len(done), 'errors_complete': len({r['run_id'] for r in done}),
                       'errors_partial_or_not_run': sorted({r['run_id'] for r in fr['rows'] if r.get('coverage') in ('partial', 'not_run')}),
                       'verdict_changes': sum(bool(r.get('verdict_changes')) for r in done), 'any_fail_changes': sum(bool(r.get('any_fail_changes')) for r in done),
                       'capped_missed_full_found': [f"{r['run_id']}|{r['judge']}" for r in done if r['capped']['honored_fails'] == 0 and r['full']['honored_fails'] > 0],
                       'max_severity_full': {f"{r['run_id']}|{r['judge']}": r['full']['max_severity'] for r in done}, 'cost_usd': fr['cost_usd']}
    else:
        full_rubric = None
    # predictions
    R_runs = set(r1(set(sets['R'])))
    p1_cases = [t for t in tax_rows if t['run_id'] in R_runs and t.get('stated_elsewhere') == 'yes' and t.get('location')]
    ag = by_set['R']['agreement']; conf = judge_vs_human['random_sample']['sev4']
    preds = {
        'P1': {'holds': (bool(p1_cases) if any(r in labels for r in R_runs) else None), 'evidence': [t['run_id'] for t in p1_cases]},
        'P2': {'holds': (ag['gemini_only'] <= 2) if ag['shared'] else None, 'evidence': f"Gemini-only {ag['gemini_only']} of {ag['shared']} shared R outputs"},
        'P3': {'holds': (any(pw['R'][j]['contradicts_rubric'] >= 1 for j in JUDGES) if pw and any(pw['R'][j]['pairs'] for j in JUDGES) else None),
               'evidence': {j: (pw['R'][j]['contradicts_rubric'], pw['R'][j]['severity_differs']) for j in JUDGES} if pw else None},
        'P4': {'holds': (conf['gemini']['fn'] >= conf['sol']['fn']) if (conf['gemini']['tp'] + conf['gemini']['fn']) else None,
               'evidence': {'gemini_missed': conf['gemini']['fn'], 'sol_missed': conf['sol']['fn'], 'confirmed_errors': conf['gemini']['tp'] + conf['gemini']['fn']}},
        'P5': {'holds': (all(pw['R'][j]['prefers_opus_consistent'] * 2 > pw['R'][j]['position_consistent'] for j in JUDGES) if pw and all(pw['R'][j]['position_consistent'] for j in JUDGES) else None),
               'evidence': {j: (pw['R'][j]['prefers_opus_consistent'], pw['R'][j]['position_consistent']) for j in JUDGES} if pw else None},
    }
    # cost
    led = read(V3 / 'judge_ledger.json') if (V3 / 'judge_ledger.json').exists() else []
    v3_runs = {r for r, x in runs.items() if x['instance_id'] in v3_made and rep(r) == 1}
    cost = {'claude_code_r1_new': round(sum((x.get('claude_result') or {}).get('total_cost_usd') or 0 for r, x in runs.items() if rep(r) == 1 and r not in v3_runs), 2),
            'claude_code_r2': round(sum((x.get('claude_result') or {}).get('total_cost_usd') or 0 for r, x in runs.items() if rep(r) == 2), 2),
            'judging_new': round(sum(e.get('actual_cost_usd') or 0 for e in led if e['run_id'] not in v3_runs), 2),
            'pairwise_new': round((pw or {}).get('cost_usd_total', 3.15) - 3.15, 2), 'full_rubric': (full_rubric or {}).get('cost_usd', 0)}
    cost['openrouter_credits_this_version'] = round(cost['judging_new'] + cost['pairwise_new'] + cost['full_rubric'], 2)  # what this version actually spent
    cost['claude_code_subscription_reported'] = round(cost['claude_code_r1_new'] + cost['claude_code_r2'], 2)  # usage-equivalent reported by Claude Code; not billed per call
    cost['total'] = round(cost['openrouter_credits_this_version'] + cost['claude_code_subscription_reported'], 2)  # subtotals only; summing every key double-counts
    # per-task explorer rows
    tasks = []
    for iid in sorted(inst, key=lambda i: (inst[i]['occupation'], i)):
        d = inst[iid]; row = {'instance_id': iid, 'occupation': d['occupation'], 'variant': d['variant'], 'tier': d.get('tier', 'A'),
                              'set': 'C' if d['variant'] == 'conflict' else 'R' if iid in sets['R'] else 'S' if iid in sets['S'] else 'O', 'solvers': {}}
        reqs = {q['id']: q['text'] for q in read(REQ / ((d.get('family_prefix') or d['family_id']) + '.json'))['requirements']} if (REQ / ((d.get('family_prefix') or d['family_id']) + '.json')).exists() else {}
        for m in ('sonnet', 'opus'):
            rid = f'{iid}__{m}__r1'; x = runs.get(rid)
            if not x: continue
            sv = {'run_id': rid, 'status': x.get('status'), 'files': [o['name'] for o in x.get('outputs', [])], 'judges': {}, 'r2': {}}
            for j in JUDGES:
                st = stats.get((rid, j))
                if st: sv['judges'][j] = {k: st[k] for k in ('max_severity', 'n_fail', 'sbnh', 'partial_output')} | {'fails': [f | {'requirement': reqs.get(f['id'], '')[:200]} for f in st['fails'][:3]]}
                st2 = stats.get((f'{iid}__{m}__r2', j))
                if st2: sv['r2'][j] = st2['max_severity']
            if rid in labels:
                l = labels[rid]; sv['human'] = {k: l.get(k) for k in ('content_acceptable', 'consequential_error', 'evaluation_defect', 'category', 'location', 'stated_elsewhere', 'reviewer_note')} | {'random_sample': rid in rs_labels}
            row['solvers'][m] = sv
        if pw:
            row['preference'] = {x['judge']: x['preference'] for x in read(pwp)['pairs'] if x['instance_id'] == iid}
        tasks.append(row)
    return {'sets': {k: len(v) for k, v in sets.items()}, 'set_members': sets, 'delivery': delivery, 'by_set': by_set, 'by_occupation': by_occ,
            'random_sample': random_sample, 'judge_vs_human': judge_vs_human, 'hand_taxonomy': {'counts': dict(taxonomy), 'rows': tax_rows, 'plain_confirmed_by_author': bool(plain.get('confirmed_by_author'))},
            'historical_sol_confound': hist_sol, 'preference_by_set': pw, 'repeats': repeats, 'full_rubric': full_rubric, 'predictions': preds, 'cost_usd': cost, 'tasks': tasks}
