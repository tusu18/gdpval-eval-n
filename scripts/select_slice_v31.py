"""Study v3.1 slice: extend the 15-task slice to 30 by a rule fixed before any v3.1 output exists.

Rule (applied mechanically to the pinned openai/gdpval parquet, revision 11e7900):
  1. Keep the original three occupations (15 tasks).
  2. Rank the other 41 occupations by how many of their five gold deliverables are delivered only as native
     Word/Excel files (.docx/.xlsx). Add every occupation with 5/5.
  3. If fewer than 30 tasks, add from the next tier (4/5), breaking ties by sharing a sector with the original
     three occupations (Manufacturing; Professional, Scientific, and Technical Services). If the tie persists, stop.
Rationale: the failure class under study lives in native business documents checked against source records;
staying in the same document formats and sectors keeps the instrument identical and the comparison clean.

  python3 scripts/select_slice_v31.py --parquet research/train-00000-of-00001.parquet
writes data/gdpval_v31/{solver,grader}/tasks.jsonl, task_selection.csv, manifest.json, selection_report.json
"""
import argparse, collections, csv, hashlib, json
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
REVISION = '11e7900cdcac61bc4daf59e65feb238acda98fbf'
ORIGINAL = ('Buyers and Purchasing Agents', 'Project Management Specialists', 'Shipping, Receiving, and Inventory Clerks')
TARGET = 30
NATIVE = ('docx', 'xlsx')


def digest(b): return hashlib.sha256(b).hexdigest()


def exts(r): return [f.rsplit('.', 1)[-1].lower() for f in (r.get('deliverable_files') or [])]


def native(r): return bool(exts(r)) and all(e in NATIVE for e in exts(r))


def main():
    a = argparse.ArgumentParser(); a.add_argument('--parquet', type=Path, required=True); a.add_argument('--out', type=Path, default=ROOT / 'data/gdpval_v31')
    a = a.parse_args()
    import pyarrow.parquet as pq
    blob = a.parquet.read_bytes(); rows = pq.read_table(a.parquet).to_pylist()
    occ = collections.defaultdict(list)
    for r in rows: occ[r['occupation']].append(r)
    sector = {o: rs[0]['sector'] for o, rs in occ.items()}
    orig_sectors = sorted({sector[o] for o in ORIGINAL})
    ranking = sorted(((sum(native(r) for r in rs), o) for o, rs in occ.items() if o not in ORIGINAL), key=lambda t: (-t[0], t[1]))
    chosen = list(ORIGINAL); log = []
    for tier in sorted({n for n, _ in ranking}, reverse=True):
        if len(chosen) * 5 >= TARGET: break
        members = [o for n, o in ranking if n == tier]
        room = (TARGET - len(chosen) * 5) // 5
        if len(members) <= room:
            chosen += members; log.append({'tier': f'{tier}/5', 'added': members, 'reason': 'whole tier fits'}); continue
        same = [o for o in members if sector[o] in orig_sectors]
        log.append({'tier': f'{tier}/5', 'candidates': members, 'tiebreak': f'shares a sector with the original slice {orig_sectors}', 'after_tiebreak': same})
        if len(same) <= room: chosen += same; log[-1]['added'] = same
        else: log[-1]['added'] = []; log[-1]['stopped'] = 'tie persists after sector tiebreak'
        break
    selected = sorted((r for r in rows if r['occupation'] in chosen), key=lambda r: (chosen.index(r['occupation']), r['task_id']))
    assert all(len(occ[o]) == 5 for o in chosen) and len({r['task_id'] for r in selected}) == len(selected)
    (a.out / 'solver').mkdir(parents=True, exist_ok=True); (a.out / 'grader').mkdir(parents=True, exist_ok=True)
    solver = [{**{k: r[k] for k in ('task_id', 'occupation', 'sector', 'prompt')}, 'reference_files': list(r['reference_files'] or []),
               'reference_urls': [f'https://huggingface.co/datasets/openai/gdpval/resolve/{REVISION}/{quote(p, safe="/")}' for p in (r['reference_files'] or [])]} for r in selected]
    grader = [{'task_id': r['task_id'], 'rubric_json': r['rubric_json'], 'rubric_pretty': r['rubric_pretty'], 'gold_deliverable_files': list(r['deliverable_files'] or [])} for r in selected]
    files = {}
    for role, recs in (('solver', solver), ('grader', grader)):
        f = a.out / role / 'tasks.jsonl'; f.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in recs)); files[f'{role}/tasks.jsonl'] = digest(f.read_bytes())
    with (a.out / 'task_selection.csv').open('w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['task_id', 'occupation', 'sector', 'in_original_slice', 'gold_deliverable_formats', 'reference_count', 'rubric_items'])
        for r in selected: w.writerow([r['task_id'], r['occupation'], r['sector'], r['occupation'] in ORIGINAL, '+'.join(exts(r)), len(r['reference_files'] or []), len(json.loads(r['rubric_json']))])
    report = {'rule': __doc__.split('Rule')[1].split('Rationale')[0].strip(), 'original_sectors': orig_sectors, 'ranking_top': [{'native_of_5': n, 'occupation': o, 'sector': sector[o]} for n, o in ranking[:14]], 'steps': log,
              'chosen_occupations': chosen, 'tasks': len(selected)}
    (a.out / 'selection_report.json').write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
    manifest = {'dataset': 'openai/gdpval', 'revision': REVISION, 'parquet_sha256': digest(blob), 'source_rows': len(rows), 'selected_rows': len(selected),
                'occupations': chosen, 'task_ids': [r['task_id'] for r in selected], 'new_task_ids': [r['task_id'] for r in selected if r['occupation'] not in ORIGINAL],
                'file_hashes': files, 'selection_rule': 'scripts/select_slice_v31.py; see selection_report.json', 'model_runs_on_new_tasks_at_selection': 0}
    (a.out / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print(json.dumps({'occupations': chosen, 'tasks': len(selected), 'steps': log}, indent=1))


if __name__ == '__main__':
    main()
