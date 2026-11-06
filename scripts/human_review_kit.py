"""Blind human-review kit for the follow-up run, plus second-reviewer agreement.

v3.1:  select-random (22 outputs, frozen before judging) · packets-random · packets-hist-sol (5 historical GPT-6.1 Sol outputs)

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
CATEGORIES = {  # hand taxonomy, one primary category per consequential error; same ids as the historical triage where they overlap
    'approval_bypass': 'an exception or provisional clause weakens a mandatory approval',
    'unsupported_commitment': 'the plan commits to stock, capacity, dates or figures the sources do not establish',
    'unsupported_claim': 'an open condition is stated as settled fact',
    'calculation_error': 'a total, formula or derived figure is wrong',
    'source_misread': 'a figure or fact contradicts the supplied source',
    'incomplete': 'a requested element or comparison is missing',
    'instruction_violation': 'an explicit constraint of the request is broken (format, scope, threshold)',
    'other': 'none of the above; describe in the note'}
QUESTIONS = ['content_acceptable: Is the output usable for the stated purpose without substantive correction? yes / no / uncertain',
             'consequential_error: Does it contain an error that would lead to a wrong decision, unauthorized action or material loss if acted on? yes / no / uncertain (if yes: quote the output line and the source line)',
             'evaluation_defect: Is there an unresolved problem in the request or source material that prevents a fair judgment? yes / no / uncertain',
             'If consequential: category (approval_bypass, unsupported_commitment, unsupported_claim, calculation_error, source_misread, incomplete, instruction_violation, other); where it sits (e.g. action table, exception clause, workbook total); and is the governing rule or figure stated correctly elsewhere in the same deliverable? yes / no / na']


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
    hist = a.run in HIST_SOL or '__openai_' in a.run or '__anthropic_' in a.run
    path = V3 / (('human_reviews_hist_sol.json' if hist else 'human_reviews_v3.json') if a.reviewer in ('project_owner_chat', 'owner', 'tus', 'tushar') else f'human_reviews_v3_{a.reviewer}.json')  # any other name = second reviewer (kappa)
    doc = read(path) if path.exists() else {'schema': 'study-v3-human-reviews-v1', 'reviewer': a.reviewer, 'recorded_at': utc(),
                                             'method': 'Blind packet (request, sources, complete output text; no judge text) read before verdict. Minutes are reviewer estimates.', 'reviews': []}
    if any(r['run_id'] == a.run for r in doc['reviews']): raise SystemExit(f'{a.run} already recorded for {a.reviewer}; edit the file to supersede')
    if a.consequential == 'yes' and not (a.output_evidence and a.source_evidence): raise SystemExit('a consequential error needs both --output-evidence and --source-evidence')
    if a.category and a.category not in CATEGORIES: raise SystemExit('unknown --category; choose from ' + ', '.join(CATEGORIES))
    if a.consequential == 'yes' and not a.category: print('note: no --category given; the hand taxonomy will list this error as uncategorized')
    doc['reviews'].append({'run_id': a.run, 'content_acceptable': a.acceptable, 'consequential_error': a.consequential, 'evaluation_defect': a.defect,
                           'review_minutes': a.minutes, 'output_evidence': a.output_evidence, 'source_evidence': a.source_evidence, 'reviewer_note': a.note,
                           'category': a.category or None, 'location': a.location or None, 'stated_elsewhere': a.stated_elsewhere or None,
                           'recorded_at': utc(), 'blinding': 'judge text withheld until after this record was written'})
    n = len(doc['reviews']); doc.setdefault('summary', {}).update({'reviewed': n, 'consequential_errors': sum(r.get('consequential_error') == 'yes' for r in doc['reviews'])})
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



FIELDS = [('content_acceptable', 'acceptable (yes/no/uncertain)'), ('consequential_error', 'consequential error (yes/no/uncertain)'),
          ('evaluation_defect', 'task or source defect (yes/no/uncertain)'), ('category', 'category (' + '/'.join(CATEGORIES) + ', blank if none)'),
          ('location', 'where it sits (blank if none)'), ('stated_elsewhere', 'rule stated correctly elsewhere (yes/no/na, blank if none)'),
          ('output_evidence', 'exact output line'), ('source_evidence', 'exact source line'), ('reviewer_note', 'one-line note')]


def verify(a):
    """Read each AI-drafted label next to its blind packet; confirm it or correct it. Saves after every case."""
    import subprocess
    done = 0
    for path in (V3 / 'human_reviews_v3.json', V3 / 'human_reviews_hist_sol.json'):
        if not path.exists(): continue
        doc = read(path)
        for r in doc['reviews']:
            drafted = r.get('label_author') or 'automated' in (r.get('review_method') or '').lower()
            if not drafted or (r.get('verified_by') and r.get('verified_at')): continue
            if a.run and r['run_id'] != a.run: continue
            pk = next(iter(sorted(V3.glob(f'review_v31/*__{r["run_id"]}.md')) + sorted(V3.glob(f'review_hist_sol/*__{r["run_id"]}.md'))), None)
            print('\n' + '=' * 78 + f'\n{r["run_id"]}\npacket: {pk.relative_to(ROOT) if pk else "(not found)"}\n' + '-' * 78)
            print(f'Draft label by {r.get("label_author") or "an automated review"} (not yet verified):')
            for k, lab in FIELDS:
                v = r.get(k)
                if v: print(f'  {lab.split(" (")[0]:<34} {v if len(str(v)) <= 400 else str(v)[:400] + " …"}')
            if a.open and pk: subprocess.run(['open', str(pk)], check=False)
            ans = input('\nRead the packet. Is this label right?  [y] yes  [n] no, correct it  [s] skip  [q] quit: ').strip().lower()
            if ans == 'q': break
            if ans not in ('y', 'n'): continue
            mins = input('Minutes you spent on this case: ').strip()
            if ans == 'n':
                r['draft_label'] = {k: r.get(k) for k, _ in FIELDS}
                for k, lab in FIELDS:
                    cur = str(r.get(k) or '')
                    new = input(f'  {lab} [{cur if len(cur) <= 80 else cur[:80] + " …"}] (Enter keeps, - clears): ').strip()
                    if new: r[k] = None if new == '-' else new
                if r.get('category') and r['category'] not in CATEGORIES: print('  unknown category kept as typed; fix it later in the file')
            r.update(human_verified=True, verification='confirmed' if ans == 'y' else 'corrected', verified_by=a.reviewer, verified_at=utc(),
                     review_minutes=float(mins) if mins.replace('.', '', 1).isdigit() else r.get('review_minutes'))
            doc.setdefault('summary', {}).update({'reviewed': len(doc['reviews']), 'consequential_errors': sum(x.get('consequential_error') == 'yes' for x in doc['reviews']),
                                                  'human_verified': sum(1 for x in doc['reviews'] if not x.get('label_author') or x.get('human_verified'))})
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + '\n'); done += 1
            print('saved:', r['verification'])
        else:
            continue
        break
    left = sum(1 for p_ in (V3 / 'human_reviews_v3.json', V3 / 'human_reviews_hist_sol.json') if p_.exists() for x in read(p_)['reviews']
               if (x.get('label_author') or 'automated' in (x.get('review_method') or '').lower()) and not (x.get('verified_by') and x.get('verified_at')))
    print(f'\nverified this session: {done}; AI-drafted labels still unverified: {left}')


# ---------------- v3.1: random sample (frozen before judging) and the historical Sol confound check ----------------
SEED_V31 = 20261106; N_V31 = 22
HIST_SOL = ['sourcing_approvals__baseline__openai_gpt-6.1-sol__r1', 'sourcing_approvals__conflict__openai_gpt-6.1-sol__r1', 'sourcing_approvals__recovery__openai_gpt-6.1-sol__r1',
            'supplier_exit__baseline__openai_gpt-6.1-sol__r1', 'supplier_exit__recovery__openai_gpt-6.1-sol__r1']  # every unreviewed Sol r1 output in the two error families


def labeled_ids():
    out = set()
    for f in V3.glob('human_reviews_v3*.json'): out |= {r['run_id'] for r in read(f)['reviews']}
    return out


def select_random():
    if (V3 / 'calibration_set_v31.json').exists(): raise SystemExit('calibration_set_v31.json already frozen; delete it only if no label has been written from it')
    INST = ROOT / 'data/study_v3/instances'; done = labeled_ids(); pop = {}
    for f in sorted((V3 / 'solver_runs').glob('*__r1.json')):
        r = read(f)
        if r.get('status') != 'submitted' or r['variant'] != 'original' or r['run_id'] in done: continue
        occ = read(INST / (r['instance_id'] + '.json'))['occupation']; pop.setdefault(occ, {'sonnet': [], 'opus': []})[r['model']].append(r['run_id'])
    sizes = {o: {m: len(v) for m, v in d.items()} for o, d in pop.items()}
    rnd = random.Random(SEED_V31)
    for o in pop.values():
        for m in o.values(): m.sort(); rnd.shuffle(m)
    occs = sorted(pop); chosen = []; turn = 0
    while len(chosen) < N_V31 and any(pop[o][m] for o in occs for m in pop[o]):
        for o in occs:
            if len(chosen) >= N_V31: break
            order = ('sonnet', 'opus') if turn % 2 == 0 else ('opus', 'sonnet')
            for m in order:
                if pop[o][m]: chosen.append(pop[o][m].pop()); break
        turn += 1
    judged = [r for r in chosen if any((V3 / 'judge_runs').glob(f'{r}__sel*__*.json'))]
    out = {'frozen_at': utc(), 'seed': SEED_V31, 'n': len(chosen), 'rule': 'config/study_v31.json human_review.random_sample', 'population_by_occupation_and_solver': sizes,
           'selected': chosen, 'selected_with_existing_v3_judge_runs': judged,
           'blinding_note': 'Outputs judged in v3 have judge files on disk; the reviewer has seen only aggregate counts on the site, never per-output judge text, for these runs.'}
    (V3 / 'calibration_set_v31.json').write_text(json.dumps(out, indent=1)); print(json.dumps({k: out[k] for k in ('n', 'selected')}, indent=1))


def _write_packet(outdir, i, n, run_id, solver_label, docs, artifacts):
    md = [f'# Blind review packet {i:02d} of {n}', '', f'Case: `{run_id}` · solver: {solver_label}', '',
          'Read the request, the sources and the complete output. Answer the three questions before looking at any judge output. Record minutes.', '',
          '## Questions', ''] + [f'{k}. {q}' for k, q in enumerate(QUESTIONS, 1)] + ['', '---', '']
    for k, v in docs.items():
        md += [f'## {"Request" if k == "request" else "Source: " + k}', '', '```', str(v)[:60000], '```', '']
    for a in artifacts:
        md += [f'## Output file: {a["id"]}', '', '```', a.get('text', '')[:80000], '```', '']
    md += ['---', '', '## Record', '', f'python3 scripts/human_review_kit.py record --run {run_id} --reviewer owner --acceptable ? --consequential ? --defect ? --minutes ? --output-evidence "<exact output line>" --source-evidence "<exact source line>" --note "<one sentence>"', '',
           'If consequential = yes, add: `--category <id> --location "<where>" --stated-elsewhere yes|no|na`', '']
    (outdir / f'{i:02d}__{run_id}.md').write_text('\n'.join(md))


def packets_random():
    from evidence_grader import extract_artifact
    from evidence_grader_v2 import reference_text
    sel = read(V3 / 'calibration_set_v31.json'); INST = ROOT / 'data/study_v3/instances'; outdir = V3 / 'review_v31'; outdir.mkdir(exist_ok=True)
    for i, run in enumerate(sel['selected'], 1):
        r = read(V3 / 'solver_runs' / f'{run}.json'); inst = read(INST / (r['instance_id'] + '.json'))
        docs = {'request': inst['prompt']}
        for x in inst.get('reference_files', []): docs['reference:' + Path(x).name] = reference_text(ROOT / x)[:60000]
        docs.update({'workspace:' + k: v for k, v in (inst.get('workspace') or {}).items()}); docs.update({'attachment:' + k: v for k, v in (inst.get('attachments') or {}).items()})
        arts = []
        for o in r['outputs']:
            f = V3 / 'claudecode' / run / 'outputs' / o['name']
            try: arts.append(extract_artifact(f))
            except Exception as e: arts.append({'id': o['name'], 'text': f'[not extractable as text: {e}; open the file directly at {f.relative_to(ROOT)}]'})
        _write_packet(outdir, i, len(sel['selected']), run, 'Claude Opus 5.5' if r['model'] == 'opus' else 'Claude Sonnet 5.5', docs, arts)
    print('wrote', len(sel['selected']), 'packets to', outdir.relative_to(ROOT))


def packets_hist_sol():
    from evidence_grader import extract_artifact
    from build_evidence_upgrade import source_documents
    outdir = V3 / 'review_hist_sol'; outdir.mkdir(exist_ok=True)
    for i, run in enumerate(HIST_SOL, 1):
        fam, var = run.split('__')[:2]; task = read(ROOT / 'data/paired_v1/solver' / f'{fam}__{var}.json')
        task.setdefault('attachments', {}); task.setdefault('workspace', {})
        docs = source_documents(task)
        arts = [extract_artifact(f) for f in sorted((ROOT / 'output/paired_v1/artifacts' / run).glob('*')) if f.suffix.lower() in ('.docx', '.xlsx')]
        _write_packet(outdir, i, len(HIST_SOL), run, 'withheld (historical run)', docs, arts)
    print('wrote', len(HIST_SOL), 'packets to', outdir.relative_to(ROOT))

if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True); sub.add_parser('select'); sub.add_parser('packets')
    r = sub.add_parser('record')
    for k in ('run', 'reviewer', 'acceptable', 'consequential', 'defect'): r.add_argument('--' + k, required=True)
    r.add_argument('--minutes', type=float); r.add_argument('--output-evidence', default=''); r.add_argument('--source-evidence', default=''); r.add_argument('--note', default='')
    r.add_argument('--category', default=''); r.add_argument('--location', default=''); r.add_argument('--stated-elsewhere', default='', choices=['', 'yes', 'no', 'na'])
    k = sub.add_parser('kappa'); k.add_argument('--a', required=True); k.add_argument('--b', required=True)
    v = sub.add_parser('verify'); v.add_argument('--reviewer', default='tus'); v.add_argument('--run'); v.add_argument('--no-open', dest='open', action='store_false')
    for c in ('select-random', 'packets-random', 'packets-hist-sol'): sub.add_parser(c)
    a = p.parse_args(); {'select': select, 'packets': packets, 'record': lambda: record(a), 'kappa': lambda: kappa(a), 'verify': lambda: verify(a),
                         'select-random': select_random, 'packets-random': packets_random, 'packets-hist-sol': packets_hist_sol}[a.cmd]()