"""Construct validity test for the rubric v2 judges (study v3 outputs).

Design (after 'A Judge Should Know What Changed', 2608.24419): take (output, requirement) pairs the judge passed,
apply one BREAK edit (violates the requirement in an operative clause) and one PARAPHRASE edit (same meaning,
different words) to the extracted-text packet the judge reads, re-run the same judge on the full packet, and ask:
  S  (sensitivity)  = share of BREAK packets where the targeted requirement's honored status flips pass -> fail
  R  (stability)    = share of PARAPHRASE packets where it stays pass
  collateral        = non-target requirements whose status changed under either edit (noise)
Edits live in data/construct_validity_15/edits.json; each must be human-confirmed before results are read.
Author labels and the edit list never enter a judge request: the judge sees only the mutated packet.

  python3 scripts/construct_validity_15.py build                # mutate packets, no model calls
  python3 scripts/construct_validity_15.py judge --max-usd 12   # both judges, spend guard
  python3 scripts/construct_validity_15.py report
"""
import argparse, copy, getpass, glob, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_completion_and_pairs import api, read, write, utc
from evidence_grader_v2 import JUDGE_INSTRUCTIONS_V2, score_judgment

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / 'output/study_v3'; OUT = ROOT / 'output/construct_validity_15'
EDITS = read(ROOT / 'data/construct_validity_15/edits.json')
JUDGES = {'gemini': 'google/gemini-4-argon', 'sol': 'openai/gpt-6.1-sol'}
CONDITIONS = ('break', 'paraphrase')


def latest_ver(run):
    vs = [os.path.basename(p).split('__')[-2] for p in glob.glob(str(V3 / 'judge_runs' / f'{run}__sel*__gemini.json'))]
    return max(vs)


def original_status(run, ver, judge, rid):
    p = V3 / 'judge_runs' / f'{run}__{ver}__{judge}.json'
    if not p.exists(): return None
    j = read(p)
    for r in (j.get('judgment') or {}).get('requirements') or []:
        if str(r.get('id')) == rid: return (r.get('honored') or {}).get('status')
    return None


def mutate(packet, art_id, old, new):
    pk = copy.deepcopy(packet); hits = 0
    for a in pk['artifacts']:
        if a['id'] != art_id: continue
        for u in a['units']:
            if old in u['text']: hits += u['text'].count(old); u['text'] = u['text'].replace(old, new)
        if old in a.get('text', ''): a['text'] = a['text'].replace(old, new)
    if hits == 0: raise ValueError(f'edit target not found in {art_id}: {old[:60]!r}')
    pk.pop('selection', None); pk.pop('limitations', None)
    return pk, hits


def build():
    (OUT / 'packets').mkdir(parents=True, exist_ok=True); manifest = []
    for e in EDITS['edits']:
        ver = latest_ver(e['run_id']); base = read(V3 / 'judge_packets' / f"{e['run_id']}__{ver}.json")
        assert e['requirement_id'] in {r['id'] for r in base['requirements']}, e['id']
        row = {'id': e['id'], 'run_id': e['run_id'], 'requirement_id': e['requirement_id'], 'packet_version': ver,
               'original_honored': {j: original_status(e['run_id'], ver, j, e['requirement_id']) for j in JUDGES}, 'packets': {}}
        for cond in CONDITIONS:
            pk, hits = mutate(base, e['artifact_id'], e['old'], e[cond])
            pk['_cv'] = None  # nothing about the edit is carried into the packet
            del pk['_cv']
            path = OUT / 'packets' / f"{e['id']}__{cond}.json"; write(path, pk)
            row['packets'][cond] = {'path': str(path.relative_to(ROOT)), 'replacements': hits}
        manifest.append(row)
    write(OUT / 'manifest.json', {'built_at': utc(), 'edits_file': 'data/construct_validity_15/edits.json', 'rows': manifest})
    print(json.dumps(manifest, indent=1))


def judge(max_usd, workers=4):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    key = os.environ.get('OPENROUTER_API_KEY') or getpass.getpass('OpenRouter API key (hidden, memory only): '); api(key, 'key')
    man = read(OUT / 'manifest.json'); led_path = OUT / 'ledger.json'; ledger = read(led_path) if led_path.exists() else []
    lock = threading.Lock(); (OUT / 'runs').mkdir(exist_ok=True)
    def spent(): return sum(r.get('actual_cost_usd') or 0 for r in ledger)
    jobs = [(jname, model, row, cond) for jname, model in JUDGES.items() for row in man['rows'] for cond in CONDITIONS]
    def one(job):
        jname, model, row, cond = job
        dest = OUT / 'runs' / f"{row['id']}__{cond}__{jname}.json"
        if dest.exists() and read(dest).get('status') == 'received': return
        with lock:
            if spent() >= max_usd: print(json.dumps({'halt': f'spend guard ${spent():.2f} >= ${max_usd}'})); return
            lid = len(ledger); ledger.append({'id': row['id'], 'condition': cond, 'judge': jname, 'status': 'dispatched_cost_pending', 'actual_cost_usd': None}); write(led_path, ledger)
        packet = read(ROOT / row['packets'][cond]['path'])
        body = {'model': model, 'messages': [{'role': 'system', 'content': JUDGE_INSTRUCTIONS_V2 + '\nBe concise: one or two evidence objects per check, short rationales.'}, {'role': 'user', 'content': json.dumps(packet, ensure_ascii=False)}],
                'max_tokens': 12000, 'reasoning': {'effort': 'medium'}, 'response_format': {'type': 'json_object'},
                'provider': {'allow_fallbacks': False, 'require_parameters': True, 'max_price': {'prompt': 10, 'completion': 50}}}
        out = {'id': row['id'], 'run_id': row['run_id'], 'requirement_id': row['requirement_id'], 'condition': cond, 'judge': jname, 'model': model, 'started_at': utc(), 'status': 'running'}
        try:
            resp = api(key, 'chat/completions', body); usage = resp.get('usage', {}); cost = usage.get('cost')
            with lock: ledger[lid].update(status='actual' if isinstance(cost, (int, float)) else 'reported_cost_missing', actual_cost_usd=cost, generation_id=resp.get('id')); write(led_path, ledger)
            content = resp['choices'][0]['message']['content']
            try: judgment = json.loads(content)
            except ValueError: judgment = {}
            out.update(status='received', returned_model=resp.get('model'), usage=usage, raw_answer=content, judgment=judgment, assessment=score_judgment(packet, judgment))
        except Exception as ex:
            out.update(status='execution_error', error=str(ex).replace(key, '[REDACTED]')[:1500])
            with lock: ledger[lid]['status'] = 'provider_error_cost_unresolved'; write(led_path, ledger)
        out['finished_at'] = utc(); write(dest, out)
        with lock: print(json.dumps({'judged': row['id'], 'cond': cond, 'judge': jname, 'status': out['status'], 'spent': round(spent(), 3)}), flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex: list(ex.map(one, jobs))


def statuses(j):
    return {str(r.get('id')): ((r.get('honored') or {}).get('status'), (r.get('honored') or {}).get('severity')) for r in (j.get('judgment') or {}).get('requirements') or []}


def report():
    man = read(OUT / 'manifest.json'); led = read(OUT / 'ledger.json') if (OUT / 'ledger.json').exists() else []
    confirmed = {e['id']: e.get('human_confirmed') for e in EDITS['edits']}
    rep = {'at': utc(), 'cost_usd': round(sum(r.get('actual_cost_usd') or 0 for r in led), 4), 'per_judge': {}, 'rows': [],
           'edit_direction_human_confirmed': confirmed,
           'reading': 'S and R are computed only over pairs the judge originally passed. Collateral counts non-target requirements whose honored status changed; large collateral under PARAPHRASE means surface sensitivity. Results are provisional until every edit is human-confirmed. Target statuses are read from the returned judgment; strict quote validity is reported separately, as in the main study.'}
    strict_ok = {}
    excluded = {e['id'] for e in EDITS['edits'] if e.get('human_confirmed') is False}
    rep['excluded_edits_human'] = sorted(excluded)
    for jname in JUDGES:
        n = n_p = s_hit = s_unc = r_keep = 0; coll_b = coll_p = 0; flips_content = 0; invalid = 0
        orig_runs = {}
        for row in man['rows']:
            rid = row['requirement_id']; o = row['original_honored'].get(jname)
            # original full statuses for collateral
            op = V3 / 'judge_runs' / f"{row['run_id']}__{row['packet_version']}__{jname}.json"
            ost = statuses(read(op)) if op.exists() else {}
            line = {'id': row['id'], 'run_id': row['run_id'], 'requirement_id': rid, 'judge': jname, 'original': o}
            for cond in CONDITIONS:
                if row['id'] in excluded: line[cond] = 'excluded_by_human_confirmation'; continue
                p = OUT / 'runs' / f"{row['id']}__{cond}__{jname}.json"
                if not p.exists(): line[cond] = 'not_run'; continue
                j = read(p); st = statuses(j) if j.get('status') == 'received' else {}
                if not st or rid not in st:
                    line[cond] = j.get('status') if j.get('status') != 'received' else 'no_parseable_judgment'; invalid += 1; continue
                tgt = st.get(rid, (None, None))
                changed = [k for k in st if k != rid and k in ost and st[k][0] != ost[k][0]]
                # Target status is read from the judgment itself; strict evidence validity is reported beside it, as in the main study
                line[cond] = {'target_honored': tgt[0], 'target_severity': tgt[1], 'strict_evidence_valid': j['assessment']['status'] != 'invalid_grader_evidence',
                              'content_acceptable': j['assessment'].get('content_acceptable'), 'consequential': j['assessment'].get('consequential_error'), 'collateral_changed': changed}
                strict_ok[jname] = strict_ok.get(jname, 0) + (j['assessment']['status'] != 'invalid_grader_evidence')
                if o == 'pass':
                    if cond == 'break':
                        n += 1; s_hit += tgt[0] == 'fail'; s_unc += tgt[0] == 'uncertain'; coll_b += len(changed)
                    else:
                        n_p += 1; r_keep += tgt[0] == 'pass'; coll_p += len(changed)
            rep['rows'].append(line)
        rep['per_judge'][jname] = {'pairs_originally_passed_break_runs': n, 'paraphrase_runs': n_p, 'S_break_flipped_to_fail': s_hit, 'break_to_uncertain': s_unc,
                                   'R_paraphrase_stayed_pass': r_keep, 'collateral_changes_break': coll_b, 'collateral_changes_paraphrase': coll_p,
                                   'invalid_or_missing_responses': invalid, 'strict_evidence_valid_responses': strict_ok.get(jname, 0),
                                   'S': round(s_hit / n, 2) if n else None, 'R': round(r_keep / n_p, 2) if n_p else None}
    write(OUT / 'report.json', rep); print(json.dumps(rep['per_judge'], indent=1)); print('cost', rep['cost_usd'])


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('build'); jd = sub.add_parser('judge'); jd.add_argument('--max-usd', type=float, default=12.0); jd.add_argument('--workers', type=int, default=4); sub.add_parser('report')
    a = p.parse_args(); {'build': build, 'judge': lambda: judge(a.max_usd, a.workers), 'report': report}[a.cmd]()
