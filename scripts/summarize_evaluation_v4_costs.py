"""Account for every existing paid request without inventing app inference costs."""
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/evaluation_v4'

def main():
    roster=json.loads((ROOT/'data/evaluation_v4/task-roster.json').read_text())
    groups=defaultdict(list); requests=[]
    for path in sorted((ROOT/'output/evaluation_v2/calls').glob('*/reservation.json')):
        r=json.loads(path.read_text())
        matches=[t['task_id'] for t in roster if t['task_id'] in r['label']]
        if len(matches)>1: raise ValueError('Ambiguous task assignment')
        tid=matches[0] if matches else None
        item={k:r.get(k) for k in ('id','label','scope','model','actual_cost_usd','reserved_usd','status')}
        item.update(task_id=tid, reservation_path=str(path.relative_to(ROOT)),
                    reservation_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        groups[tid].append(item);requests.append(item)
    def stats(items):
        return {'request_count':len(items), 'known_provider_cost_usd':sum(x['actual_cost_usd'] or 0 for x in items),
                'unresolved_reserved_usd':sum(x['reserved_usd'] for x in items if x['actual_cost_usd'] is None)}
    rows=[]
    for t in roster:
        items=groups[t['task_id']]
        rows.append({'task_id':t['task_id'],'occupation':t['occupation'],'original_cohort':t['status'],
                     **stats(items),'in_app_inference_cost_usd':None,
                     'cost_scope':'All task-ID-linked paid requests, including repeats, model comparisons and grading; not cost of one deliverable.',
                     'new_v4_openrouter_cost_usd':0})
    total=stats(requests);before=json.loads((OUT/'budget-before.json').read_text())
    current_hashes={r['reservation_path']:r['reservation_sha256'] for r in requests}
    unchanged=current_hashes==before['reservation_hashes']
    total['committed_usd']=total['known_provider_cost_usd']+total['unresolved_reserved_usd']
    if total['committed_usd']>30+1e-9: raise RuntimeError('Budget ceiling exceeded')
    result={'created_at':datetime.now(timezone.utc).isoformat(), 'api_limit_usd':30,
            'ledger_unchanged_from_before_v4':unchanged, 'total':total,
            'headroom_usd':30-total['committed_usd'], 'tasks':rows,
            'shared_or_unassigned_development_checks':stats(groups[None]), 'requests':requests,
            'in_app_inference_cost_usd':None,'cost_per_accepted_deliverable':None,
            'interpretation':'Known charges are a subtotal; unresolved reserves are not confirmed charges. App usage is unavailable, not free. Shared development checks are retained separately, not arbitrarily spread across tasks.'}
    (OUT/'costs.json').write_text(json.dumps(result,indent=2)+'\n')
    with (OUT/'task-costs.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps({'ledger_unchanged':unchanged,'total':total,'task_rows':len(rows),
                      'shared':result['shared_or_unassigned_development_checks']}))

if __name__=='__main__': main()
