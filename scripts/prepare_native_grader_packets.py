"""Link new native bytes and mechanical checks to private grading evidence.

Offline only. This prepares inputs; it does not invent grader or human labels.
"""
import hashlib, json
from pathlib import Path
from evidence_grader import prepare_packet

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/native_workflow_01'
def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')

def main():
    maps={m['instance_id']:m for m in read(ROOT/'data/evidence_upgrade_01/grader/evidence_maps.json')}
    audit=read(OUT/'engineering_audit.json'); rows=[]
    for stage in ('native_transport_02','native_completion_03','native_completion_07','paired_native_08','native_backoff_probe_09'):
        if (ROOT/'output'/stage/'engineering_audit.json').exists():
            audit['runs']+=read(ROOT/'output'/stage/'engineering_audit.json')['runs']
    for r in audit['runs']:
        if r['status']!='submitted':continue
        raw=read(ROOT/r['raw_record']);task=read(ROOT/'data/evidence_upgrade_01/solver'/(raw['instance_id']+'.json'))
        cid='N-'+hashlib.sha256(('native-review-01:'+r['run_id']).encode()).hexdigest()[:8]
        trace={'tool_events':raw['tool_events'],'trace_complete':True}
        stage_root=(ROOT/r['raw_record']).parent.parent
        packet=prepare_packet(task,maps[task['instance_id']],stage_root/'workspaces'/r['run_id']/'submitted',trace)
        # Preserve the frozen extractor's uncertainty fields. Add actual engine
        # evidence as a separate record, never silently upgrade human visual QA.
        packet['native_execution_evidence']={
            'submitted_hashes_verified':all(f['submitted_hash_verified'] for f in r['submitted_files']),
            'rendered_final_file_count':len(r['submitted_files']),
            'files':r['submitted_files'],
            'visual_quality_human_validated':False,
            'business_quality_human_validated':False,
            'recalculation_scope':'artifact-tool recalculate and reopen; not a Microsoft Excel application check',
        }
        serialized=json.dumps(packet,ensure_ascii=False).replace(r['run_id'],'CASE_WORKSPACE').replace(r['model'],'MODEL_WITHHELD')
        dest=OUT/'grader_packets'/(cid+'.json');write(dest,json.loads(serialized))
        rows.append({'review_id':cid,'packet':str(dest.relative_to(ROOT)),
                     'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
                     'artifact_count':len(packet['artifacts']),
                     'native_contract_pass':packet['engineering_checks']['native_count_and_types_pass']})
    write(OUT/'grader_packets/manifest.json',{'status':'prepared_unjudged','packets':rows,'api_calls':0,
        'human_labels_created':0,'calibration_status':'pending human labels and comparable new judge outputs',
        'separation':'Private evidence maps remain outside solver and reviewer folders. No old judge label is reused for a new output.'})
    print(json.dumps({'prepared_native_grader_packets':len(rows),'paid_calls':0}))

if __name__=='__main__':main()
