"""Score exported human labels without inventing labels or modifying raw results."""
import argparse
import collections
import json
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[1]
def validated_rows(doc,known):
    if doc.get('schema')!='turing-human-review-v1':raise ValueError('Wrong review schema')
    result=[];seen=set()
    for r in doc.get('rows',[]):
        rid=r.get('review_id')
        if rid not in known or rid in seen:raise ValueError('Unknown or repeated review ID')
        seen.add(rid)
        if r.get('human_reviewed') is not True:continue
        if not str(doc.get('reviewer_id') or '').strip():raise ValueError('Reviewer ID required')
        for field in ['content_acceptable','consequential_error','evaluation_defect']:
            if r.get(field) not in ['yes','no','uncertain']:raise ValueError('Incomplete human judgment')
        minutes=r.get('review_minutes')
        if minutes is not None and (type(minutes) not in [int,float] or not 0<=minutes<float('inf')):raise ValueError('Invalid measured review time')
        if r['consequential_error']=='yes' and (not str(r.get('output_evidence') or '').strip() or not str(r.get('source_and_consequence') or '').strip()):raise ValueError('Consequential error needs source and output evidence')
        result.append(r)
    return result

def agreement(rows,mapping,field,judge_field):
    pairs=[]
    for r in rows:
        k=mapping[r['review_id']]
        if not k['calibration_queue'] or r['evaluation_defect']!='no' or r[field]=='uncertain':continue
        j=(k.get('primary_judge') or {}).get(judge_field)
        if type(j) is not bool:continue
        pairs.append((k['family_id'],r[field]=='yes',j))
    matrix=collections.Counter((h,j) for _,h,j in pairs)
    families=sorted({f for f,_,_ in pairs});interval=None
    if len(families)>=2:
        rng=random.Random(20261031);samples=[]
        blocks={f:[h==j for g,h,j in pairs if g==f] for f in families}
        for _ in range(10000):
            chosen=[v for f in rng.choices(families,k=len(families)) for v in blocks[f]]
            samples.append(sum(chosen)/len(chosen))
        samples.sort();interval=[samples[249],samples[9749]]
    return {'agree':sum(h==j for _,h,j in pairs),'reviewed_comparable':len(pairs),'task_families':len(families),'human_yes_judge_yes':matrix[(True,True)],'human_yes_judge_no':matrix[(True,False)],'human_no_judge_yes':matrix[(False,True)],'human_no_judge_no':matrix[(False,False)],'descriptive_family_bootstrap_95_interval':interval,'caveat':'Purposively selected outputs from at most five families; no population accuracy claim. Resampling only describes this sample. A degenerate all-agree interval is not certainty. Uncertain and task-defective judgments are excluded and remain visible in review counts.'}

def score(doc,mapping):
    rows=validated_rows(doc,mapping);cal=[r for r in rows if mapping[r['review_id']]['calibration_queue']]
    taxonomy=collections.Counter(r.get('category') or 'unassigned' for r in rows if mapping[r['review_id']]['failure_queue'])
    return {'status':'partial_human_review' if len(cal)<20 else 'calibration_queue_reviewed_not_release_validation','reviewer_id':doc.get('reviewer_id'),'qualification':doc.get('qualification'),'independent_of_author':doc.get('independent_of_author'),'human_attempt_reviews':len(rows),'calibration_reviewed':len(cal),'calibration_planned':20,'task_defects_flagged':sum(r['evaluation_defect']=='yes' for r in rows),'uncertain_task_validity':sum(r['evaluation_defect']=='uncertain' for r in rows),'content_agreement':agreement(rows,mapping,'content_acceptable','content_acceptable'),'critical_agreement':agreement(rows,mapping,'consequential_error','critical_error'),'human_taxonomy_counts':dict(taxonomy),'recorded_review_minutes':sum(r.get('review_minutes') or 0 for r in rows),'missing_review_times':sum(r.get('review_minutes') is None for r in rows),'model_recommendation':None,'limits':'One reviewer cannot establish inter-rater taxonomy reliability. Full expert qualification, customer thresholds, fresh-family validation and review labor rate remain separate requirements. No old issue-only label has been promoted to output acceptance.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('review_file',type=Path);args=parser.parse_args()
    doc=json.loads(args.review_file.read_text());mapping={r['review_id']:r for r in json.loads((ROOT/'output/submission_audit/private_review_key.json').read_text())}
    result=score(doc,mapping)
    target=ROOT/'output/submission_audit/human_review_summary.json'
    if target.exists():raise SystemExit('Existing human summary preserved; explicitly archive it before replacing with revised labels.')
    target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
