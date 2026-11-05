"""Blind human-review kit for the follow-up run, plus second-reviewer agreement.

  python3 scripts/human_review_kit.py select     # freeze calibration_set_v2: 11 more outputs, stratified by judge verdict, seed 20261105
  python3 scripts/human_review_kit.py packets    # write blind packets (request, sources, full output text; NO judge text) for all 14
  python3 scripts/human_review_kit.py record --run <run_id> --reviewer <id> --acceptable yes|no|uncertain \
          --consequential yes|no|uncertain --defect yes|no|uncertain --minutes 6 --output-evidence "..." --source-evidence "..." [--note "..."]
  python3 scripts/human_review_kit.py kappa --a output/study_v3/human_reviews_v3.json --b output/study_v3/human_reviews_v3_reviewer2.json

Selection rule (fixed before labels): from the outputs not yet reviewed, take every output neither judge flagged, then
split the rest between 'both judges flagged' and 'Sol-only' in proportion, balancing Sonnet/Opus; deterministic seed.
Packets never contain judge output. Reviewers answer three endpoints before seeing any judge text.
"""
import argparse, glob, json, os, random, re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; V3 = ROOT / 'output/study_v3'
read = lambda p: json.loads(Path(p).read_text())
utc = lambda: datetime.now(timezone.utc).isoformat(timespec='seconds')
TARGET = 11; SEED = 20261105
QUESTIONS = ['content_acceptable: Is the output usable for the stated purpose without substantive correction? yes / no / uncertain',
             'consequential_error: Does it contain an error that would lead to a wrong decision, unauthorized action or material loss if acted on? yes / no / uncertain (if yes: quote the output line and the source line)',
             'evaluation_defect: Is there an unresolved problem in the request or source material that prevents a fair judgment? yes / no / uncertain']


def latest_judge():
    latest = {}
    for p in sorted((V3 / 'judge_runs').glob('*__sel*__*.json')):
        j = read(p); k = (j['run_id'], j['judge']); ver = os.path.basename(p).split('__')[-2]
        if k not in latest or ver > latest[k][0]: latest[k] = (ver, j)
    flags = {}
    for (run, judge), (ver, j) in latest.items():
        reqs = (j.get('judgment') or {}).get('requirements') or []
        if j.get('status') != 'received' or not reqs: continue
        flags.setdefault(run, {})[judge] = any((x.get('honored') or {}).get('status') == 'fail' for x in reqs)
        flags[run][judge + '_ver'] = ver
    return flags


def select():
    done = {r['run_id'] for r in read(V3 / 'human_reviews_v3.json')['reviews']}
    flags = latest_judge(); strata = {'neither': [], 'both': [], 'sol_only': [], 'gemini_only': []}
    for run, f in sorted(flags.items()):
        if run in done or 'gemini' not in f or 'sol' not in f: continue
        key = 'both' if f['gemini'] and f['sol'] else 'sol_only' if f['sol'] else 'gemini_only' if f['gemini'] else 'neither'
        strata[key].append(run)
    rnd = random.Random(SEED); chosen = list(strata['neither'])
    pool = {k: sorted(v) for k, v in strata.items() if k in ('both', 'sol_only')}
    remaining = TARGET - len(chosen); total = sum(len(v) for v in pool.values())
    quota = {k: round(remaining * len(v) / total) for k, v in pool.items()} if total else {}
    while sum(quota.values()) > remaining: quota[max(quota, key=quota.get)] -= 1
    while sum(quota.values()) < remaining: quota[min(quota, key=quota.get)] += 1
    for k, v in pool.items():
        by_model = {'sonnet': [r for r in v if '__sonnet__' in r], 'opus': [r for r in v if '__opus__' in r]}
        for m in by_model.values(): rnd.shuffle(m)
        pick = []
        while len(pick) < quota[k] and (by_model['sonnet'] or by_model['opus']):
            for m in ('sonnet', 'opus'):
                if by_model[m] and len(pick) < quota[k]: pick.append(by_model[m].pop())
        chosen += pick
    out = {'frozen_at': utc(), 'seed': SEED, 'rule': 'all unflagged outputs, then proportional split of both-flagged and Sol-only, Sonnet/Opus balanced; chosen before any label',
           'already_reviewed': sorted(done), 'strata_sizes': {k: len(v) for k, v in strata.items()}, 'quota': quota, 'selected': sorted(chosen),
           'judge_flags': {r: {k: flags[r][k] for k in ('gemini', 'sol')} for r in chosen}}
    (V3 / 'calibration_set_v2.json').write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))


def packets():
    sel = read(V3 / 'calibration_set_v2.json'); flags = latest_judge(); outdir = V3 / 'review_v2'; outdir.mkdir(exist_ok=True)
    for i, run in enumerate(sel['selected'], 1):
        ver = flags[run].get('gemini_ver') or flags[run].get('sol_ver'); pk = read(V3 / 'judge_packets' / f'{run}__{ver}.json')
        md = [f'# Blind review packet {i:02d} of {len(sel["selected"])}', '', f'Case: `{run}` · solver: {"Claude Opus 5.5" if "__opus__" in run else "Claude Sonnet 5.5"} · variant: {run.split("__")[1]}', '',
              'Read the request, the sources and the complete output. Answer the three questions before looking at any judge output. Record minutes.', '']
        md += ['## Questions', ''] + [f'{n}. {q}' for n, q in enumerate(QUESTIONS, 1)] + ['', '---', '', '## Request', '', pk['source_documents'].get('request', ''), '']
        for k, v in pk['source_documents'].items():
            if k == 'request': continue
            md += [f'## Source: {k}', '', '```', str(v)[:60000], '```', '']
        for a in pk['artifacts']:
            md += [f'## Output file: {a["id"]}', '', '```', a.get('text', '')[:80000], '```', '']
        md += ['---', '', '## Answer (copy into the record command)', '', f'python3 scripts/human_review_kit.py record --run {run} --reviewer <you> --acceptable ? --consequential ? --defect ? --minutes ? --output-evidence "<exact output line>" --source-evidence "<exact source line>" --note "<one sentence>"', '']
        (outdir / f'{i:02d}__{run}.md').write_text('\n'.join(md))
    print('wrote', len(sel['selected']), 'packets to', outdir.relative_to(ROOT))


def record(a):
    path = V3 / ('human_reviews_v3.json' if a.reviewer in ('project_owner_chat', 'owner') else f'human_reviews_v3_{a.reviewer}.json')
    doc = read(path) if path.exists() else {'schema': 'study-v3-human-reviews-v1', 'reviewer': a.reviewer, 'recorded_at': utc(),
                                             'method': 'Blind packet (request, sources, complete output text; no judge text) read before verdict. Minutes are reviewer estimates.', 'reviews': []}
    if any(r['run_id'] == a.run for r in doc['reviews']): raise SystemExit(f'{a.run} already recorded for {a.reviewer}; edit the file to supersede')
    if a.consequential == 'yes' and not (a.output_evidence and a.source_evidence): raise SystemExit('a consequential error needs both --output-evidence and --source-evidence')
    doc['reviews'].append({'run_id': a.run, 'content_acceptable': a.acceptable, 'consequential_error': a.consequential, 'evaluation_defect': a.defect,
                           'review_minutes': a.minutes, 'output_evidence': a.output_evidence, 'source_evidence': a.source_evidence, 'reviewer_note': a.note,
                           'recorded_at': utc(), 'blinding': 'judge text withheld until after this record was written'})
    n = len(doc['reviews']); doc['summary'] = {'reviewed': n, 'consequential_errors': sum(r['consequential_error'] == 'yes' for r in doc['reviews'])}
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n'); print('recorded', a.run, '->', path.relative_to(ROOT), f'({n} reviews)')


def kappa(a):
    A = {r['run_id']: r for r in read(a.a)['reviews']}; B = {r['run_id']: r for r in read(a.b)['reviews']}
    shared = sorted(set(A) & set(B)); out = {'shared_cases': len(shared), 'endpoints': {}}
    rnd = random.Random(SEED)
    for ep in ('content_acceptable', 'consequential_error', 'evaluation_defect'):
        pairs = [(A[r][ep], B[r][ep]) for r in shared]
        def k_of(ps):
            n = len(ps); po = sum(x == y for x, y in ps) / n
            labels = {x for p in ps for x in p}; pe = sum((sum(x == l for x, _ in ps) / n) * (sum(y == l for _, y in ps) / n) for l in labels)
            return po, (None if pe == 1 else (po - pe) / (1 - pe))
        po, k = k_of(pairs)
        boots = [k_of([pairs[rnd.randrange(len(pairs))] for _ in pairs])[1] for _ in range(2000)] if len(pairs) >= 4 else []
        boots = sorted(b for b in boots if b is not None)
        out['endpoints'][ep] = {'observed_agreement': round(po, 3), 'cohen_kappa': None if k is None else round(k, 3),
                                'kappa_95ci_bootstrap': [round(boots[int(0.025 * len(boots))], 3), round(boots[int(0.975 * len(boots))], 3)] if boots else None,
                                'matrix': {f'{x}|{y}': sum(1 for p in pairs if p == (x, y)) for x in ('yes', 'no', 'uncertain') for y in ('yes', 'no', 'uncertain') if any(p == (x, y) for p in pairs)},
                                'disagreements': [r for r in shared if A[r][ep] != B[r][ep]]}
    out['reading'] = 'Small n: report κ with its interval and the raw matrix; disagreements are adjudicated, not averaged.'
    (V3 / 'reviewer_agreement.json').write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True); sub.add_parser('select'); sub.add_parser('packets')
    r = sub.add_parser('record')
    for k in ('run', 'reviewer', 'acceptable', 'consequential', 'defect'): r.add_argument('--' + k, required=True)
    r.add_argument('--minutes', type=float); r.add_argument('--output-evidence', default=''); r.add_argument('--source-evidence', default=''); r.add_argument('--note', default='')
    k = sub.add_parser('kappa'); k.add_argument('--a', required=True); k.add_argument('--b', required=True)
    a = p.parse_args(); {'select': select, 'packets': packets, 'record': lambda: record(a), 'kappa': lambda: kappa(a)}[a.cmd]()
