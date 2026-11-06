"""One record for every full-output human review across both studies.

Historical study (tool-loop harness): imported exports under reviews/assignment_final/exports/, supersession
chains resolved (an export superseded by a later one from the same reviewer is history, not current).
Follow-up study (Claude Code harness): output/study_v3/human_reviews_v3.json.
The two studies are listed side by side, never pooled into one rate: different harnesses, different packets.
No API calls; standard library only.

  python3 scripts/consolidate_human_reviews.py   -> output/human_reviews_all.json, output/human_reviews_all.md
"""
import collections, json, hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
read = lambda p: json.loads(Path(p).read_text())


def historical():
    mapping = {}
    for rel in ('output/submission_audit/private_review_key.json', 'output/native_workflow_01/calibration_private_key.json'):
        for item in read(ROOT / rel): mapping.setdefault(item['review_id'], {}).update(item)
    exports = {}
    for p in sorted((ROOT / 'reviews/assignment_final/exports').glob('*.json')):
        if p.name.endswith('.receipt.json'): continue
        exports[p.stem] = read(p)
    superseded = set()
    for d in exports.values():
        s = d.get('supersedes_export_sha256') or []
        superseded.update([s] if isinstance(s, str) else s)
    current = {}
    for digest, d in exports.items():
        if digest in superseded: continue
        for row in d['rows']:
            if row.get('human_reviewed') is not True: continue
            cid = row['review_id']; m = mapping.get(cid, {}); pj = m.get('primary_judge') or {}
            current[cid] = {
                'study': 'historical', 'harness': 'openrouter tool loop + native docx/xlsx engine', 'review_id': cid,
                'run_id': m.get('run_id'), 'family_id': m.get('family_id'), 'model': m.get('model'),
                'content_acceptable': row['content_acceptable'], 'consequential_error': row['consequential_error'],
                'evaluation_defect': row['evaluation_defect'], 'category': row.get('category'),
                'review_minutes': row.get('review_minutes'),
                'output_evidence': row.get('output_evidence'), 'source_and_consequence': row.get('source_and_consequence'),
                'minimum_repair': row.get('minimum_repair'),
                'judge_comparison': {'primary_judge_content_acceptable': pj.get('content_acceptable'), 'primary_judge_critical_error': pj.get('critical_error')},
                'blinding': 'blind packet; judge text withheld until after the verdict' if not m.get('prior_user_issue_exposure') else 'prior issue-only exposure recorded',
                'export_sha256': digest, 'reviewer_id': d.get('reviewer_id')}
    return sorted(current.values(), key=lambda r: r['review_id'])


def followup():
    d = read(ROOT / 'output/study_v3/human_reviews_v3.json'); rows = []
    cs = ROOT / 'output/study_v3/calibration_set_v31.json'; sample = set(read(cs)['selected']) if cs.exists() else set()
    for r in d['reviews']:
        parts = r['run_id'].split('__')
        rows.append({'study': 'v31_random_sample' if r['run_id'] in sample else 'follow_up_v3', 'harness': 'Claude Code CLI', 'review_id': r['run_id'], 'run_id': r['run_id'],
                     'family_id': parts[0], 'variant': parts[1], 'model': 'anthropic/claude-' + parts[2] + '-5.5',
                     'content_acceptable': r['content_acceptable'], 'consequential_error': r['consequential_error'],
                     'evaluation_defect': r['evaluation_defect'], 'category': r.get('category'), 'location': r.get('location'), 'stated_elsewhere': r.get('stated_elsewhere'), 'review_minutes': r.get('review_minutes'),
                     'output_evidence': r.get('output_evidence'), 'source_and_consequence': r.get('source_evidence'),
                     'minimum_repair': None, 'reviewer_note': r.get('reviewer_note'), 'judge_comparison': r.get('judge_comparison'),
                     'blinding': d.get('method'), 'reviewer_id': d.get('reviewer'),
                     'label_author': r.get('label_author') or 'human', 'human_verified': r.get('human_verified', True), 'verification': r.get('verification')})
    return rows


def hist_sol():
    f = ROOT / 'output/study_v3/human_reviews_hist_sol.json'
    if not f.exists(): return []
    d = read(f)
    return [{'study': 'historical_sol_confound', 'harness': 'openrouter tool loop + native docx/xlsx engine', 'review_id': r['run_id'], 'run_id': r['run_id'],
             'family_id': r['run_id'].split('__')[0], 'variant': r['run_id'].split('__')[1], 'model': 'openai/gpt-6.1-sol',
             'content_acceptable': r['content_acceptable'], 'consequential_error': r['consequential_error'], 'evaluation_defect': r['evaluation_defect'],
             'category': r.get('category'), 'location': r.get('location'), 'stated_elsewhere': r.get('stated_elsewhere'), 'review_minutes': r.get('review_minutes'),
             'output_evidence': r.get('output_evidence'), 'source_and_consequence': r.get('source_evidence'), 'minimum_repair': None, 'reviewer_note': r.get('reviewer_note'),
             'judge_comparison': None, 'blinding': d.get('method'), 'reviewer_id': d.get('reviewer'),
             'label_author': r.get('label_author') or 'human', 'human_verified': r.get('human_verified', True), 'verification': r.get('verification')} for r in d['reviews']]


def summarize(rows):
    n = len(rows); ce = sum(r['consequential_error'] == 'yes' for r in rows)
    acc = sum(r['content_acceptable'] == 'yes' for r in rows); defect = sum(r['evaluation_defect'] == 'yes' for r in rows)
    return {'reviewed': n, 'content_acceptable_yes': acc, 'consequential_error_yes': ce, 'evaluation_defect_yes': defect,
            'minutes_recorded': [r['review_minutes'] for r in rows if r.get('review_minutes') is not None]}


def main():
    h, f, hs = historical(), followup(), hist_sol()
    by = collections.defaultdict(list)
    for r in h + f + hs: by[r['study']].append(r)
    out = {'schema': 'human-reviews-all-v1', 'built_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
           'reviewer': 'single reviewer (project owner); no second reviewer yet',
           'studies': {k: summarize(v) for k, v in by.items()},
           'all': {'reviewed': len(h + f + hs), 'consequential_error_yes': sum(r['consequential_error'] == 'yes' for r in h + f + hs)},
           'not_pooled_because': 'different harnesses, prompts and packets; counts are reported per study and never combined into a rate',
           'reviews': h + f + hs}
    dest = ROOT / 'output/human_reviews_all.json'; dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    md = ['# Full-output human reviews, both studies', '', f"Built {out['built_at']}. One reviewer. {out['all']['reviewed']} reviews, {out['all']['consequential_error_yes']} consequential errors. Not pooled.", '',
          '| Study | Case | Model | Acceptable | Consequential | Task defect | Min | Primary judge |', '|---|---|---|---|---|---|---|---|']
    for r in h + f + hs:
        jc = r.get('judge_comparison') or {}
        pj = jc.get('gemini') or ('accept' if jc.get('primary_judge_content_acceptable') else 'reject' if jc.get('primary_judge_content_acceptable') is False else '?')
        md.append(f"| {r['study']} | {r['review_id']} | {(r.get('model') or '?').split('/')[-1]} | {r['content_acceptable']} | {r['consequential_error']} | {r['evaluation_defect']} | {r.get('review_minutes') or ''} | {pj} |")
    (ROOT / 'output/human_reviews_all.md').write_text('\n'.join(md) + '\n')
    print(json.dumps({k: out[k] for k in ('studies', 'all')}, indent=1)); print('wrote', dest.relative_to(ROOT))


if __name__ == '__main__':
    main()
