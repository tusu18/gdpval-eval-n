"""Study v3 solver runner: resumable native-file episodes for Claude Sonnet 5.5 and Claude Opus 5.5.

Differences from run_native_models.py, each tied to a recorded failure:
  * transport retry with backoff (3 attempts) and a per-turn private checkpoint; a crashed or
    socket-failed episode resumes from its last completed turn instead of being lost
    (14/17 and 3/5 earlier non-submissions were provider/socket failures);
  * 16,000-token responses and a system addendum to build long documents in sections
    (supplier-exit hit the 10k limit in both paired versions);
  * spend guard, pinned provider, served provider logged, identical settings for both models.

Instances are read from data/study_v3/instances/*.json (same schema as evidence_upgrade_01 solver files).
Variants must be validated before they are placed there; this runner never edits a task.

  python3 scripts/run_study_v3.py                 # prepare + freeze; no API calls
  python3 scripts/run_study_v3.py --execute --workers 4 [--max-usd 70] [--only original|conflict|missing]
"""
import argparse, getpass, json, os, random, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from native_file_workflow import ROOT, NativeWorkspace, TOOLS, SYSTEM, initial_message, write, sha
from run_native_models import api, image_message

OUT = ROOT / 'output/study_v3'; CONFIG = ROOT / 'config/study_v3.json'; INST = ROOT / 'data/study_v3/instances'
LOCK = threading.Lock()
MODELS = ['anthropic/claude-sonnet-5.5', 'anthropic/claude-opus-5.5']
REPEATS = {'original': 2, 'conflict': 1, 'missing': 1}
SYSTEM_ADDENDUM = ('\nFor a document longer than about two pages, build it in sections across several tool calls and '
                   'revise the same filename; do not attempt the whole document in one response. Before submitting, '
                   'inspect every action table, exception clause and schedule you wrote against the governing rules you stated.')
TRANSIENT = ('timed out', 'timeout', 'connection', 'reset', 'socket', 'remote end closed', 'remotedisconnected',
             'http 502', 'http 503', 'http 504', 'http 529', 'temporarily', 'eof occurred')


def utc(): return datetime.now(timezone.utc).isoformat()


def prepare():
    if CONFIG.exists(): return json.loads(CONFIG.read_text())
    instances = sorted(INST.glob('*.json'))
    if not instances: raise SystemExit('No validated instances in data/study_v3/instances/. Validate variants first.')
    jobs = []
    for p in instances:
        t = json.loads(p.read_text()); variant = t['variant']
        for m in MODELS:
            for r in range(1, REPEATS[variant] + 1):
                jobs.append({'instance_id': t['instance_id'], 'family_id': t['family_id'], 'variant': variant, 'tier': t.get('tier', 'A'),
                             'model': m, 'repeat': r, 'run_id': f"{t['instance_id']}__{m.replace('/', '_')}__r{r}"})
    random.Random(20261105).shuffle(jobs)
    paths = list(instances) + [ROOT / 'scripts' / s for s in ('native_file_engine.mjs', 'native_file_workflow.py', 'run_native_models.py',
                                                              'workflow_workspace.py', 'run_study_v3.py', 'evidence_grader_v2.py')]
    cfg = {'id': 'study-v3', 'created_at': utc(), 'status': 'frozen_unrun', 'models': MODELS, 'repeats': REPEATS, 'jobs': jobs,
           'system': SYSTEM + SYSTEM_ADDENDUM, 'tools': TOOLS, 'max_turns': 16, 'max_tool_calls': 80, 'max_tokens': 16000,
           'reasoning_effort': 'high', 'max_request_bytes': 8000000, 'provider_price_ceiling_per_million': {'prompt': 10, 'completion': 50},
           'transport_retries': 3, 'input_hashes': {str(p.relative_to(ROOT)): sha(p) for p in paths}, 'seed': 20261105,
           'seed_scope': 'run order only', 'plan': 'docs/study_v3_plan.md',
           'interpretation': 'Pre-registered counts on 15 gold tasks in three occupations. No model ranking, rate or training claim.'}
    write(CONFIG, cfg); return cfg


def is_transient(e):
    s = str(e).lower(); return any(k in s for k in TRANSIENT) and 'http 4' not in s


def call_with_retry(key, body, record, cfg):
    for attempt in range(cfg['transport_retries']):
        try:
            return api(key, 'chat/completions', body)
        except Exception as e:
            record.setdefault('transport_events', []).append({'at': utc(), 'attempt': attempt + 1, 'error': str(e).replace(key, '[REDACTED]')[:300]})
            if not is_transient(e) or attempt == cfg['transport_retries'] - 1: raise
            time.sleep(5 * 2 ** attempt)


def ledger_add(run_id, turn):
    with LOCK:
        p = OUT / 'ledger.json'; led = json.loads(p.read_text()) if p.exists() else []
        led.append({'id': len(led), 'run_id': run_id, 'turn': turn, 'status': 'dispatched_cost_pending', 'started_at': utc(), 'actual_cost_usd': None})
        write(p, led); return len(led) - 1


def ledger_set(lid, **kw):
    with LOCK:
        p = OUT / 'ledger.json'; led = json.loads(p.read_text()); led[lid].update(kw); write(p, led)


def spent():
    p = OUT / 'ledger.json'
    return sum(r.get('actual_cost_usd') or 0 for r in json.loads(p.read_text())) if p.exists() else 0.0


def one(job, cfg, key, max_usd):
    dest = OUT / 'runs' / (job['run_id'] + '.json'); root = OUT / 'workspaces' / job['run_id']; ckpt = root / 'checkpoint.private.json'
    prior = json.loads(dest.read_text()) if dest.exists() else None
    if prior and prior.get('status') not in ('execution_error', 'running'): return prior
    if spent() >= max_usd: return {'run_id': job['run_id'], 'status': 'skipped_spend_guard'}
    task = json.loads((INST / (job['instance_id'] + '.json')).read_text())
    state_before = json.loads((root / 'state.json').read_text()) if (root / 'state.json').exists() else None
    env = NativeWorkspace(task, root)
    record = {**job, 'started_at': utc(), 'status': 'running', 'calls': [], 'tool_events': [], 'image_exposures': [], 'transport_events': [],
              'task_sha256': cfg['input_hashes'][f"data/study_v3/instances/{job['instance_id']}.json"], 'resumed_from_turn': None}
    messages = [{'role': 'system', 'content': cfg['system']}, {'role': 'user', 'content': initial_message(task)}]
    count, start_turn, pending = 0, 0, []
    if prior and ckpt.exists() and state_before:  # resume
        ck = json.loads(ckpt.read_text()); messages, count, start_turn, pending = ck['messages'], ck['count'], ck['turn'], ck.get('pending_images', [])
        env.files, env.events, env.submitted = state_before['files'], state_before['events'], state_before['submitted']; env._persist()
        record.update(calls=prior.get('calls', []), tool_events=env.events, transport_events=prior.get('transport_events', []),
                      resumed_from_turn=start_turn, previous_attempts=prior.get('previous_attempts', []) + [{k: prior.get(k) for k in ('started_at', 'finished_at', 'status', 'error')}])
    start = time.monotonic(); write(dest, record)
    try:
        for turn in range(start_turn, cfg['max_turns']):
            body = {'model': job['model'], 'messages': messages, 'tools': cfg['tools'], 'max_tokens': cfg['max_tokens'],
                    'reasoning': {'effort': cfg['reasoning_effort']},
                    'provider': {'allow_fallbacks': False, 'require_parameters': True, 'max_price': cfg['provider_price_ceiling_per_million']}}
            if len(json.dumps(body).encode()) > cfg['max_request_bytes']: raise ValueError('request_size_limit')
            lid = ledger_add(job['run_id'], turn)
            try:
                response = call_with_retry(key, body, record, cfg)
            except Exception as e:
                ledger_set(lid, status='provider_error_cost_unresolved', error=str(e).replace(key, '[REDACTED]')[:500]); raise
            usage = response.get('usage', {}); cost = usage.get('cost')
            ledger_set(lid, status='actual' if type(cost) in (float, int) and cost >= 0 else 'reported_cost_missing', actual_cost_usd=cost,
                       generation_id=response.get('id'), provider=response.get('provider'))
            env.acknowledge_images(pending); record['image_exposures'] += pending; pending = []
            message = response['choices'][0]['message']; calls = message.get('tool_calls') or []
            assistant = {'role': 'assistant', 'content': message.get('content')}
            for f in ('tool_calls', 'reasoning_details'):
                if message.get(f): assistant[f] = message[f]
            messages.append(assistant)
            record['calls'].append({'turn': turn, 'generation_id': response.get('id'), 'returned_model': response.get('model'), 'provider': response.get('provider'),
                                    'usage': usage, 'assistant_content': message.get('content'), 'tool_calls': calls, 'finish_reason': response['choices'][0].get('finish_reason')})
            if not calls:
                record['status'] = 'ended_without_submission'; break
            if len(calls) > 12 or count + len(calls) > cfg['max_tool_calls']: raise ValueError('tool_call_limit')
            for call in calls:
                count += 1
                try: args = json.loads(call['function']['arguments'])
                except (ValueError, TypeError): args = None
                reply = env.call(call['function']['name'], args)
                messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(reply, ensure_ascii=False)})
            if env.image_queue:
                messages.append(image_message(env.image_queue)); pending = env.image_queue; env.image_queue = []
            record['tool_events'] = env.events; write(dest, record)
            write(ckpt, {'turn': turn + 1, 'count': count, 'pending_images': pending, 'messages': messages})
            with LOCK: print(json.dumps({'run': job['run_id'], 'turn': turn + 1, 'tools': count, 'submitted': bool(env.submitted), 'spent': round(spent(), 2)}), flush=True)
            if env.submitted: record['status'] = 'submitted'; record['submission'] = env.submitted; break
        else: record['status'] = 'turn_limit'
    except Exception as e:
        record.update(status='execution_error', error=str(e).replace(key, '[REDACTED]')[:1500])
    record.update(tool_events=env.events, finished_at=utc(), elapsed_seconds=time.monotonic() - start,
                  reported_api_cost_usd=sum(c['usage'].get('cost') or 0 for c in record['calls']))
    write(dest, record); return record


def summary(cfg):
    rows = [json.loads(p.read_text()) for p in (OUT / 'runs').glob('*.json')] if (OUT / 'runs').exists() else []
    by = {}
    for r in rows: by.setdefault((r['model'], r['variant']), []).append(r.get('status'))
    out = {'planned': len(cfg['jobs']), 'attempted': len(rows), 'status_counts': {}, 'by_model_variant': {}, 'reported_api_cost_usd': round(spent(), 4),
           'resumed_episodes': sum(1 for r in rows if r.get('resumed_from_turn') is not None),
           'transport_retries': sum(len(r.get('transport_events', [])) for r in rows), 'interpretation': cfg['interpretation']}
    for r in rows: out['status_counts'][r.get('status')] = out['status_counts'].get(r.get('status'), 0) + 1
    for k, v in by.items(): out['by_model_variant'][f'{k[0]}|{k[1]}'] = {s: v.count(s) for s in set(v)}
    write(OUT / 'summary.json', out); print(json.dumps(out, indent=1))


def main():
    p = argparse.ArgumentParser(); p.add_argument('--execute', action='store_true'); p.add_argument('--workers', type=int, default=4)
    p.add_argument('--max-usd', type=float, default=70.0); p.add_argument('--only', choices=['original', 'conflict', 'missing'])
    a = p.parse_args(); cfg = prepare()
    for rel, digest in cfg['input_hashes'].items():
        if sha(ROOT / rel) != digest: raise ValueError('Frozen input changed: ' + rel)
    jobs = [j for j in cfg['jobs'] if not a.only or j['variant'] == a.only]
    if not a.execute:
        print(json.dumps({'prepared': len(cfg['jobs']), 'selected': len(jobs), 'paid_calls': 0})); summary(cfg); return
    key = os.environ.get('OPENROUTER_API_KEY') or getpass.getpass('OpenRouter API key (hidden, memory only): '); api(key, 'key')
    try:
        with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex: list(ex.map(lambda j: one(j, cfg, key, a.max_usd), jobs))
    finally: summary(cfg)


if __name__ == '__main__': main()
