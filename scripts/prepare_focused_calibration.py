"""Package frozen historical calibration plus new native outputs for human review.

No grades are prefilled. Existing labels and historical packets are preserved.
The private mapping is written outside the reviewer folder.
"""
import hashlib,json,shutil
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Image
from pypdf import PdfReader,PdfWriter
from evidence_grader import extract_artifact

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reviews/calibration_ready_01';PRIVATE=ROOT/'output/native_workflow_01'
style=ParagraphStyle('body',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=8)
head=ParagraphStyle('head',parent=style,fontName='Helvetica-Bold',fontSize=14,leading=18,spaceBefore=12,keepWithNext=True)
small=ParagraphStyle('small',parent=style,fontSize=8.5,leading=11)
def p(text,s=style):return Paragraph(escape(text).replace('\n','<br/>'),s)
def write(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def paragraphs(text):return [p(t) for t in text.split('\n\n') if t.strip()]

def make_packet(case,folder):
    flow=[p('Case '+case['id'],head),p('Read the request, sources and entire output before recording a judgment. Model identity and automated grades are withheld. This is a selected diagnostic sample, not a population estimate.'),
          p('Requested work',head),*paragraphs(case['request'])]
    if case.get('output_status')=='unsubmitted_draft':
        flow.insert(2,p('DIAGNOSTIC DRAFT: These are the latest successfully written native files. They were never formally submitted. Review their content for diagnosis; do not count a usable draft as a completed delivery.',small))
    if case.get('solver_instructions'):
        flow += [p('Additional solver instructions',head),p(case['solver_instructions'],small),
                 p('Audit field names also disclosed to the solver: '+', '.join(case.get('audit_field_names',[])),small)]
    for title,content in list(case['attachments'].items())+list(case['workspace'].items()):
        flow += [p('Source '+title,head),*paragraphs(content)]
    for item in case.get('clarifications',[]):flow += [p('Available scripted clarification '+item['topic'],head),p(item['reply'])]
    flow += [p('Execution context',head),p(case['context'],small)]
    source=folder/'sources.pdf'
    SimpleDocTemplate(str(source),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=42,bottomMargin=44).build(flow)
    writer=PdfWriter();writer.append(str(source))
    rendered=[f for f in case['files'] if f['kind']=='pdf']
    for file in rendered:writer.append(str(OUT/file['path']))
    # Workbooks are supplied natively; include every extracted cell and formula in
    # the packet so no content depends on a partial thumbnail or cached summary.
    for file in case['files']:
        if file['kind']!='xlsx':continue
        artifact=extract_artifact(OUT/file['path']);flow=[p('Workbook '+file['label'],head),p('Open the accompanying XLSX to inspect formulas and usability. Rendered views are followed by every populated cell and formula. Empty cells remain available in the native file and rendered grid; they are not expanded into empty text rows. Cached results alone do not certify Excel recalculation.',small)]
        from PIL import Image as PILImage
        for preview in [f for f in case['files'] if f.get('preview_for')==file['label']]:
            path=OUT/preview['path']
            with PILImage.open(path) as im:w,h=im.size
            scale=min(499/w,610/h)
            flow += [p(preview['label'],small),Image(str(path),width=w*scale,height=h*scale),PageBreak()]
        flow.append(p('Populated cells and formulas',head))
        populated=[u for u in artifact['units'] if u['text'] not in ('',None)]
        flow.append(p(f"{len(populated)} populated entries; {len(artifact['units'])-len(populated)} empty entries omitted from this text listing. Zero values and formulas are retained.",small))
        for u in populated:flow.append(p(u['locator']+'  '+u['text'],small))
        xpdf=folder/(Path(file['path']).stem+'-cells.pdf');SimpleDocTemplate(str(xpdf),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=42,bottomMargin=44).build(flow);writer.append(str(xpdf))
    if not case['files']:
        missing=folder/'no-output.pdf';SimpleDocTemplate(str(missing),pagesize=A4).build([p('No submitted native file is available for this attempt.',head),p('Record whether the evidence permits an output judgment. Do not infer a consequential business error solely from missing output.')]);writer.append(str(missing))
    writer.add_metadata({'/Title':'Human review '+case['id'],'/Author':'Evaluation coordinator'})
    with (folder/'review-packet.pdf').open('wb') as f:writer.write(f)
    case['packet']='files/'+case['id']+'/review-packet.pdf';case['packet_pages']=len(writer.pages)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cfg=json.loads((ROOT/'config/native_workflow_01.json').read_text())
    data=json.loads((ROOT/'site/review/cases.js').read_text().removeprefix('window.REVIEW_DATA = ').removesuffix(';\n'))
    key=json.loads((ROOT/'output/submission_audit/private_review_key.json').read_text());keyby={k['review_id']:k for k in key}
    calibration=data['queues']['calibration'];behavior=[k['review_id'] for k in key if k['triage_category'] in ('approval_bypass','unsupported_continuity','unsupported_eligibility','missing_comparison')]
    historical=list(dict.fromkeys(calibration+behavior));by_id={c['id']:c for c in data['cases']};cases=[];private=[]
    for cid in historical:
        source=by_id[cid];folder=OUT/'files'/cid;folder.mkdir(parents=True,exist_ok=True)
        files=[]
        for rel in source['native_files']:
            src=ROOT/'site/review'/rel;dest=folder/src.name;shutil.copyfile(src,dest)
            files.append({'path':str(dest.relative_to(OUT)),'kind':dest.suffix[1:],'label':dest.name})
        case={'id':cid,'occupation':source['occupation'],'request':source['request'],'attachments':source['attachments'],
              'workspace':source['workspace'],'clarifications':[],'files':files,'batch':'historical',
              'context':'Historical run with extracted source text and a JSON-to-file renderer. The solver could not view or revise native files. The original task and original files are preserved here; later repairs have not been substituted.'}
        trace=source['observable_transcript']
        for call in trace.get('assistant_turns',[]):
            call['tool_calls']=[{'function':x.get('function')} for x in call.get('tool_calls') or []]
        write(folder/'observable-transcript.json',trace)
        case['transcript']='files/'+cid+'/observable-transcript.json'
        make_packet(case,folder);cases.append(case);private.append(keyby[cid])
    native=[];recovery=[];completion=[];upload_repair=[];paired=[];backoff_probe=[]
    stage_queues={'native_workflow_01':native,'native_transport_02':recovery,'native_completion_03':completion,'native_completion_07':upload_repair,'paired_native_08':paired,'native_backoff_probe_09':backoff_probe}
    stage_names={'native_workflow_01':'initial','native_transport_02':'recovery','native_completion_03':'completion','native_completion_07':'upload_repair','paired_native_08':'paired','native_backoff_probe_09':'backoff_probe'}
    run_paths=[p for stage in stage_queues for p in sorted((ROOT/'output'/stage/'runs').glob('*.json'))]
    for path in run_paths:
        r=json.loads(path.read_text())
        if r['status']=='running':continue
        stage_root=path.parent.parent;stage_name=stage_names[stage_root.name]
        cid='N-'+hashlib.sha256(('native-review-01:'+r['run_id']).encode()).hexdigest()[:8]
        stage_queues[stage_root.name].append(cid)
        task=json.loads((ROOT/'data/evidence_upgrade_01/solver'/(r['instance_id']+'.json')).read_text());folder=OUT/'files'/cid;folder.mkdir(parents=True,exist_ok=True);files=[]
        entries=r.get('submission',[]);output_status='submitted' if entries else 'none'
        if not entries:
            state=json.loads((stage_root/'workspaces'/r['run_id']/'state.json').read_text())
            entries=[{'filename':name,'revision':f['revision'],'authored_path':f['path'],'preview_paths':[v['path'] for v in f['previews']]} for name,f in state['files'].items()]
            if entries:output_status='unsubmitted_draft'
        prefix='deliverable' if output_status=='submitted' else 'draft'
        for i,entry in enumerate(entries,1):
            src=Path(entry['authored_path']) if entry.get('authored_path') else stage_root/'workspaces'/r['run_id']/'submitted'/entry['filename']
            dest=folder/f'{prefix}-{i}{src.suffix}';shutil.copyfile(src,dest);files.append({'path':str(dest.relative_to(OUT)),'kind':src.suffix[1:],'label':dest.name})
            if src.suffix=='.docx':
                pdfs=list((stage_root/'workspaces'/r['run_id']/'history'/entry['filename']/f'r{entry["revision"]}'/'render').glob('*.pdf'))
                if len(pdfs)!=1:raise ValueError('Missing or ambiguous render PDF: '+cid)
                dest=folder/f'{prefix}-{i}.pdf';shutil.copyfile(pdfs[0],dest);files.append({'path':str(dest.relative_to(OUT)),'kind':'pdf','label':dest.name})
            elif src.suffix=='.xlsx':
                for number,preview in enumerate(entry['preview_paths'],1):
                    png=folder/f'{prefix}-{i}-view-{number}.png';shutil.copyfile(preview,png)
                    files.append({'path':str(png.relative_to(OUT)),'kind':'png','label':png.name,'preview_for':dest.name})
        case={'id':cid,'occupation':task['occupation'],'request':task['prompt'],'attachments':task['attachments'],'workspace':task['workspace'],
              'clarifications':task.get('clarifications',[]),'files':files,'batch':'native',
              'output_status':output_status,
              'solver_instructions':cfg['system'],'audit_field_names':task['fact_keys'],
              'context':({'initial':'Initial native-file development attempt. ',
                          'recovery':'Post-hoc infrastructure recovery attempt. Only an infrastructure-failed original slot was restarted, sequentially with a different HTTP client. Same task and model limits. ',
                          'completion':'Continuation after account-limit increase. An unattempted or infrastructure-failed slot was restarted; earlier outcomes remain in a separate cohort. ',
                          'upload_repair':'Infrastructure continuation with repaired upload transport and one bounded identical-request network retry. Older outcomes and extra unknown charges are preserved. ',
                          'backoff_probe':'One post-hoc engineering probe of bounded identical-request retries and provider-directed waiting. It is separate from the matched study; prior failures are preserved. ',
                          'paired':'Fixed-model paired development study. Task-version membership and model identity are withheld for review. '}[stage_name])+
              'The solver could create, render, inspect, view images and revise outputs. These are selected, previously inspected task families, not a held-out test. Submission does not certify business correctness.'}
        if output_status=='unsubmitted_draft':case['context']+=' The files shown are unsubmitted drafts for diagnostic review; this attempt did not complete delivery.'
        make_packet(case,folder);cases.append(case)
        # Observable tool history excludes model identity, hidden reasoning and private rubric.
        trace={'events':r.get('tool_events',[]),'terminal_status':r['status'],
            'execution_error':'Execution failed; provider and account details withheld.' if r.get('error') else None,
            'image_exposures':[{k:v for k,v in e.items() if k!='path'} for e in r.get('image_exposures',[])],
            'assistant_turns':[
            {k:c.get(k) for k in ('turn','assistant_content','tool_calls','finish_reason')} for c in r.get('calls',[])]}
        # Remove coordinator workspace identifiers from error paths. Provider
        # tokens in tool-call IDs are unnecessary to inspect observable actions.
        for call in trace['assistant_turns']:
            call['tool_calls']=[{'function':x.get('function')} for x in call.get('tool_calls') or []]
        raw=json.dumps(trace,ensure_ascii=False).replace(r['run_id'],'CASE_WORKSPACE').replace(r['model'],'MODEL_WITHHELD')
        write(folder/'observable-transcript.json',json.loads(raw))
        case['transcript']='files/'+cid+'/observable-transcript.json'
        private.append({'review_id':cid,'run_id':r['run_id'],'family_id':r['family_id'],'model':r['model'],'calibration_queue':False,'failure_queue':False,'new_native_queue':True,'native_stage':stage_name,'condition':r.get('condition'),'native_output_status':output_status,'primary_judge':None})
    public={'schema':'focused-review-01','queues':{'calibration':calibration,'diagnostic_extra':[x for x in behavior if x not in calibration],'native':native,'recovery':recovery,'completion':completion,'upload_repair':upload_repair,'paired':paired,'backoff_probe':backoff_probe},'cases':cases,
            'selection_note':'20 frozen calibration cases plus six additional diagnostic cases after overlap removal; new native outputs are a separate development batch.'}
    (OUT/'cases.js').write_text('window.CASES = '+json.dumps(public,ensure_ascii=False).replace('</','<\\/')+';\n')
    shutil.copyfile(ROOT/'scripts/calibration_review_ui.html',OUT/'index.html')
    write(PRIVATE/'calibration_private_key.json',private)
    write(OUT/'manifest.json',{'historical_calibration':20,'historical_behavior_candidates':11,'overlap':5,'historical_unique':26,'new_native_cases':len(native),'recovery_cases':len(recovery),'completion_cases':len(completion),'upload_repair_cases':len(upload_repair),'paired_cases':len(paired),
                              'backoff_probe_cases':len(backoff_probe),'native_cases_with_submitted_files':sum(c.get('output_status')=='submitted' for c in cases),
                              'native_cases_with_unsubmitted_drafts':sum(c.get('output_status')=='unsubmitted_draft' for c in cases),
                              'human_labels_created':0,'model_grades_disclosed':False,'review_files':len(cases),
                              'frozen_rubric':{'content_acceptable':'Usable without substantive correction; cosmetic changes may be allowed.',
                                  'consequential_error':'A specific error materially changes a decision, misstates resources/cost, or bypasses required authority.',
                                  'evaluation_defect':'The source, contract or setup prevents fair attribution; explain the ambiguity.'},
                              'prior_labels':'Existing issue-only and uncertain partial labels remain in their original records; none are converted to acceptance.'})
    print(json.dumps({'review_cases':len(cases),'historical':26,'native':len(native),'recovery':len(recovery),'destination':str(OUT)}))
if __name__=='__main__':main()
