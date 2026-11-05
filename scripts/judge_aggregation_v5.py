"""Offline endpoint aggregation. Unknown is never a negative vote."""
from collections import defaultdict
ELIGIBLE = 'automated_assessment_not_human_acceptance'
ENDPOINTS = ('content_acceptable', 'consequential_error')

def aggregate(records):
    groups = defaultdict(list)
    for row in records:
        groups[(row['run_id'], row['judge'])].append(row)
    by_judge = {}; by_run = defaultdict(dict)
    for (run, judge), chunks in groups.items():
        assessments = [r.get('assessment') or {} for r in chunks]
        valid = all(r.get('status') == 'received' and a.get('status') == ELIGIBLE
                    for r, a in zip(chunks, assessments))
        endpoints = {}
        for name in ENDPOINTS:
            vals = [a.get(name) for a in assessments]
            if not valid or any(type(v) is not bool for v in vals):
                endpoints[name] = None
            else:
                endpoints[name] = all(vals) if name == 'content_acceptable' else any(vals)
        by_run[run][judge] = endpoints
        stats = by_judge.setdefault(judge, {'jobs': 0, 'eligible_jobs': 0, 'endpoints': {k:{'true':0,'false':0,'unknown':0} for k in ENDPOINTS}})
        stats['jobs'] += 1; stats['eligible_jobs'] += valid
        for name, value in endpoints.items():
            stats['endpoints'][name]['unknown' if value is None else str(value).lower()] += 1
    judges = sorted(by_judge)
    comparisons = {}
    for name in ENDPOINTS:
        pairs=[]; disagreements=[]
        if len(judges) == 2:
            for run, values in by_run.items():
                votes=[values.get(j,{}).get(name) for j in judges]
                if all(type(v) is bool for v in votes):
                    pairs.append(votes)
                    if votes[0] != votes[1]: disagreements.append({'run_id':run,'votes':dict(zip(judges,votes))})
        comparisons[name]={'eligible_pairs':len(pairs),'agree':sum(a==b for a,b in pairs),
                           'both_true':sum(a and b for a,b in pairs),'any_true':sum(a or b for a,b in pairs),
                           'disagreements':disagreements}
    return {'per_judge':by_judge,'comparisons':comparisons,'per_run':dict(by_run),
            'scope':'Automated endpoints on eligible records only; no human accuracy claim. Missing/invalid/source-uncertain judgments stay unknown.'}
