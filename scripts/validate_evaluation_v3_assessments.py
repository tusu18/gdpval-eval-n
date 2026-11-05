"""Check judgment contracts and quote provenance; never decide correctness."""
import json
import re
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/evaluation_v3'

def norm(x):return re.sub(r'\s+',' ',str(x)).strip()

def main():
    results=[]
    for path in sorted((OUT/'assessments').glob('*.json')):
        if path.stem=='validation':continue
        packet_path=OUT/'judge-packets'/path.stem/'packet.json'
        if not packet_path.exists():continue
        packet=json.loads(packet_path.read_text());judgment=json.loads(path.read_text())
        problems=[];quotes=[];items={}
        items['original_prompt']=packet['original_prompt']
        for item in packet['sources']+packet['artifacts']:
            ex=json.loads(Path(item['extraction']).read_text())
            text='\n'.join(u['text'] for u in ex['units'])
            for key in (item['id'],item.get('original_name'),item.get('submitted_filename'),item['path'],Path(item['path']).name):
                if key:items[key]=text
        expected={c['criterion_id'] for c in packet['rubric']['criteria']}
        criteria=judgment.get('criteria',[]);ids=[c.get('criterion_id') for c in criteria]
        if Counter(ids)!=Counter(expected):problems.append('Missing, duplicate, or unexpected criterion IDs')
        if judgment.get('rubric_sha256')!=packet['rubric_sha256']:problems.append('Rubric hash mismatch')
        if judgment.get('task_id')!=packet['task_id']:problems.append('Task ID mismatch')
        for c in criteria:
            verdict=c.get('verdict')
            if verdict not in ('pass','fail','uncertain','not_assessed'):problems.append(str(c.get('criterion_id'))+': invalid verdict')
            if verdict=='fail' and (type(c.get('severity')) is not int or not 1<=c['severity']<=5):problems.append(str(c.get('criterion_id'))+': failure missing severity 1-5')
            for field in ('source_evidence','output_evidence','counterevidence','operative_sections_inspected'):
                if not isinstance(c.get(field),list):problems.append(str(c.get('criterion_id'))+': '+field+' must be an array');continue
                for evidence in c[field]:
                    quote=evidence.get('quote') or evidence.get('supporting_quote')
                    if not quote:continue
                    ref=evidence.get('source') or evidence.get('artifact') or evidence.get('file')
                    content=items.get(ref,items.get(Path(str(ref)).name))
                    status='text_verified' if content is not None and norm(quote) in norm(content) else 'requires_manual_verification'
                    quotes.append({'criterion_id':c.get('criterion_id'),'field':field,'reference':ref,'locator':evidence.get('locator') or evidence.get('section_or_range'),'quote':quote,'status':status,'view_id':evidence.get('view_id'),'view_ids':evidence.get('view_ids')})
        expected_overall='project_rubric_fail' if any(c.get('verdict')=='fail' for c in criteria) else ('project_rubric_uncertain' if any(c.get('verdict') in ('uncertain','not_assessed') for c in criteria) else 'project_rubric_pass')
        if judgment.get('overall')!=expected_overall:problems.append('Overall does not follow frozen aggregation')
        results.append({'task_id':path.stem,'contract_problems':problems,'contract_valid':not problems,'criteria_counts':dict(Counter(c.get('verdict') for c in criteria)),'quotes':quotes,'quote_counts':dict(Counter(q['status'] for q in quotes)),'accuracy_or_human_acceptance_validated':False})
    dest=OUT/'assessments/validation.json';dest.parent.mkdir(exist_ok=True);dest.write_text(json.dumps({'checks':results,'interpretation':'Mechanical schema and quote checks only. Unmatched visual/numeric quotations require manual verification; they are retained and never silently discarded. Contract-valid does not mean correct.'},indent=2)+'\n')
    print(json.dumps([{'task_id':r['task_id'],'contract_valid':r['contract_valid'],'criteria_counts':r['criteria_counts'],'quote_counts':r['quote_counts']} for r in results]))

if __name__=='__main__':main()
