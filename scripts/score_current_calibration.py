"""Compare exported human reviews with the new blinded Gemini assessments."""
import argparse,copy,json
from pathlib import Path
from compare_human_reviews import reviewer_metrics
ROOT=Path(__file__).resolve().parents[1]
def score(doc,mapping,judgments):
    current=copy.deepcopy(mapping)
    for cid,row in current.items():
        r=judgments.get(cid,{});a=r.get('assessment',{})
        # Never backfill the new judge with the historical model's judgment.
        row['primary_judge']=None
        if r.get('status')=='received' and a.get('status')=='automated_assessment_not_human_acceptance':
            row['primary_judge']={'content_acceptable':a.get('content_acceptable'),'critical_error':a.get('consequential_error')}
    result=reviewer_metrics(doc,current)
    return {'schema':'current-human-calibration-v1','judge':'google/gemini-4-argon','results':result,
            'interpretation':'Only completed human judgments and valid comparable new grader responses. Unknown labels and task defects remain explicit exclusions. Agreement does not prove human expertise, independence or semantic correctness.','model_ranking':None}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('reviews',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    mapping={r['review_id']:r for r in json.loads((ROOT/'output/native_workflow_01/calibration_private_key.json').read_text())}
    judgments={r['id']:r for f in (ROOT/'output/grader_checks_05/runs').glob('*.json') if (r:=json.loads(f.read_text()))['cohort']=='historical_calibration'}
    result=score(json.loads(args.reviews.read_text()),mapping,judgments);args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'human_reviews':result['results']['human_completed'],'output':str(args.output)}))
