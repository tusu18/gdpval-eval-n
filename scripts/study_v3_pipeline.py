"""Study v3 end-to-end pipeline, $10 OpenRouter budget.

Solvers run through the local Claude Code CLI (your subscription; no OpenRouter spend):
  claude -p ... --model sonnet|opus   in a per-run sandbox folder with reference files + outputs/.
Judges run through OpenRouter under a hard $10 guard: Gemini 4 Argon (primary) and GPT-6.1 Sol (secondary),
rubric v2 (scripts/evidence_grader_v2.py). Neither judge shares a family with the solvers.

  python3 scripts/study_v3_pipeline.py prepare            # instances + requirements; no model calls
  python3 scripts/study_v3_pipeline.py solve  --models sonnet opus --workers 2 [--only original|conflict]
  python3 scripts/study_v3_pipeline.py judge  --max-usd 10
  python3 scripts/study_v3_pipeline.py report

Check once: `claude --help` for the exact flag names of your CLI version (see CLAUDE_ARGS below).
"""
import argparse, getpass, hashlib, json, os, random, re, shutil, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_completion_and_pairs import api, read, write, sha, utc
from evidence_grader_v2 import unit_chars, JUDGE_INSTRUCTIONS_V2, build_packet, score_judgment

ROOT = Path(__file__).resolve().parents[1]; OUT = ROOT / 'output/study_v3'; INST = ROOT / 'data/study_v3/instances'; REQ = ROOT / 'data/study_v3/requirements'
STUDY_CONFIG = os.environ.get('STUDY_CONFIG', 'config/study_v3.proposed.json')  # v3.1: STUDY_CONFIG=config/study_v31.json
PROPOSAL = read(ROOT / STUDY_CONFIG); LOCK = threading.Lock()
SLICE = ROOT / (PROPOSAL.get('dataset', {}).get('slice_dir') or 'data/gdpval')
IS_V31 = 'v31' in STUDY_CONFIG
JUDGES = {'gemini': 'google/gemini-4-argon', 'sol': 'openai/gpt-6.1-sol'}
CLAUDE_MODELS = {'sonnet': 'sonnet', 'opus': 'opus'}  # Claude Code aliases; pin full ids here if your CLI needs them
CLAUDE_ARGS = ['--output-format', 'json', '--permission-mode', 'bypassPermissions']  # headless: any tool prompt would otherwise abort the run
def claude_args():
    h = subprocess.run(['claude', '--help'], capture_output=True, text=True).stdout
    extra = ['--max-turns', '40'] if '--max-turns' in h else []
    if '--permission-mode' not in h: return ['--output-format', 'json', '--dangerously-skip-permissions'] + extra
    return CLAUDE_ARGS + extra
CRITICAL = re.compile(r'\b(must|required?|approv|authori[sz]|only|before|not exceed|shall|cannot|never)\b', re.I)
SOLVER_PREAMBLE = ('You are an experienced professional completing a real work assignment. Work only inside this folder. '
    'Inputs: reference_files/ (original attachments), workspace/ (operations records; a registry says which record is operative; '
    'a newer draft is not approved), attachments/ (text extracts). Save every deliverable in outputs/ in the format the assignment asks for, '
    'using python-docx or openpyxl (install with pip if missing). There is no internet. Do not ask questions; state unresolved assumptions inside the '
    'deliverable where a professional would, and do not invent missing facts. Before finishing, re-read every action table, exception clause and '
    'schedule you wrote against the rules you stated and fix contradictions. When done, print DONE and list the files in outputs/.')


# v3.1 tier addenda. Tier A prompts are byte-identical to v3. Tier W replaces the no-internet sentence; P and D append one sentence.
TIER_ADDENDUM = {
    'P': ' For a PowerPoint deliverable use python-pptx (install with pip if missing).',
    'D': ' For a PDF deliverable write the PDF with a Python library such as reportlab or fpdf2 (install with pip if missing).',
    'W': ' This assignment requires public web research: use your web search and fetch tools, and cite every source URL with its retrieval date inside the deliverable.',
}


def solver_prompt(inst):
    tier = inst.get('preamble_tier', 'A'); pre = SOLVER_PREAMBLE
    if tier == 'W': pre = pre.replace(' There is no internet.', '')
    return pre + TIER_ADDENDUM.get(tier, '') + '\n\nASSIGNMENT:\n' + inst['prompt']


def prefix(tid): return tid[:8]


def prepare():
    tiers = {t['id_prefix']: t for t in PROPOSAL['tasks']}
    tasks = [json.loads(l) for l in (SLICE / 'solver/tasks.jsonl').read_text().split('\n') if l.strip()]  # split on newline only: prompts contain U+2028
    grader = {json.loads(l)['task_id']: json.loads(l) for l in (SLICE / 'grader/tasks.jsonl').read_text().split('\n') if l.strip()}
    made, skipped = [], []
    for t in tasks:
        p = prefix(t['task_id']); tier = tiers[p]['tier']
        snap = ROOT / 'data/study_v3/snapshots' / p
        if tier == 'C': skipped.append((p, 'pptx not supported')); continue  # v3 only; v3.1 runs PowerPoint as tier P
        if tier == 'B' and not snap.exists(): skipped.append((p, 'public-data snapshot missing: ' + str(snap.relative_to(ROOT)))); continue
        refs = ['research/' + r for r in t['reference_files']] + ([str(x.relative_to(ROOT)) for x in snap.glob('*')] if snap.exists() and tier == 'B' else [])
        for r in refs:
            if not (ROOT / r).exists(): raise SystemExit('missing reference ' + r)
        inst = {'instance_id': f'{p}__original', 'family_id': p, 'source_task_id': t['task_id'], 'occupation': t['occupation'], 'variant': 'original',
                'tier': tier, 'prompt': t['prompt'], 'reference_files': refs, 'attachments': {}, 'workspace': {}, 'deliverable_hint': tiers[p]['deliverable'],
                'adaptation': tiers[p].get('adaptation'), 'preamble_tier': tier if tier in TIER_ADDENDUM else 'A', 'new_occupation': bool(tiers[p].get('new'))}
        write(INST / (inst['instance_id'] + '.json'), inst); made.append(inst['instance_id'])
        # requirements from the dataset rubric; reviewable text file per task
        items = grader[t['task_id']].get('rubric_json'); items = json.loads(items) if isinstance(items, str) else items
        reqs = []
        for i, it in enumerate(items or []):
            text = it if isinstance(it, str) else (it.get('criterion') or it.get('text') or it.get('description') or json.dumps(it))
            reqs.append({'id': f'R{i+1:02d}', 'text': str(text)[:600], 'source_ids': ['request'], 'critical': bool(CRITICAL.search(str(text))),
                         'operative_sections': ['action tables and schedules', 'exception or provisional clauses', 'approval routing', 'companion files or sheets']})
        write(REQ / (p + '.json'), {'task_id': t['task_id'], 'basis': 'GDPval public rubric items; critical flag is a keyword heuristic to review', 'requirements': reqs})
    # reuse the five validated historical conflict variants
    for f in sorted((ROOT / 'data/evidence_upgrade_01/solver').glob('*__conflict.json')):
        src = read(f)
        if not src.get('source_task_id'): skipped.append((f.stem, 'authored family without a GDPval source task; not part of the gold slice')); continue
        p = prefix(src['source_task_id'])
        inst = {**{k: src[k] for k in ('instance_id', 'family_id', 'source_task_id', 'occupation', 'variant', 'prompt', 'attachments', 'workspace')},
                'tier': 'A', 'reference_files': [], 'reused_from': str(f.relative_to(ROOT)), 'family_prefix': p}
        inst['instance_id'] = f'{p}__conflict'; write(INST / (inst['instance_id'] + '.json'), inst); made.append(inst['instance_id'])
    write(OUT / ('prepare_summary_v31.json' if IS_V31 else 'prepare_summary.json'), {'study_config': STUDY_CONFIG, 'made': made, 'skipped': skipped, 'at': utc(), 'variant_proposals_pending_validation': 'data/study_v3/variants.proposed.json'})
    print(json.dumps({'instances': len(made), 'skipped': skipped}, indent=1))


def sandbox(inst, run_dir):
    for d in ('reference_files', 'workspace', 'attachments', 'outputs'): (run_dir / d).mkdir(parents=True, exist_ok=True)
    for r in inst['reference_files']: shutil.copy(ROOT / r if not Path(r).is_absolute() else r, run_dir / 'reference_files' / Path(r).name)
    for k, v in inst['workspace'].items(): (run_dir / 'workspace' / k.replace('/', '__')).write_text(v)
    for k, v in inst['attachments'].items(): (run_dir / 'attachments' / (Path(k).stem + '.txt')).write_text(v)
    (run_dir / 'TASK.md').write_text(inst['prompt'])


ART_CAP = 280000 if IS_V31 else None  # v3.1: output budget = largest output any judge read in study v3 (278k unit characters)
CREDIT = threading.Event()  # OpenRouter 402: out of credits or key limit; stop dispatching


def credit_error(msg):
    return 'HTTP 402' in msg or 'Prompt tokens limit exceeded' in msg


def packet_received(run_id, ver):
    return any((OUT / 'judge_runs' / f'{run_id}__{ver}__{j}.json').exists() and read(OUT / 'judge_runs' / f'{run_id}__{ver}__{j}.json').get('status') == 'received' for j in JUDGES)


LIMIT_RE = re.compile(r"hit your (session|usage|weekly) limit|usage limit|rate limit", re.I)
LIMIT = threading.Event()


def hit_limit(rec):
    """The Claude Code subscription ran out mid-run: not an attempt by the model, so it is retried, never scored."""
    return bool(LIMIT_RE.search(rec.get('final_message') or '') or LIMIT_RE.search(rec.get('stdout_tail') or ''))


def archive_attempt(run_id, old, run_dir):
    """Keep a failed or cut-off attempt for the record and give the retry a clean sandbox."""
    fdir = OUT / 'solver_runs_failed'; cdir = OUT / 'claudecode_failed'; fdir.mkdir(exist_ok=True); cdir.mkdir(exist_ok=True)
    n = len(list(fdir.glob(run_id + '__a*.json'))) + 1
    write(fdir / f'{run_id}__a{n}.json', old)
    if run_dir.exists(): shutil.move(str(run_dir), str(cdir / f'{run_id}__a{n}'))


def solve_one(job):
    inst = read(INST / (job['instance_id'] + '.json')); run_dir = OUT / 'claudecode' / job['run_id']; rec_path = OUT / 'solver_runs' / (job['run_id'] + '.json')
    if LIMIT.is_set(): return  # usage limit reached earlier in this pass: leave the rest for the next pass
    if rec_path.exists():
        old = read(rec_path)
        if old.get('status') == 'submitted' and not hit_limit(old): return  # done
        archive_attempt(job['run_id'], old, run_dir); rec_path.unlink()  # no_outputs, timeouts, errors and cut-off runs are retried
    sandbox(inst, run_dir)
    prompt = solver_prompt(inst)
    cmd = ['claude', '-p', prompt, '--model', CLAUDE_MODELS[job['model']]] + ARGS
    rec = {**job, 'started_at': utc(), 'status': 'running', 'timeout_s': int(os.environ.get('STUDY_V3_TIMEOUT', '1800')), 'command': cmd[:1] + ['-p', '<prompt>'] + cmd[3:]}; write(rec_path, rec)
    try:
        p = subprocess.run(cmd, cwd=run_dir, capture_output=True, text=True, timeout=int(os.environ.get('STUDY_V3_TIMEOUT', '1800')), env={**os.environ, 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1'})
        rec['exit_code'] = p.returncode; rec['stderr_tail'] = p.stderr[-1500:]
        try:
            res = json.loads(p.stdout); rec['claude_result'] = {k: res.get(k) for k in ('total_cost_usd', 'num_turns', 'duration_ms', 'session_id', 'is_error', 'subtype')}
            rec['final_message'] = str(res.get('result'))[:4000]; rec['claude_raw'] = {k: (str(v)[:1500] if not isinstance(v, (int, float, bool)) else v) for k, v in res.items() if k != 'result'}
        except ValueError: rec['stdout_tail'] = p.stdout[-3000:]
    except subprocess.TimeoutExpired: rec['status'] = 'timeout'
    files = [f for f in (run_dir / 'outputs').glob('*') if f.is_file()]
    rec['outputs'] = [{'name': f.name, 'sha256': sha(f), 'bytes': f.stat().st_size} for f in files]
    if rec['status'] != 'timeout': rec['status'] = 'usage_limit' if hit_limit(rec) else ('submitted' if files else 'no_outputs')
    rec['finished_at'] = utc(); write(rec_path, rec)
    with LOCK: print(json.dumps({'run': job['run_id'], 'status': rec['status'], 'files': [f.name for f in files]}), flush=True)
    if rec['status'] == 'usage_limit' and not LIMIT.is_set():
        LIMIT.set(); print(json.dumps({'stopped': 'Claude Code usage limit: ' + (rec.get('final_message') or '')[:120], 'resume': 'run the same command after the reset; finished runs are kept'}), flush=True)


ARGS = CLAUDE_ARGS


def solve(models, workers, only, repeat=1):
    global ARGS; ARGS = claude_args(); print(json.dumps({'claude_args': ARGS}), flush=True)
    insts = sorted(INST.glob('*.json'))
    jobs = [{'instance_id': i.stem, 'model': m, 'repeat': repeat, 'run_id': f'{i.stem}__{m}__r{repeat}', 'variant': read(i)['variant']} for i in insts for m in models]
    jobs = [j for j in jobs if not only or j['variant'] == only]; random.Random(20261105).shuffle(jobs)
    write(OUT / ('solver_jobs.json' if repeat == 1 else f'solver_jobs_r{repeat}.json'), {'jobs': jobs, 'at': utc(), 'harness': 'Claude Code CLI headless; subscription billing; see CLAUDE_ARGS'})
    with ThreadPoolExecutor(max_workers=workers) as ex: list(ex.map(solve_one, jobs))
    if LIMIT.is_set(): sys.exit(3)


def judge(max_usd, workers=1, repeat=None, only_judges=None, sample_only_for=(), max_pass_usd=None):
    key = os.environ.get('OPENROUTER_API_KEY') or getpass.getpass('OpenRouter API key (hidden, memory only): '); api(key, 'key')
    led_path = OUT / 'judge_ledger.json'; ledger = read(led_path) if led_path.exists() else []
    def spent(): return sum(r.get('actual_cost_usd') or 0 for r in ledger)
    runs = [r for r in (read(p) for p in sorted((OUT / 'solver_runs').glob('*.json'))) if r.get('status') == 'submitted' and not hit_limit(r)
            and (repeat is None or r['run_id'].endswith(f'__r{repeat}'))]  # --repeat keeps r1 judging from spending r2's budget
    # Budget rule ($10): one call per output on a selected requirement subset. 20-item chunks truncated at 16k tokens at $0.19/call.
    CAP = 10; OPERATIVE = re.compile(r'\b(recommend|decision|action|plan|schedule|timeline|approv|authori|cost|total|quantit|calculat|exception|release|hold|owner|deadline|threshold)', re.I)
    work = []
    for r in runs:
        inst = read(INST / (r['instance_id'] + '.json'))
        rq = REQ / ((inst.get('family_prefix') or inst['family_id']) + '.json'); reqs = read(rq)['requirements']
        crit = [q for q in reqs if q['critical']]; rest = sorted([q for q in reqs if not q['critical']], key=lambda q: -len(OPERATIVE.findall(q['text'])))
        sel = (crit + rest)[:CAP]
        arts = [str(OUT / 'claudecode' / r['run_id'] / 'outputs' / o['name']) for o in r['outputs'] if o['name'].lower().endswith(('.docx', '.xlsx', '.pptx', '.pdf'))]
        if not arts: write(OUT / 'judge_runs' / (r['run_id'] + '__skip.json'), {'run_id': r['run_id'], 'status': 'no_native_artifact'}); continue
        refs = [str(ROOT / x) if not Path(x).is_absolute() else x for x in inst.get('reference_files', [])]
        ver = 'sel2' if refs else 'sel'  # sel2: packet carries the reference-file text the first pass omitted; reference-free runs keep their sel results
        packet_path = OUT / 'judge_packets' / f"{r['run_id']}__{ver}.json"
        rebuild = not packet_path.exists()
        if not rebuild and ART_CAP and not packet_received(r['run_id'], ver):  # an over-budget packet nobody has judged yet is rebuilt under the budget
            old = read(packet_path); rebuild = 'artifact_budget' not in old and unit_chars(old['artifacts']) > ART_CAP
        if rebuild:
            pk = build_packet(inst, sel, arts, trace=[{'final_message': r.get('final_message', '')[:2000]}], engineering_checks={'files': r['outputs']}, reference_paths=refs, max_total_ref_chars=240000, max_artifact_unit_chars=ART_CAP)
            pk['selection'] = {'judged': len(sel), 'of': len(reqs), 'rule': 'all heuristic-critical items, then operative-keyword rank, cap 10; full rubric deferred for cost', 'reference_files_included': [Path(x).name for x in refs]}
            write(packet_path, pk)
        work.append((r, ver, packet_path))
    sample = set(read(OUT / 'calibration_set_v31.json')['selected']) if sample_only_for else set()
    jobs = [(jname, model, r, c, packet_path) for jname, model in JUDGES.items() if not only_judges or jname in only_judges for r, c, packet_path in work
            if jname not in sample_only_for or r['run_id'] in sample]  # cost control: some judges only on the frozen human-review sample  # primary judge's jobs are queued first
    def one(job):
        jname, model, r, c, packet_path = job
        dest = OUT / 'judge_runs' / f"{r['run_id']}__{c}__{jname}.json"
        if dest.exists() and read(dest).get('status') == 'received': return
        if CREDIT.is_set(): return
        with LOCK:
            if spent() >= max_usd or (max_pass_usd is not None and spent() - start_spent >= max_pass_usd): print(json.dumps({'halt': f'spend guard: this pass ${spent() - start_spent:.2f} (limit {max_pass_usd}), all-time ${spent():.2f} (limit {max_usd})'}), flush=True); return
            lid = len(ledger); ledger.append({'run_id': r['run_id'], 'chunk': c, 'judge': jname, 'status': 'dispatched_cost_pending', 'actual_cost_usd': None}); write(led_path, ledger)
        packet = read(packet_path)
        payload = {k: v for k, v in packet.items() if k not in ('limitations', 'selection', 'artifact_budget')}
        body = {'model': model, 'messages': [{'role': 'system', 'content': JUDGE_INSTRUCTIONS_V2 + '\nBe concise: one or two evidence objects per check, short rationales.'}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
                'max_tokens': 12000, 'reasoning': {'effort': 'medium'}, 'response_format': {'type': 'json_object'},
                'provider': {'allow_fallbacks': False, 'require_parameters': True, 'max_price': {'prompt': 10, 'completion': 50}}}
        row = {'run_id': r['run_id'], 'chunk': c, 'judge': jname, 'model': model, 'started_at': utc(), 'status': 'running',
               'artifact_budget': {k: v for k, v in (packet.get('artifact_budget') or {}).items() if k != 'artifacts'} | {'files': (packet.get('artifact_budget') or {}).get('artifacts')}}
        try:
            resp = api(key, 'chat/completions', body); usage = resp.get('usage', {}); cost = usage.get('cost')
            with LOCK: ledger[lid].update(status='actual' if isinstance(cost, (int, float)) and cost >= 0 else 'reported_cost_missing', actual_cost_usd=cost, generation_id=resp.get('id')); write(led_path, ledger)
            content = resp['choices'][0]['message']['content']
            try: judgment = json.loads(content)
            except ValueError: judgment = {}
            row.update(status='received', returned_model=resp.get('model'), usage=usage, raw_answer=content, judgment=judgment, assessment=score_judgment(packet, judgment))
        except Exception as e:
            row.update(status='execution_error', error=str(e).replace(key, '[REDACTED]')[:1500])
            with LOCK: ledger[lid]['status'] = 'provider_error_cost_unresolved'; write(led_path, ledger)
            if credit_error(row['error']): CREDIT.set()
        row['finished_at'] = utc(); write(dest, row)
        with LOCK:
            print(json.dumps({'judged': r['run_id'], 'judge': jname, 'status': row['status'], 'spent': round(spent(), 3)} | ({'error': row['error'][:160]} if row['status'] != 'received' else {})), flush=True)
            tally[row['status']] = tally.get(row['status'], 0) + 1
    tally = {}
    start_spent = spent()
    with ThreadPoolExecutor(max_workers=workers) as ex: list(ex.map(one, jobs))
    left = sum(1 for jname, _, r, c, _ in jobs if not ((OUT / 'judge_runs' / f"{r['run_id']}__{c}__{jname}.json").exists() and read(OUT / 'judge_runs' / f"{r['run_id']}__{c}__{jname}.json").get('status') == 'received'))
    print(json.dumps({'this_pass': tally, 'still_unjudged': left, 'spent_this_pass': round(spent() - start_spent, 2), 'spent_total': round(spent(), 2)}), flush=True)
    if CREDIT.is_set():
        print(json.dumps({'stopped': 'OpenRouter returned 402: out of credits or the key has hit its spending limit. Add credits and raise or remove the key limit, then re-run the same phase.'}), flush=True); sys.exit(5)
    errs = tally.get('execution_error', 0)
    if errs and errs > 0.2 * sum(tally.values()): sys.exit(4)  # pre-registered stop rule: transport failures above 20%

def report():
    solver = [read(p) for p in sorted((OUT / 'solver_runs').glob('*.json'))]
    latest = {}  # per (run, judge) keep sel2 over sel; chunk attempts (c0..c3) are superseded; all costs stay in the ledger
    for p in sorted((OUT / 'judge_runs').glob('*__sel*__*.json')):
        j = read(p); k = (j['run_id'], j['judge']); ver = p.name.split('__')[-2]
        if k not in latest or ver > latest[k][0]: latest[k] = (ver, j)
    judged = [v[1] for v in latest.values()]
    led = read(OUT / 'judge_ledger.json') if (OUT / 'judge_ledger.json').exists() else []
    out = {'at': utc(), 'solver': {'runs': len(solver), 'status': {}, 'by_model_variant': {}, 'claude_code_reported_cost_usd': round(sum((r.get('claude_result') or {}).get('total_cost_usd') or 0 for r in solver), 4)},
           'judge': {'responses': len(judged), 'openrouter_cost_usd': round(sum(r.get('actual_cost_usd') or 0 for r in led), 4), 'per_judge': {}, 'disagreements': []}, 'human_review_sample': []}
    for r in solver:
        out['solver']['status'][r['status']] = out['solver']['status'].get(r['status'], 0) + 1
        k = f"{r['model']}|{r['variant']}"; out['solver']['by_model_variant'].setdefault(k, {}); out['solver']['by_model_variant'][k][r['status']] = out['solver']['by_model_variant'][k].get(r['status'], 0) + 1
    from judge_aggregation_v5 import aggregate
    summary = aggregate(judged)
    out['judge']['endpoint_analysis_v5'] = summary
    out['judge']['per_judge'] = summary['per_judge']
    out['judge']['agreement'] = summary['comparisons']
    out['judge']['disagreements'] = {k:v['disagreements'] for k,v in summary['comparisons'].items()}
    # Queue selection is explicit and does not impute missing votes as passes.
    flagged = [r for r,v in summary['per_run'].items() if any(x['consequential_error'] is True for x in v.values())]
    passed = [r for r,v in summary['per_run'].items() if len(v)==len(JUDGES) and all(x['content_acceptable'] is True for x in v.values())]
    rnd = random.Random(20261105)
    out['human_review_sample'] = sorted(rnd.sample(flagged,min(10,len(flagged))) + rnd.sample(passed,min(10,len(passed))))
    out['interpretation'] = 'Counts on a 13-15 task slice; judge agreement is not validity; human labels on human_review_sample decide false accepts and missed errors.'
    write(OUT / 'report.json', out); print(json.dumps(out, indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True); sub.add_parser('prepare')
    s = sub.add_parser('solve'); s.add_argument('--models', nargs='+', default=['sonnet', 'opus'], choices=list(CLAUDE_MODELS)); s.add_argument('--workers', type=int, default=2); s.add_argument('--only', choices=['original', 'conflict']); s.add_argument('--repeat', type=int, default=1, help='repeat index; r2 = second independent attempt per instance')
    jd = sub.add_parser('judge'); jd.add_argument('--max-usd', type=float, default=10.0); jd.add_argument('--workers', type=int, default=1); jd.add_argument('--repeat', type=int, help='judge only this repeat index'); jd.add_argument('--judges', nargs='+', choices=list(JUDGES), help='run only these judges (cost control)'); jd.add_argument('--max-pass-usd', type=float, help='stop once this pass has spent this much (counts only this run, not earlier spend)'); jd.add_argument('--sample-only-for', nargs='+', default=[], choices=list(JUDGES), help='these judges grade only the frozen random human-review sample'); sub.add_parser('report')
    a = p.parse_args()
    {'prepare': lambda: prepare(), 'solve': lambda: solve(a.models, a.workers, a.only, a.repeat), 'judge': lambda: judge(a.max_usd, a.workers, a.repeat, a.judges, tuple(a.sample_only_for), a.max_pass_usd), 'report': lambda: report()}[a.cmd]()
