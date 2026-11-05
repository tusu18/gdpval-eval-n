"""Offline gate and preparation integrity. Does not dispatch judges."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inspect(root=ROOT):
 cfg=json.loads((root/'config/evaluation_v5.json').read_text());manifest=json.loads((root/cfg['source']).read_text());problems=[];pending=[]
 responses=json.loads((root/'reviews/evaluation_v5/responses.json').read_text())['responses']
 for c in manifest['cases']:
  for key in ['source_packet','native_original']:
   expected=c['source_packet_sha256'] if key=='source_packet' else c['native_sha256']
   if digest(root/c[key])!=expected:problems.append(c['case_id']+':changed '+key)
  versions=[]
  for v in c['variants']:
   if digest(root/v['path'])!=v['sha256']:problems.append(c['case_id']+':changed '+v['label'])
   versions.append(json.loads((root/v['path']).read_text()))
  for other in versions[1:]:
   if versions[0]['source_documents']!=other['source_documents']:problems.append('sources differ')
   a,b=versions[0]['artifacts'][0]['units'],other['artifacts'][0]['units']
   if len(a)!=len(b) or [x['locator'] for x,y in zip(a,b) if x!=y]!=[c['target_locator']]:problems.append('non-target changes')
  expected={v['label']:v['sha256'] for v in c['variants']}
  for field in cfg['required_human_fields']:
   eligible=[r for r in responses if r.get('case_id')==c['case_id'] and r.get('field')==field and r.get('variant_hashes')==expected and r.get('answer_verbatim') and r.get('reviewer_id')]
   if not eligible or eligible[-1].get('value') is not True:pending.append(c['case_id']+':'+field)
 return {'checks_pass':not problems,'problems':problems,'pending_human_fields':pending,'completed_cases':sum(not any(x.startswith(c['case_id']+':') for x in pending) for c in manifest['cases']),'execution_enabled':cfg['execution_enabled'],'ready_for_judges':not problems and not pending and cfg['execution_enabled'],'judge_calls':0}
if __name__=='__main__':
 d=inspect();p=ROOT/'output/evaluation_v5/verification.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2)+'\n');print(json.dumps(d,indent=2))
