"""Recompute descriptive generator/judge differences from original saved runs.

Judge acceptance is not human acceptance or a causal self-preference estimate.
No new inference, task changes or human labels are created.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from score_paired_pilot import score

ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads(p.read_text())


def aggregate(records,runs):
    for record in records:
        if any(type(record['judgment'].get(k)) is not bool for k in ('content_acceptable','critical_error')):
            raise ValueError('Binary judge verdict required; do not silently count unresolved labels')
    groups={}
    for model in sorted({r['model'] for r in runs.values()}):
        subset=[r for r in records if runs[r['run_id']]['model']==model]
        groups[model]={'judged':len(subset),
            'accepted':sum(r['judgment'].get('content_acceptable') is True for r in subset),
            'rejected':sum(r['judgment'].get('content_acceptable') is False for r in subset),
            'critical_error':sum(r['judgment'].get('critical_error') is True for r in subset)}
    return groups


def build(root=ROOT):
    root=Path(root);paths=set()
    def load(rel):
        paths.add(str(rel));return read(root/rel)
    runs={p.stem:load(p.relative_to(root)) for p in sorted((root/'output/paired_v1/runs').glob('*.json'))}
    judgments=[load(p.relative_to(root)) for p in sorted((root/'output/paired_v1/judgments_v3').glob('*.json'))]
    rubrics={x['id']:x for x in load('data/paired_v1/grader/rubrics.json')}
    primary=[r for r in judgments if r['kind']=='primary' and r['status']=='completed']
    secondary=[r for r in judgments if r['kind']=='secondary' and r['status']=='completed']
    pby={r['run_id']:r for r in primary};sby={r['run_id']:r for r in secondary}
    if len(pby)!=len(primary) or len(sby)!=len(secondary):raise ValueError('Duplicate judge record')
    def excluded(r):return r['family_id']=='change_control' or (r['family_id']=='ev_localization' and r['variant']=='conflict')
    excluded_runs=[r for r in runs.values() if excluded(r)]
    filtered=[r for r in primary if not excluded(runs[r['run_id']])]
    paired=defaultdict(dict)
    for record in filtered:
        run=runs[record['run_id']]
        paired[(run['family_id'],run['variant'],run['trial'])][run['model']]=record
    pairs=[]
    models=sorted({r['model'] for r in runs.values()})
    for (family,variant,trial),members in sorted(paired.items()):
        if set(members)!=set(models):continue
        pairs.append({'family_id':family,'variant':variant,'trial':trial,
                      'judgments':{m:{'run_id':members[m]['run_id'],
                          'accepted':members[m]['judgment']['content_acceptable']} for m in models}})
    overlap=[]
    for rid in sorted(pby.keys()&sby.keys()):
        overlap.append({'run_id':rid,'generator_model':runs[rid]['model'],
                        'primary_accepted':pby[rid]['judgment']['content_acceptable'],
                        'secondary_accepted':sby[rid]['judgment']['content_acceptable'],
                        'primary_critical':pby[rid]['judgment']['critical_error'],
                        'secondary_critical':sby[rid]['judgment']['critical_error']})
    e=load('output/assignment_final/evidence.json')
    mapping={x['review_id']:x for x in load('output/submission_audit/private_review_key.json')}
    human={x['review_id']:x for x in e['human']['calibration']['case_level_comparisons']}
    manual=[]
    for finding in e['human']['taxonomy']['examples']:
        cid=finding['review_id'];rid=mapping[cid]['run_id'];prior=pby[rid]
        manual.append({'review_id':cid,'run_id':rid,'family_id':runs[rid]['family_id'],
            'variant':runs[rid]['variant'],'human_category':finding['category_label'],
            'primary_judge_finished_at':prior['finished_at'],
            'primary_accepted':prior['judgment']['content_acceptable'],
            'primary_critical':prior['judgment']['critical_error'],
            'primary_omissions':prior['judgment'].get('omissions',[]),
            'primary_critical_evidence':prior['judgment'].get('critical_evidence',[]),
            'secondary_accepted':sby[rid]['judgment']['content_acceptable'] if rid in sby else None,
            'human_content_acceptable':human[cid]['endpoints']['content_acceptable']['human_label'],
            'human_consequential_error':human[cid]['endpoints']['consequential_error']['human_label'],
            'scope':'Primary judge flagged the same issue before the human review; the human confirmed/refined it. Primary critical and human consequential labels can differ.'})
    byvariant=[]
    for variant in ('baseline','recovery','conflict'):
        rr=[r for r in runs.values() if r['variant']==variant]
        byvariant.append({'variant':variant,'attempts':len(rr),
            'parseable':sum(r['status']=='completed' for r in rr),
            'targeted_fact_passes':sum(score(r,rubrics[r['family_id']])['decision_pass'] for r in rr)})
    filtered_pairs_counts={m:{'accepted':sum(x['judgments'][m]['accepted'] is True for x in pairs),
                             'judged':len(pairs)} for m in models}
    return {'schema':'descriptive-judge-gap-v1','new_api_calls':0,'human_labels_added':0,
        'primary_judge':sorted({r['judge_model'] for r in primary}),
        'secondary_judge':sorted({r['judge_model'] for r in secondary}),
        'primary_by_generator':aggregate(primary,runs),
        'secondary_by_generator':aggregate(secondary,runs),
        'secondary_overlap':{'cases':len(overlap),
            'acceptance_disagreements':sum(r['primary_accepted']!=r['secondary_accepted'] for r in overlap),
            'rows':overlap},
        'sensitivity_exclusion':{'rule':'Exclude every change_control attempt and every EV conflict attempt; this is a post-hoc sensitivity analysis, not merely filtering the scorer known_task_defect flag.',
            'excluded_attempts':len(excluded_runs),
            'excluded_with_primary_judgment':sum(r['run_id'] in pby for r in excluded_runs),
            'remaining_attempts':len(runs)-len(excluded_runs),
            'remaining_judged':len(filtered),'by_generator':aggregate(filtered,runs),
            'excluded_run_ids':sorted(r['run_id'] for r in excluded_runs),
            'complete_matched_pairs':len(pairs),'matched_by_generator':filtered_pairs_counts,
            'discordant_pairs':sum(len({v['accepted'] for v in x['judgments'].values()})>1 for x in pairs),
            'pairs':pairs},
        'null_result':{'attempts':len(runs),'parseable':sum(r['status']=='completed' for r in runs.values()),
            'targeted_fact_passes':sum(score(r,rubrics[r['family_id']])['decision_pass'] for r in runs.values()),
            'by_variant':byvariant,
            'interpretation':'No incorrect targeted values among parseable outputs; seven attempts did not produce parseable output. This narrow, cued probe did not separate the models on its fact fields. It does not establish universal conflict resolution or whole-document correctness.'},
        'human_confirmed_prior_flags':manual,
        'historical_attempt_status_counts':dict(Counter(r['status'] for r in runs.values())),
        'limitations':[
            'These are model-judge verdicts, not an independently established generator-quality gap or causal self-preference effect.',
            'Generator identity was withheld from judge prompts, but style, verbosity, substantive quality and shared model-family tendencies may still matter.',
            'Unequal parseable coverage, task/renderer conditions, five source families and repeated dependent variants limit interpretation.',
            'The selected secondary sample accepts 7/7 GPT and 4/5 Claude outputs; it does not identify a symmetric self-preference pattern.',
            'The five human cases were selected post hoc and reviewed with knowledge of the hypothesis; their agreement cannot validate the full gap.',
            'The later Gemini calibration disagreement is a different judge and phase from the original GPT primary/Claude secondary analysis.'],
        'source_hashes':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(paths)}}


def main():
    out=ROOT/'output/strengthening_14';out.mkdir(parents=True,exist_ok=True)
    result=build(ROOT);(out/'judge-gap.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'primary':result['primary_by_generator'],'filtered':result['sensitivity_exclusion']['by_generator'],
                      'null':result['null_result'],'new_api_calls':0}))


if __name__=='__main__':main()
