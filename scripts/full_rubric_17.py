"""Full-rubric check on human-confirmed errors: did the 10-item cap hide or invent anything?

For every follow-up output a blind reviewer labeled consequential_error=yes, judge ALL rubric requirements (chunks of 10,
same instructions, same packet builder, same judges) and compare with the capped run: max severity, honored fails,
stated-but-not-honored count, and whether the capped verdict would change.

  python3 scripts/full_rubric_17.py judge --max-usd 30 --workers 2
  python3 scripts/full_rubric_17.py report
"""
import argparse, getpass, json, os, re, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys; sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_completion_and_pairs import api, read, write, utc
from evidence_grader_v2 import JUDGE_INSTRUCTIONS_V2, build_packet, score_judgment

ROOT = Path(__file__).resolve().parents[1]; V3 = ROOT / 'output/study_v3'; OUT = ROOT / 'output/full_rubric_17'
INST = ROOT / 'data/study_v3/instances'; REQ = ROOT / 'data/study_v3/requirements'
JUDGES = {'gemini': 'google/gemini-4-argon', 'sol': 'openai/gpt-6.1-sol'}; CHUNK = 10; LOCK = threading.Lock()


def targets():
    hr = V3 / 'human_reviews_v3.json'
    return [r['run_id'] for r in read(hr)['reviews'] if r['consequential_error'] == 'yes' and ((not r.get('label_author') and 'automated' not in (r.get('review_method') or '').lower()) or (r.get('verified_by') and r.get('verified_at')))] if hr.exists() else []


CREDIT = threading.Event()


def judge(max_usd, workers):
    key = os.environ.get('OPENROUTER_API_KEY') or getpass.getpass('OpenRouter API key (hidden, memory only): '); api(key, 'key')
    (OUT / 'runs').mkdir(parents=True, exist_ok=True); (OUT / 'packets').mkdir(exist_ok=True)
    led_path = OUT / 'ledger.json'; ledger = read(led_path) if led_path.exists() else []
    def spent(): return sum(x.get('actual_cost_usd') or 0 for x in ledger)
    jobs = []
    for run in targets():
        r = read(V3 / 'solver_runs' / f'{run}.json'); inst = read(INST / (r['instance_id'] + '.json'))
        reqs = read(REQ / ((inst.get('family_prefix') or inst['family_id']) + '.json'))['requirements']
        arts = [str(V3 / 'claudecode' / run / 'outputs' / o['name']) for o in r['outputs'] if o['name'].lower().endswith(('.docx', '.xlsx', '.pptx', '.pdf'))]
        refs = [str(ROOT / x) for x in inst.get('reference_files', [])]
        for k in range(0, len(reqs), CHUNK):
            pp = OUT / 'packets' / f'{run}__full{k // CHUNK:02d}.json'
            if not pp.exists():
                pk = build_packet(inst, reqs[k:k + CHUNK], arts, trace=[{'final_message': r.get('final_message', '')[:2000]}], engineering_checks={'files': r['outputs']}, reference_paths=refs, max_total_ref_chars=240000, max_artifact_unit_chars=280000)
                write(pp, pk)
            for j, m in JUDGES.items(): jobs.append((run, k // CHUNK, j, m, pp))
    def one(job):
        run, c, j, m, pp = job; dest = OUT / 'runs' / f'{run}__full{c:02d}__{j}.json'
        if dest.exists() and read(dest).get('status') == 'received': return
        if CREDIT.is_set(): return
        with LOCK:
            if spent() >= max_usd: print(json.dumps({'halt': f'spend guard ${spent():.2f}'}), flush=True); return
            lid = len(ledger); ledger.append({'run_id': run, 'chunk': c, 'judge': j, 'status': 'dispatched_cost_pending', 'actual_cost_usd': None}); write(led_path, ledger)
        packet = read(pp); payload = {k: v for k, v in packet.items() if k not in ('limitations', 'selection', 'artifact_budget')}
        body = {'model': m, 'messages': [{'role': 'system', 'content': JUDGE_INSTRUCTIONS_V2 + '\nBe concise: one or two evidence objects per check, short rationales.'}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
                'max_tokens': 12000, 'reasoning': {'effort': 'medium'}, 'response_format': {'type': 'json_object'},
                'provider': {'allow_fallbacks': False, 'require_parameters': True, 'max_price': {'prompt': 10, 'completion': 50}}}
        row = {'run_id': run, 'chunk': c, 'judge': j, 'started_at': utc(), 'status': 'running'}
        try:
            resp = api(key, 'chat/completions', body); cost = resp.get('usage', {}).get('cost')
            with LOCK: ledger[lid].update(status='actual', actual_cost_usd=cost); write(led_path, ledger)
            content = resp['choices'][0]['message']['content']
            try: jd = json.loads(content)
            except ValueError: jd = {}
            row.update(status='received', raw_answer=content, judgment=jd, assessment=score_judgment(packet, jd))
        except Exception as e:
            row.update(status='execution_error', error=str(e).replace(key, '[REDACTED]')[:1500])
            with LOCK: ledger[lid]['status'] = 'provider_error_cost_unresolved'; write(led_path, ledger)
            if 'HTTP 402' in row['error'] or 'Prompt tokens limit exceeded' in row['error']: CREDIT.set()
        write(dest, row)
        with LOCK: print(json.dumps({'run': run, 'chunk': c, 'judge': j, 'status': row['status'], 'spent': round(spent(), 3)} | ({'error': row['error'][:160]} if row['status'] != 'received' else {})), flush=True)
    with ThreadPoolExecutor(max_workers=workers) as ex: list(ex.map(one, jobs))
    if CREDIT.is_set():
        print(json.dumps({'stopped': 'OpenRouter returned 402: out of credits or key limit reached.'}), flush=True); sys.exit(5)


def stats(judgments):
    fails = []; sbnh = 0
    for jd in judgments:
        for x in (jd.get('requirements') or []):
            h = x.get('honored') or {}
            if h.get('status') == 'fail':
                fails.append(int(h.get('severity') or 0)); sbnh += (x.get('stated') or {}).get('status') == 'pass'
    return {'honored_fails': len(fails), 'max_severity': max(fails) if fails else 0, 'stated_not_honored': sbnh}


def report():
    rows = []
    for run in targets():
        for j in JUDGES:
            capped = sorted(V3.glob(f'judge_runs/{run}__sel*__{j}.json'))
            cap = read(capped[-1]) if capped else {}
            full = [read(f) for f in sorted((OUT / 'runs').glob(f'{run}__full*__{j}.json'))]
            rows.append({'run_id': run, 'judge': j, 'chunks_received': sum(f.get('status') == 'received' for f in full), 'chunks': len(full),
                         'capped': stats([cap.get('judgment') or {}]), 'full': stats([f.get('judgment') or {} for f in full if f.get('status') == 'received'])})
    for r in rows: r['verdict_changes'] = (r['capped']['max_severity'] >= 4) != (r['full']['max_severity'] >= 4)
    led = read(OUT / 'ledger.json') if (OUT / 'ledger.json').exists() else []
    out = {'at': utc(), 'cost_usd': round(sum(x.get('actual_cost_usd') or 0 for x in led), 2), 'rows': rows,
           'reading': 'verdict_changes = the severity>=4 call differs between the 10-item capped run and the full rubric. Full-rubric fails >= capped fails is expected (more items checked).'}
    write(OUT / 'report.json', out); print(json.dumps(out, indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); s = p.add_subparsers(dest='cmd', required=True)
    j = s.add_parser('judge'); j.add_argument('--max-usd', type=float, default=30); j.add_argument('--workers', type=int, default=2); s.add_parser('report')
    a = p.parse_args(); {'judge': lambda: judge(a.max_usd, a.workers), 'report': report}[a.cmd]()
