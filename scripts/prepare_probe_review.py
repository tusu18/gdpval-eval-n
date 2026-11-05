"""Publish all preselected first-repeat outputs for user review, without scores."""
import hashlib
import json
from pathlib import Path
import shutil
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Table,TableStyle
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'output/repair_probe_01';OUT=ROOT/'reviews/repair_probe_01'
body=ParagraphStyle('body',fontName='Helvetica',fontSize=9.5,leading=13,textColor=colors.HexColor('#18324A'),spaceAfter=8)
title=ParagraphStyle('title',parent=body,fontName='Helvetica-Bold',fontSize=20,leading=24,spaceAfter=12)
head=ParagraphStyle('head',parent=body,fontName='Helvetica-Bold',fontSize=11.5,leading=15,textColor=colors.HexColor('#176D77'))
def p(text,style=body):return Paragraph(text,style)
def pdf(path,items):
    path.parent.mkdir(parents=True,exist_ok=True)
    SimpleDocTemplate(str(path),pagesize=A4,leftMargin=46,rightMargin=46,topMargin=44,bottomMargin=44).build(items)
def save(path,x):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(x,indent=2)+'\n')

def main():
    cfg=json.loads((ROOT/'config/repair_probe_01.json').read_text())
    jobs=sorted([j for j in cfg['jobs'] if j['trial']==1],key=lambda j:hashlib.sha256(('human-probe-review:'+j['run_id']).encode()).hexdigest())
    if any(not (BASE/'runs'/(j['run_id']+'.json')).exists() for j in jobs):raise SystemExit('Wait for every prespecified first repeat; do not publish a selected subset.')
    lookup=[];forms=[];index=[]
    for n,job in enumerate(jobs,1):
        run=json.loads((BASE/'runs'/(job['run_id']+'.json')).read_text())
        if run['status']=='running':raise SystemExit('A prespecified first repeat is still running.')
        rid=f'P{n:02d}';family='Supplier continuity' if job['family_id']=='supplier_exit' else 'Sourcing approvals'
        dest=OUT/'reviewer_files'/rid;dest.mkdir(parents=True,exist_ok=True)
        docs=list((BASE/'artifacts'/job['run_id']).glob('*.docx'))
        rendered=list((BASE/'artifact_qa/documents'/job['run_id']).rglob('*.pdf'))
        for i,path in enumerate(docs,1):shutil.copyfile(path,dest/f'deliverable-{i}.docx')
        for i,path in enumerate(rendered,1):shutil.copyfile(path,dest/f'deliverable-{i}.pdf')
        if not rendered:(dest/'NO_RENDERED_OUTPUT.txt').write_text('No rendered final output was produced for this attempt. Record the acceptance outcome from the available evidence; do not invent missing content.\n')
        task=json.loads((ROOT/'data/paired_v2/solver'/(job['instance_id']+'.json')).read_text())
        source=[p(rid+' - '+family,title),p('Request supplied to the model',head),p(escape(task['prompt']).replace('\n','<br/>'))]
        for label,group in [('Attachments',task['attachments']),('Available operational records',task['workspace'])]:
            source.append(p(label,head))
            for name,content in group.items():source.extend([p(escape(name),head),p(escape(content).replace('\n','<br/>'))])
        source.extend([p('Clarification environment',head),p('No additional requester facts were scripted for these two families. Every clarification receives: No additional confirmed information is available for that question. Do not infer a new approval, capacity commitment, or appointment.')])
        for event in run.get('tool_events',[]):
            if event['tool']=='ask_requester':
                source.extend([p('Actual clarification exchange',head),p('<b>Question:</b> '+escape(event['arguments'].get('question',''))),p('<b>Reply:</b> '+escape(event['reply'].get('answer','')))])
        pdf(dest/'task-evidence.pdf',source)
        lookup.append({'review_id':rid,**job})
        forms.append({'review_id':rid,'reviewer_id':None,'qualification':None,'aware_of_study_hypothesis':True,'review_minutes':None,'accepted':None,'consequential_error':None,'evaluation_defect':None,'evidence':[{'output_page_and_quote':None,'source_support':None,'business_consequence':None}],'minimum_repair':None,'confidence':None})
        index.append([rid,family,f'{rid}/task-evidence.pdf',f'{rid}/deliverable-1.pdf' if rendered else 'No final output'])
    instructions=[p('Purchasing review: eight anonymous outputs',title),p('These are every first-repeat output from the prespecified repair probe. Models and prompt arms are withheld. The remaining repeat is a stability check; it is not substituted based on outcome. Your earlier two-case calibration concerns old v1 examples, not these new outputs.'),p('How to review',head),p('Open task-evidence.pdf and the complete deliverable for each ID. Decide whether it can be used for the requested purpose without substantive correction, whether any error changes a material decision or authorizes an unsupported commitment, and whether the task itself prevents a fair judgment. Respect the requested 2-3-page constraint, but keep pagination and consequential errors separate. A proposed action explicitly conditional on approval is not an invented completed action.'),p('Record actual review minutes, your purchasing role/experience, a source/output quotation for each substantive issue and the minimum repair. Use null/unknown when evidence is insufficient. One reviewer does not establish inter-rater reliability. You know the study hypothesis, so this is not fully blinded independent validation.'),p('Reply format',head),p('For each ID: accepted yes/no/uncertain; consequential error yes/no/uncertain; task defect yes/no; reason + page; review minutes. You can give those answers in chat or copy review_form.template.json before filling it.'),p('Files',head)]
    t=Table([[p('<b>'+x+'</b>') for x in ['ID','Task','Source','Output']]]+[[p(escape(x)) for x in row] for row in index],colWidths=[36,111,160,190])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCE9EF')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    instructions.insert(2,p('<b>Known task defect:</b> the notes say they were copied on 2025-06-23 from a proposal the register dates to 2026-10-22. All eight attempts received this inconsistency. Sources are preserved exactly as supplied. Record whether this prevents a fair judgment; do not attribute the task defect to the model. Corrected tasks have not been run.'))
    instructions.append(t);pdf(OUT/'reviewer_files/START-HERE.pdf',instructions)
    save(OUT/'private_coordinator_key.json',lookup)
    save(OUT/'reviewer_files/review_form.template.json',{'status':'pending_user_review','rows':forms})
    print(json.dumps({'first_repeat_review_packets':len(forms),'reviews_completed':0,'start_here':str(OUT/'reviewer_files/START-HERE.pdf')}))

if __name__=='__main__':main()
