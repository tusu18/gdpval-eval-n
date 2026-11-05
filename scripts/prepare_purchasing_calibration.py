"""Human calibration of two v1 issue candidates, not full-output acceptance."""
import json
import shutil
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reviews/purchasing_calibration';OUT.mkdir(parents=True,exist_ok=True)
style=ParagraphStyle('body',fontName='Helvetica',fontSize=10.5,leading=14.5,textColor=colors.HexColor('#18324A'),spaceAfter=10)
title=ParagraphStyle('title',parent=style,fontName='Helvetica-Bold',fontSize=22,leading=26,spaceAfter=12)
head=ParagraphStyle('head',parent=style,fontName='Helvetica-Bold',fontSize=12,textColor=colors.HexColor('#176D77'))
def p(text,s=style):return Paragraph(text,s)
def footer(c,d):
    c.setFont('Helvetica',8);c.drawString(46,26,'Purchasing issue review | Human judgment pending | 31 October 2026');c.drawRightString(A4[0]-46,26,str(d.page))
cases=[
    {'id':'A','run':'supplier_exit__recovery__anthropic_claude-sonnet-5.5__r2','stem':'Modlev_Tail_Lamp_LPI_Negotiation_Strategy','page':2,'title':'Supplier continuity','context':'The supplier stops supply in 21 calendar days; no extension has been agreed. Current demand is 800 sets/month. Electronics redevelopment takes 4-5 months and plastics 3-4 months; they may run in parallel. Tool transfer takes about 25 days. Starting inventory is not supplied. The requested deliverable is a 2-3-page negotiation and continuity strategy.','claim':'"LPI notice ends. Absent an agreement, buffer stock and air freight cover the gap."','surrounding':'Elsewhere on the same page the output says "Production may be interrupted for some months" and identifies the current stock level as unresolved. Its assumptions also state that no stock-on-hand data were provided. It proposes negotiating a supply bridge; it does not claim that a bridge is already agreed.','question':'Does the action-table statement require material correction before an executive could use the plan, or do the surrounding caveats make it acceptable? Consider a contradiction in an operational instruction separately from a conditional negotiation proposal.'},
    {'id':'B','run':'sourcing_approvals__conflict__anthropic_claude-sonnet-5.5__r1','stem':'Revised_Sourcing_Nomination_Workflow','page':4,'title':'Provisional commercial release','context':'The approved operational rule requires Finance controllers, Program Managers and Purchase to approve price-change requests. A newer Purchase-only proposal is unapproved. The requested output is a first-level revised sourcing workflow and blueprint for a digital platform; it is not an instruction to execute a purchase now.','claim':'"Provisional release: for urgent program needs, the vendor can proceed at a provisional price, subject to a cap, while the final price is settled. This must be recorded and approved by the Program Manager and Purchase."','surrounding':'The very next paragraph states that price changes need Finance, Program and Purchase approval, all three required. The table below repeats the three-way commercial approval rule. The document calls the provisional cap and thresholds open points for CPO decision.','question':'Does the provisional-release clause create a material approval bypass in the proposed workflow, or is it sufficiently constrained by the following rule and its draft status? Identify the exact change, if any, needed before the workflow could guide implementation.'},
]
flow=[p('Purchasing review: two specific issues',title),p('Please review the issue, its full context and the attached rendered page. This is not a request to approve the entire benchmark or certify a model. Your qualifications and review time should be recorded separately.'),p('Review categories',head),p('<b>Material correction:</b> could change a consequential business decision or permit an unauthorized operational commitment.<br/><b>Minor clarification:</b> wording should improve, but context adequately protects the decision.<br/><b>Acceptable in context:</b> no correction is necessary for this issue.<br/><b>Insufficient evidence:</b> identify the fact or document needed.'),p('The study author has discussed these examples with you, so this calibration is not fully blinded. It is separate from the anonymous new-output review. Existing model-judge labels are intentionally omitted here.'),PageBreak()]
for i,c in enumerate(cases):
    folder=ROOT/'output/paired_v1/artifact_qa/documents'/c['run']/c['stem']
    pdf=next(folder.glob('*.pdf'))
    shutil.copyfile(pdf,OUT/f'case-{c["id"]}-full-output.pdf')
    flow.extend([p('Case '+c['id']+': '+c['title'],title),p('Task evidence',head),p(c['context']),p('Statement to assess',head),p(c['claim']),p('Relevant surrounding context',head),p(c['surrounding']),p('Your judgment',head),p(c['question']),p('Category: ____________________<br/>Reason and source/output evidence: ____________________<br/>Minimum correction or missing evidence: ____________________<br/>Review minutes: ______'),p('The next page reproduces the relevant rendered output page. The complete native output is also provided as case-'+c['id']+'-full-output.pdf.'),PageBreak()])
    img=Image(str(folder/f'page-{c["page"]}.png'),width=490,height=634)
    flow.extend([p('Case '+c['id']+': rendered output excerpt',title),img])
    if i<len(cases)-1:flow.append(PageBreak())
dest=ROOT/'output/pdf/purchasing-calibration-review.pdf'
SimpleDocTemplate(str(dest),pagesize=A4,leftMargin=46,rightMargin=46,topMargin=42,bottomMargin=42).build(flow,onFirstPage=footer,onLaterPages=footer)
assignment={'reviewer':'user_volunteered','qualification':None,'independent_of_task_author':None,'aware_of_study_hypothesis':True,'scope':'Specific issue severity only; not full deliverable acceptance or full task validation.','status':'pending','cases':[{'case_id':c['id'],'run_id':c['run'],'judgment':None,'reason':None,'review_minutes':None} for c in cases]}
assignment_path=OUT/'review_assignment.json'
if not assignment_path.exists():
    assignment_path.write_text(json.dumps(assignment,indent=2)+'\n')
saved=json.loads(assignment_path.read_text())
print(json.dumps({'review_pdf':str(dest),'cases':2,'human_issue_reviews_completed':sum(x['judgment'] is not None for x in saved['cases'])}))
