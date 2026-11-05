"""Raw judge diagnostics plus a separately labeled, lossless quote-format repair.

Do not change raw judgments or primary calibration scores. A locator is stripped
only when the quoted value matches the identified native-artifact unit exactly.
This fixes a possible extract/quote interface mismatch, not semantic mistakes.
"""
import copy,json
from collections import Counter
from pathlib import Path
from evidence_grader import score_judgment
from run_completion_and_pairs import read,write,sha
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/grader_checks_05'
def normalize(packet,judgment):
    result=copy.deepcopy(judgment);changes=[];artifacts={a['id']:a for a in packet['artifacts']}
    for c in result.get('criteria',[]):
        revised=[]
        for e in c.get('evidence',[]):
            a=artifacts.get(e.get('artifact_id'));q=e.get('output_quote')
            if not a or not isinstance(q,str) or c.get('evidence_kind')!='quoted':revised.append(e);continue
            units={u['locator']:u['text'] for u in a['units']}
            parts=q.splitlines();decoded=[]
            for line in parts:
                loc,tab,value=line.partition('\t')
                if not tab or loc not in units or not value or value!=units[loc]:decoded=[];break
                decoded.append((loc,value))
            if decoded:
                for loc,value in decoded:revised.append({**e,'output_quote':value})
                changes.append({'criterion':c.get('id'),'artifact_id':a['id'],'original_quote':q,'verified_units':[loc for loc,_ in decoded],
                    'rule':'Exact native-unit value match; remove generated locator prefixes and separate multi-cell quotes.'})
            else:revised.append(e)
        if 'evidence' in c:c['evidence']=revised
    return result,changes
def main():
    cfg=read(ROOT/'config/grader_checks_05.json');rows=[];error_counts=Counter()
    for j in cfg['jobs']:
        path=OUT/'runs'/(j['id']+'.json')
        if not path.exists():continue
        r=read(path)
        if r['status']!='received':continue
        packet=read(ROOT/j['packet']);raw=r['assessment'];candidate,changes=normalize(packet,r.get('judgment',{}));derived=score_judgment(packet,candidate)
        for x in raw.get('errors',[]):error_counts[x.split(':')[-1]]+=1
        row={'id':j['id'],'cohort':j['cohort'],'raw_record_sha256':sha(path),'raw_status':raw['status'],
             'secondary_normalized_status':derived['status'],'exact_quote_format_changes':changes,'secondary_assessment':derived,
             'human_validated':False,'use_in_primary_calibration':False}
        if changes:row['secondary_judgment']=candidate
        write(OUT/'quote_format_diagnostics'/(j['id']+'.json'),row);rows.append(row)
    summary={'received_analyzed':len(rows),'raw_status_counts':dict(Counter(r['raw_status'] for r in rows)),
        'cohort_raw_status_counts':{cohort:dict(Counter(r['raw_status'] for r in rows if r['cohort']==cohort)) for cohort in sorted({r['cohort'] for r in rows})},
        'raw_validation_error_counts':dict(error_counts),'cases_with_exact_quote_format_changes':sum(bool(r['exact_quote_format_changes']) for r in rows),
        'invalid_raw_but_valid_after_exact_format_alignment':sum(r['raw_status']=='invalid_grader_evidence' and r['secondary_normalized_status']!='invalid_grader_evidence' for r in rows),
        'primary_calibration':'Use original responses and their raw validity, not the secondary normalized judgments.',
        'limitation':'Post-hoc interface diagnostic. No model call, semantic adjudication, human label or business acceptance is created.'}
    write(OUT/'quote_format_summary.json',summary);print(json.dumps(summary))
if __name__=='__main__':main()
