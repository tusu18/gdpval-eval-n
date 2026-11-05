"""Deterministic decision checks and family-level paired analysis (no API)."""
import json, math, random, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/paired_v1'

def matches(actual,expected):
    if isinstance(expected,bool):return isinstance(actual,bool) and actual==expected
    if isinstance(expected,(int,float)):
        return isinstance(actual,(int,float)) and not isinstance(actual,bool) and math.isfinite(actual) and abs(actual-expected)<=0.01
    if isinstance(expected,list):return isinstance(actual,list) and sorted(actual)==sorted(expected)
    return actual==expected

def score(run,rubric):
    facts=run.get('final',{}).get('facts') or {}
    if not isinstance(facts,dict):facts={}
    checks={k:{'actual':facts.get(k),'expected':v,'correct':matches(facts.get(k),v),'missing':facts.get(k) is None} for k,v in rubric['truth'].items()}
    reads=[t['arguments'].get('filename') for t in run.get('tool_events',[]) if t['name']=='read_record' and 'error' not in t['reply']]
    completed=run['status']=='completed'
    return {k:run.get(k) for k in ['run_id','family_id','variant','model','trial','status','actual_cost_usd','elapsed_seconds']}|{
      'eligible_for_decision_scoring':run['status']!='infrastructure_error',
      'decision_pass':completed and all(c['correct'] for c in checks.values()),
      'explicit_wrong':any(not c['correct'] and not c['missing'] for c in checks.values()),
      'missing_decision':any(c['missing'] for c in checks.values()),
      'read_operative_record':'record-17.txt' in reads,'read_registry':'registry.txt' in reads,
      'checks':checks,'artifacts_count':len(run.get('final',{}).get('artifacts') or [])}

def paired_summary(rows,model,variant):
    base={(r['family_id'],r['trial']):r for r in rows if r['model']==model and r['variant']=='baseline' and r['eligible_for_decision_scoring']}
    var={(r['family_id'],r['trial']):r for r in rows if r['model']==model and r['variant']==variant and r['eligible_for_decision_scoring']}
    family={};discord={'both_pass':0,'baseline_only_pass':0,'variant_only_pass':0,'both_fail':0}
    for key in sorted(base.keys()&var.keys()):
        b=int(base[key]['decision_pass']);v=int(var[key]['decision_pass']);family.setdefault(key[0],[]).append(v-b)
        discord['both_pass' if b and v else 'baseline_only_pass' if b else 'variant_only_pass' if v else 'both_fail']+=1
    means=[statistics.mean(x) for x in family.values()]
    if not means:return {'paired_families':0}
    rng=random.Random(20261030);draws=sorted(statistics.mean(rng.choices(means,k=len(means))) for _ in range(10000))
    return {'paired_families':len(means),'paired_runs':sum(len(x) for x in family.values()),'family_mean_difference':statistics.mean(means),'descriptive_family_bootstrap_95_interval':[draws[249],draws[9749]],'discordant_pairs':discord,'family_differences':{k:statistics.mean(v) for k,v in family.items()},'warning':'Five purposively selected families; a degenerate interval at all-pass is not evidence of certainty or equivalence.'}

def main():
    rubrics={r['id']:r for r in json.loads((ROOT/'data/paired_v1/grader/rubrics.json').read_text())}
    runs=[json.loads(p.read_text()) for p in sorted((OUT/'runs').glob('*.json'))]
    rows=[score(r,rubrics[r['family_id']]) for r in runs]
    groups=[]
    for m in sorted({r['model'] for r in rows}):
      for v in ['baseline','recovery','conflict']:
        allr=[r for r in rows if r['model']==m and r['variant']==v];rs=[r for r in allr if r['eligible_for_decision_scoring']]
        n=len(rs);passed=sum(r['decision_pass'] for r in rs)
        groups.append({'model':m,'variant':v,'attempted':len(allr),'decision_denominator':n,'passes':passed,'decision_pass_rate':passed/n if n else None,
          'explicit_wrong':sum(r['explicit_wrong'] for r in rs),'missing':sum(r['missing_decision'] for r in rs),'infra_errors':len(allr)-n,
          'operative_read_and_pass':sum(r['read_operative_record'] and r['decision_pass'] for r in rs),
          'registry_read_and_pass':sum(r['read_registry'] and r['decision_pass'] for r in rs),
          'cost_usd':sum(r['actual_cost_usd'] for r in allr),
          'cost_per_decision_pass':sum(r['actual_cost_usd'] for r in allr)/passed if passed else None,
          'median_run_seconds':statistics.median(r['elapsed_seconds'] for r in allr) if allr else None})
    ledger=json.loads((OUT/'ledger.json').read_text())
    summary={'saved_runs':len(rows),'groups':groups,'paired':[{'model':m,'variant':v,**paired_summary(rows,m,v)} for m in sorted({r['model'] for r in rows}) for v in ['recovery','conflict']],
      'cost_actual_reported_usd':sum(x.get('actual_cost_usd',0) for x in ledger),'cost_charged_or_reserved_usd':sum(x['charged_or_reserved'] for x in ledger),
      'unresolved_charges':sum(x['status']!='actual' for x in ledger),'human_expert_acceptance':None,'human_review_minutes':None,'human_interrater_agreement':None,
      'metric_scope':'Structured critical-decision checks only; inspect deliverables and independent reviews before claiming full task acceptance.'}
    (OUT/'scores.json').write_text(json.dumps(rows,indent=2));(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
