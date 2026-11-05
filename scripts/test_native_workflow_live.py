"""Four local engine smoke checks with constructed content, never model results."""
import copy,json
from pathlib import Path
from native_file_workflow import ROOT,NativeWorkspace,write

OUT=ROOT/'output/native_workflow_01/engineering_smoke'
def task(family='original_supplier_landed_cost'):
    return json.loads((ROOT/'data/evidence_upgrade_01/solver'/f'{family}__conflict.json').read_text())
def document(text):return {'title':'File workflow check','sections':[{'heading':'Result','paragraphs':[text]}]}
def inspect_all(env,name):
    r=env.call('inspect_file',{'filename':name});assert 'error' not in r,r
    for i in range(1,r['pages_or_sheet_views']+1):assert 'error' not in env.call('view_page',{'filename':name,'page':i})
    env.acknowledge_images(env.image_queue);env.image_queue=[]
    return r
def main():
    if (OUT/'results.json').exists():raise SystemExit('Smoke evidence already exists; use a new output folder for a new trial.')
    results=[]
    e=NativeWorkspace(task(),OUT/'docx_revision')
    assert e.call('write_document',{'filename':'memo.docx','content':document('Initial draft for local engine testing.')})['written']
    assert 'error' in e.call('submit_files',{'filenames':['memo.docx']})
    inspect_all(e,'memo.docx')
    assert e.call('write_document',{'filename':'memo.docx','content':document('Revised draft for local engine testing.')})['revision']==2
    assert 'error' in e.call('submit_files',{'filenames':['memo.docx']})
    result=inspect_all(e,'memo.docx');assert any('Revised draft' in u['text'] for u in result['native_content'])
    assert e.call('submit_files',{'filenames':['memo.docx']})['submitted']
    results.append({'check':'DOCX create render inspect revise submit with stale-review rejection','passed':True})

    t=task();t.update(deliverable_format='xlsx',deliverable_count=1)
    e=NativeWorkspace(t,OUT/'xlsx_recalculation')
    content={'sheets':[{'name':'Cost','rows':[['Item','Quantity','Unit cost','Total'],['Enclosures',500,42,'=B2*C2']],
       'header_row':0,'number_formats':[{'range':'C2:D2','format':'#,##0.00'}]}]}
    assert e.call('write_workbook',{'filename':'cost.xlsx','content':content})['written']
    first=inspect_all(e,'cost.xlsx');assert first['recalculated_cells'][0]['values'][1][3]==21000,first
    content['sheets'][0]['rows'][1][2]=43
    assert e.call('write_workbook',{'filename':'cost.xlsx','content':content})['written']
    second=inspect_all(e,'cost.xlsx');assert second['recalculated_cells'][0]['values'][1][3]==21500,second
    assert e.call('submit_files',{'filenames':['cost.xlsx']})['submitted']
    results.append({'check':'XLSX formula recomputes after input revision and native reopen','passed':True,'before':21000,'after':21500,'engine':'artifact-tool; Excel desktop not exercised'})

    e=NativeWorkspace(task('change_control'),OUT/'mixed_contract')
    for name in ['sop.docx','form.docx']:
        r=e.call('write_document',{'filename':name,'content':document('Constructed file-contract test. This is not a reference solution.')});assert r.get('written'),r
        inspect_all(e,name)
    content={'sheets':[{'name':'Tracker','rows':[['Change ID','Project','Date Submitted','Requestor','Summary','Risk Level','Status','Outcome','Last Updated By','Date Closed']], 'column_widths':[15,20,20,20,30,16,18,20,22,18]}]}
    r=e.call('write_workbook',{'filename':'tracker.xlsx','content':content});assert r.get('written'),r
    inspect_all(e,'tracker.xlsx');assert 'error' in e.call('submit_files',{'filenames':['sop.docx','form.docx']})
    assert e.call('submit_files',{'filenames':['sop.docx','form.docx','tracker.xlsx']})['submitted']
    results.append({'check':'Mixed SOP DOCX form DOCX tracker XLSX contract','passed':True})

    e=NativeWorkspace(task('original_delivery_appointment'),OUT/'source_access')
    assert 'error' in e.call('read_file',{'path':'../grader/evidence_maps.json'})
    assert 'error' in e.call('write_document',{'filename':'../escape.docx','content':document('Invalid path.')})
    r=e.call('ask_requester',{'question':'What is the latest receiving deadline?'})
    assert '2026-11-06 at 16:00' in r['answer'] and r['new_approval_granted'] is False
    results.append({'check':'Source isolation and recoverable clarification','passed':True})
    write(OUT/'results.json',{'status':'local_engine_checks_pass','checks':results,'model_runs':0,'human_domain_validation':False})
    print(json.dumps({'local_checks':len(results),'passed':all(r['passed'] for r in results),'model_runs':0}))
if __name__=='__main__':main()
