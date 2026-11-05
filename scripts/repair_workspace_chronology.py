"""Detect impossible note/proposal dates; create an unrun successor, never edit inputs."""
from datetime import date
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
def chronology_defect(task):
    note=task.get('attachments',{}).get('working-notes.txt','')
    register=task.get('workspace',{}).get('project/decision-register.txt','')
    copied=re.search(r'copied on (\d{4}-\d{2}-\d{2}) from a revision-3 proposal',note)
    created=re.search(r'planning/proposal-r3\.txt was created (\d{4}-\d{2}-\d{2})',register)
    if copied and created and date.fromisoformat(copied[1])<date.fromisoformat(created[1]):
        return {'copied_date':copied[1],'proposal_created_date':created[1],'issue':'Working notes predate the proposal they claim to copy.'}
    return None

def main():
    dest=ROOT/'data/paired_v2_1/solver';dest.mkdir(parents=True,exist_ok=True)
    if (ROOT/'output/paired_v2_1/runs').exists():raise SystemExit('Refuse to rebuild an executed successor.')
    defects=[];files=[]
    for path in sorted((ROOT/'data/paired_v2/solver').glob('*.json')):
        original=path.read_bytes();task=json.loads(original);issue=chronology_defect(task)
        if issue:
            defects.append({'instance_id':task['instance_id'],**issue})
            task['attachments']['working-notes.txt']=task['attachments']['working-notes.txt'].replace('copied on '+issue['copied_date'],'copied on '+issue['proposal_created_date'])
        task['parent_v2_sha256']=hashlib.sha256(original).hexdigest()
        task['version']='paired-v2.1-chronology-candidate'
        assert chronology_defect(task) is None
        out=dest/path.name;out.write_text(json.dumps(task,indent=2)+'\n')
        files.append({'path':str(out.relative_to(ROOT)),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'parent_sha256':task['parent_v2_sha256'],'changed_note_date':issue is not None})
    affected=[json.loads(p.read_text())['run_id'] for p in (ROOT/'output/repair_probe_01/runs').glob('*.json')]
    record={'defect_id':'v2-note-proposal-chronology','discovered_during':'Post-run visual inspection of reviewer source packet','description':'Working notes copied on 2025-06-23 claim to come from a revision-3 proposal which the v2 register says was created 2026-10-22. The date contradiction was inherited when v1 notes were reused with a new v2 register.','affected_candidate_instances':defects,'affected_probe_run_ids':sorted(affected),'impact':'All 16 probe attempts share the same task chronology defect. Mechanical outcomes remain descriptive, but the experiment is not validated workplace-reliability evidence. Whether individual business judgments remain interpretable requires domain review. No assumption of zero effect on model behavior.','disposition':'Preserve all original inputs, raw runs, costs and scores; flag all affected attempts. Do not impute corrected-task outcomes or silently rerun.','repair':'Separate unrun v2.1 candidates align the five copied-note dates to the proposal creation date, retaining status, facts, tools, objectives and deliverables. This is an assistant-authored synthetic date correction, not source GDPval evidence.','independent_validation':False,'corrected_candidate_model_runs':0,'successor_manifest':'../../data/paired_v2_1/manifest.json'}
    (ROOT/'output/repair_probe_01/task_defects.json').write_text(json.dumps(record,indent=2)+'\n')
    manifest={'status':'unrun_chronology_repair_pending_independent_validation','parent':'data/paired_v2','instances':24,'changed_instances':len(defects),'reference_rubrics':'data/paired_v2/grader/rubrics.json','model_runs':0,'independent_task_reviews':0,'rights_attestations':0,'training_eligible':False,'files':files}
    (dest.parent/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'detected_defects':len(defects),'affected_probe_attempts':len(affected),'successor_instances':len(files),'successor_model_runs':0}))

if __name__=='__main__':main()
