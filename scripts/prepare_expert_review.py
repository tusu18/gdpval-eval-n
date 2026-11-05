"""Prepare blinded v1 output review packets, without inventing human judgments."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reviews/paired_v1_expert'

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')

def main():
    mapping=[];rows=[]
    for path in sorted((ROOT/'output/paired_v1/runs').glob('*.json')):
        run=json.loads(path.read_text());rid=run['run_id']
        review_id='R-'+hashlib.sha256(('expert-review-v1:'+rid).encode()).hexdigest()[:12]
        task=json.loads((ROOT/'data/paired_v1/solver'/(run['instance_id']+'.json')).read_text())
        artifact_files=[]
        for index,p in enumerate(sorted((ROOT/'output/paired_v1/artifacts'/rid).glob('*')),1):
            if p.suffix not in ['.docx','.xlsx']:continue
            target=OUT/'blinded'/review_id/f'deliverable-{index}{p.suffix}'
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
            artifact_files.append(str(target.relative_to(ROOT)))
        packet={'review_id':review_id,'instructions':'Judge the actual request and submitted deliverable. Source text may reveal the condition, but model labels, prior scores and model-judge opinions are withheld. Separate task defects, missing outputs, unsupported commitments and cosmetic issues. Quote exact source/output evidence. Do not infer a failed fact check from a page-count problem.','request':task['prompt'],'attachments':task['attachments'],'available_workspace_records':task['workspace'],'submission':run.get('final'),'native_deliverables':artifact_files,'output_available':bool(run.get('final'))}
        save(OUT/'blinded'/review_id/'packet.json',packet)
        mapping.append({'review_id':review_id,'run_id':rid,'family_id':run['family_id'],'variant':run['variant'],'model':run['model'],'trial':run['trial'],'packet':str((OUT/'blinded'/review_id/'packet.json').relative_to(ROOT))})
        blank={'reviewer_id':None,'qualification':None,'independent_of_author':None,'reviewed_at':None,'review_minutes':None,'accepted':None,'consequential_error':None,'evaluation_defect':None,'evidence':[{'output_quote_or_cell':None,'source_support':None,'business_consequence':None,'severity':None}],'notes':None}
        rows.append({'review_id':review_id,'reviewers':[dict(blank),dict(blank)],'adjudication':{'adjudicator_id':None,'final_accepted':None,'final_consequential_error':None,'final_evaluation_defect':None,'reason':None}})
    save(OUT/'private_coordinator_key.json',mapping)
    template=OUT/'output_reviews.template.json'
    save(template,{'status':'empty_template_no_human_reviews_completed','reviewer_guidance':'Copy this template before filling. Do not give private_coordinator_key.json, model-judge results, or model names to reviewers before adjudication. Log actual review time, not estimates. Investigate every critical label and disagreement. Reject empty or contradictory judgments.','rows':rows})
    print(json.dumps({'blind_packets':len(rows),'copied_native_artifacts':len(list((OUT/'blinded').rglob('*.docx')))+len(list((OUT/'blinded').rglob('*.xlsx'))),'human_reviews_completed':0}))

if __name__=='__main__':main()
