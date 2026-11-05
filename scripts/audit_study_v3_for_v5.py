"""Recompute into V5 only. Never overwrite historical packets, judgments or reports."""
import json,hashlib
from pathlib import Path
from collections import Counter
from judge_aggregation_v5 import aggregate
from evidence_grader_v2 import score_judgment
ROOT=Path(__file__).resolve().parents[1]
def main():
 latest={};hashes={}
 for p in sorted((ROOT/'output/study_v3/judge_runs').glob('*__sel*__*.json')):
  j=json.loads(p.read_text());key=(j['run_id'],j['judge']);version=p.name.split('__')[-2]
  if key not in latest or version>latest[key][0]:latest[key]=(version,j,p)
 stored=[];rescored=[]
 for version,j,p in latest.values():
  hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest();stored.append(j)
  row=dict(j)
  if j.get('status')=='received':
   packet=ROOT/'output/study_v3/judge_packets'/f'{j["run_id"]}__{version}.json'
   hashes[str(packet.relative_to(ROOT))]=hashlib.sha256(packet.read_bytes()).hexdigest()
   row['assessment']=score_judgment(json.loads(packet.read_text()),j.get('judgment') or {})
  rescored.append(row)
 result={'historical_results_unchanged':True,'new_api_calls':0,'stored_endpoint_reaggregation':aggregate(stored),'strict_coverage_rescore':aggregate(rescored),'rescore_statuses':dict(Counter((j.get('assessment') or {}).get('status',j['status']) for j in rescored)),'source_hashes':hashes,'interpretation':'Scorer/parser changes only, not improved model judgment. Older responses may lack the newly required coverage locations; excluded rather than treated as errors or passes.'}
 dest=ROOT/'output/evaluation_v5/historical-rescore.json';dest.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'stored_comparisons':result['stored_endpoint_reaggregation']['comparisons'],'strict_rescore_statuses':result['rescore_statuses']},indent=2))
if __name__=='__main__':main()
