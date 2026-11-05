"""Fail-closed model/configuration selection after independent human review.

Input rows use ONE predeclared exposure per family/model/arm. Repeated trials or
multiple conditions cannot inflate n. The gate reports uncertainty, not just a
zero-error point estimate. Tests use fictional rows, never claimed study data.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

def error_upper_bound(errors, n, confidence=0.95):
    if not isinstance(errors,int) or not isinstance(n,int) or not 0 <= errors <= n or n < 1 or not 0 < confidence < 1:
        raise ValueError('invalid_binomial_inputs')
    if errors == n:
        return 1.0
    alpha=1-confidence
    if errors == 0:
        return 1-alpha**(1/n)
    def cdf(p):
        if p<=0:return 1.0
        if p>=1:return 0.0
        terms=[math.lgamma(n+1)-math.lgamma(i+1)-math.lgamma(n-i+1)+i*math.log(p)+(n-i)*math.log1p(-p) for i in range(errors+1)]
        peak=max(terms)
        return math.exp(peak)*sum(math.exp(x-peak) for x in terms)
    lo,hi=0.0,1.0
    for _ in range(90):
        mid=(lo+hi)/2
        if cdf(mid)>alpha:lo=mid
        else:hi=mid
    return (lo+hi)/2

def finite_nonnegative(value):
    return type(value) in (int,float) and math.isfinite(value) and value>=0

def select(rows, config):
    blockers=[]
    if config.get('customer_approved_thresholds') is not True:blockers.append('Customer error and acceptance thresholds are not approved.')
    if config.get('independent_representative_sampling_approved') is not True:blockers.append('Independent, representative family sampling has not been approved.')
    if type(config.get('confidence_level')) not in (int,float) or not 0<config['confidence_level']<1:blockers.append('Confidence level is missing or invalid.')
    for k in ['critical_error_ceiling','minimum_acceptance_rate']:
        if type(config.get(k)) not in (int,float) or not 0<=config[k]<=1:blockers.append(k+' is unset or invalid.')
    if not finite_nonnegative(config.get('reviewer_cost_per_hour_usd')):blockers.append('Human review cost is missing.')
    if not rows:blockers.append('No expert-adjudicated selection-cell observations exist.')
    groups=defaultdict(list)
    for row in rows:
        groups[(row['model'],row['arm'])].append(row)
    families=[{r['family_id'] for r in rs} for rs in groups.values()]
    if families and any(x!=families[0] for x in families):blockers.append('Candidate systems were not evaluated on the same family set.')
    for key,rs in groups.items():
        if len({r['family_id'] for r in rs})!=len(rs):blockers.append(f'{key}: repeated observations cannot count as independent families.')
        for r in rs:
            if r.get('variant')!='conflict' or r.get('trial')!=1:blockers.append('An observation is outside the prespecified selection cell.')
            if any(r.get(k) is not True for k in ['independent_expert_adjudicated','task_validated','permission_for_evaluation']):blockers.append('Task permission, independent validation or expert adjudication is missing.')
            reviewers=r.get('reviewer_ids')
            if not isinstance(reviewers,list) or len(set(x for x in reviewers if isinstance(x,str) and x.strip()))<2:blockers.append('Two distinct human reviewer IDs are required.')
            if r.get('evaluation_defect') is not False:blockers.append('An evaluation defect remains unresolved or unreviewed.')
            if type(r.get('accepted')) is not bool or type(r.get('critical_error')) is not bool:blockers.append('Expert labels are incomplete.')
            if r.get('accepted') and r.get('critical_error'):blockers.append('An accepted output is simultaneously labeled a consequential error; adjudicate it.')
            if not finite_nonnegative(r.get('solver_cost_usd')) or not finite_nonnegative(r.get('review_minutes')):blockers.append('An attempt has missing or invalid cost/time data.')
    if blockers:
        return {'status':'not_selectable','recommended_configuration':None,'blockers':sorted(set(blockers)),'candidates':[]}
    # Bonferroni over both endpoint bounds and every candidate configuration.
    confidence=config.get('confidence_level',0.95)
    bound_confidence=1-(1-confidence)/(2*len(groups))
    candidates=[]
    for (model,arm),rs in sorted(groups.items()):
        n=len(rs);accepted=sum(r['accepted'] for r in rs);errors=sum(r['critical_error'] for r in rs)
        upper=error_upper_bound(errors,n,bound_confidence)
        lower=1-error_upper_bound(n-accepted,n,bound_confidence)
        total=sum(r['solver_cost_usd']+r['review_minutes']/60*config['reviewer_cost_per_hour_usd'] for r in rs)
        eligible=upper<=config['critical_error_ceiling'] and lower>=config['minimum_acceptance_rate'] and accepted>0
        candidates.append({'model':model,'arm':arm,'independent_families':n,'accepted':accepted,'critical_errors':errors,'critical_error_upper_bound':upper,'acceptance_lower_bound':lower,'simultaneous_confidence':confidence,'total_solver_and_review_cost_usd':total,'cost_per_accepted_deliverable_usd':total/accepted if accepted else None,'eligible':eligible})
    eligible=[x for x in candidates if x['eligible']]
    winner=min(eligible,key=lambda x:x['cost_per_accepted_deliverable_usd']) if eligible else None
    return {'status':'selectable' if winner else 'insufficient_evidence','recommended_configuration':winner,'blockers':[] if winner else ['No configuration meets both uncertainty-adjusted thresholds.'],'candidates':candidates,'caveat':'The exact bounds assume independent sampled families with a common target error probability. They do not repair biased task sampling. Review cost here includes every measured review minute in the selection cell; separately report development/evaluation setup cost.'}

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    config=json.loads((root/'config/paired_v2/model_selection.json').read_text())
    observation_path=root/'reviews/paired_v2/adjudicated_selection_rows.json'
    rows=json.loads(observation_path.read_text()) if observation_path.exists() else []
    result=select(rows,config)
    out=root/'output/paired_v2/model_selection_status.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
