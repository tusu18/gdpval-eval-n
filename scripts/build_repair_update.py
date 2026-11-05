"""Create the current take-home brief and evidence card from the saved probe."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'output/repair_probe_01'; OUT=ROOT/'output/pdf'
S=json.loads((BASE/'summary.json').read_text())
R=json.loads((ROOT/'reviews/purchasing_calibration/review_assignment.json').read_text())
assert S['finished_runs']==16 and S['unresolved_reservations']==0
NAVY=colors.HexColor('#18324A');TEAL=colors.HexColor('#176D77');GRAY=colors.HexColor('#526274')
styles={name:ParagraphStyle(name,fontName='Helvetica-Bold' if name in ['title','head'] else 'Helvetica',fontSize=size,leading=leading,textColor=color,spaceAfter=7) for name,size,leading,color in [('title',22,26,NAVY),('head',12,15,TEAL),('body',9.7,13.3,NAVY),('small',8.1,10.9,GRAY),('cell',9,12,NAVY),('sub',10,14,GRAY)]}
def p(text,style='body'):return Paragraph(text,styles[style])
def table(headers,rows,widths):
    t=Table([[p('<b>'+escape(str(x))+'</b>','cell') for x in headers]]+[[p(escape(str(x)),'cell') for x in row] for row in rows],colWidths=widths,repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCE9EF')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F7F9')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    return t
def footer(c,d):
    c.setFont('Helvetica',8);c.setFillColor(GRAY);c.drawString(48,27,'Turing FDE take-home | 31 October 2026 | Private evaluation evidence');c.drawRightString(A4[0]-48,27,str(d.page))
def build(name,pages):
    flow=[]
    for i,(title,subtitle,items) in enumerate(pages):
        if i:flow.append(PageBreak())
        flow.extend([p(title,'title'),p(subtitle,'sub'),Spacer(1,4),*items])
    SimpleDocTemplate(str(OUT/name),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=42,bottomMargin=46).build(flow,onFirstPage=footer,onLaterPages=footer)

cost=S['campaign_charged_or_reserved_usd']; new=S['probe_reported_cost_usd']
one=[('Correct facts do not guarantee usable work','A paired GDPval study and a completed prompt-repair probe',[
    p('<b>The take-home:</b> evaluate a focused public GDPval slice, inspect consequential failures and propose a defensible data product. The main study covers five task families across purchasing, project management and shipping: 60 runs with GPT-6.1 Sol and Claude Sonnet 5.5.'),
    table(['Evidence','What it supports'],[
        ['Original study: 53/60 valid fact checks','All parseable outputs stated the tested facts correctly. Seven attempts failed to produce a valid final output.'],
        ['Original study: 18/35 page failures','Correct audit fields did not ensure a document that met the brief. All 12 exported workbooks passed value checks.'],
        ['Two human issue judgments','The project owner marked both selected purchasing issues as requiring material correction. These are issue judgments, not full-output acceptance or an error-rate estimate.'],
        ['New probe: 15/16 valid fact checks; 5/16 artifact passes','The 16-run matched prompt comparison found no aggregate improvement in page/format compliance. Substantive business-error review is pending.'],
    ],[193,306]),
    p('What the purchasing review exposed','head'),
    p('A plan asserted that buffer stock and air freight cover a supply gap while inventory was unknown. A workflow allowed provisional-price release with two approvers while the governing rule required three. The project owner marked each <b>Material correction required</b>. Qualifications, independence and review time remain undeclared; neither whole output has been accepted.'),
    p('What I would sell','head'),
    p('A scoped workflow diagnostic: preserve the professional objective, vary missing information and authority, retain the files and traces, and measure accepted deliverables, consequential errors and review-adjusted cost. The data opportunity is verified dependency and approval episodes. First prove a prompt/tool repair; expand to SFT or RL data only if confirmed failures persist and separate-family tests show transfer.'),
    p(f'<b>Budget:</b> ${cost:.2f} of the $25 API cap spent; ${new:.2f} for the new probe. No unresolved reservations. <b>Model choice:</b> withheld until human acceptance, error thresholds and review cost are available. No training was performed.'),
    p('<b>Task defect:</b> all 16 new attempts received notes dated before the proposal they supposedly copied. Results are descriptive diagnostics; a separate date correction is prepared and unrun. <b>Limits:</b> two selected families in the new probe, fixed text/tool harness and renderer, public pretraining exposure unknown, rights attestations pending. The new experiment is separate from the original 60 runs; 76 runs are not 76 independent tasks. Evaluation Cards document evidence, not superiority.','small'),
    p('Evidence: turing-repair-probe-and-pitch.pdf; output/repair_probe_01/summary.json; purchasing-review-pack.zip. Earlier research and v1 results remain unchanged.','small'),
])]
build('turing-submission-one-page.pdf',one)

pages=[('The repair probe is complete','A narrow experiment; no model winner or training claim',[
    p(f'<b>Delivered:</b> 16 new model runs, 15 native documents and rendered PDFs, full tool traces, a reconciled cost ledger and eight prespecified anonymous review packets. New API cost: <b>${new:.6f}</b>. Cumulative campaign cost: <b>${cost:.7f}</b>; remaining API budget: ${25-cost:.7f}.'),
    p('Two selected purchasing families, conflict condition only: supplier continuity and sourcing approvals. Each model ran the baseline and evidence-check prompt twice. Both arms shared inputs, tools, medium reasoning, six-call and 9,000-output-token limits, and the same fixed document renderer. The protocol and inputs were hashed before paid calls.'),
    table(['Measured endpoint','Baseline','Evidence check'],[
        ['Valid final output + tested facts correct','8/8','7/8'],
        ['Native document and requested page limit','3/8','2/8'],
        ['Read governing record and decision register','8/8','8/8'],
        ['Human accepted / consequential error','Not measured','Not measured'],
    ],[285,107,107]),
    p('What changed, and what did not','head'),
    p('The checklist asks the model to reconcile deadlines and resources, preserve mandatory approvals in exceptions, separate proposals from confirmed facts and align the final document with its audit fields. It contains no task-specific answer. The measured artifact result declined by one pass in eight paired comparisons. Correctness of substantive plans is still unmeasured; this result does not establish that the checklist helps or harms business reasoning.'),
    p('One response stopped normally but contained malformed JSON. Its raw text is retained. It was neither repaired nor replaced. All 15 parseable outputs passed the frozen audit fields; ten exceeded the 2-3-page constraint. A parsing or pagination failure is a delivery failure, not by itself proof of a wrong commercial decision.'),
    p('<b>Post-run task defect:</b> copied notes are dated 2025-06-23, but the register dates the proposal they copy to 2026-10-22. All 16 attempts received this inconsistency. The same defect in both arms does not prove it had no effect. These are descriptive diagnostics, not a validated repair or workplace-reliability result. Frozen inputs are preserved; five affected candidate instances have a separate, unrun date correction.'),
    p('The original v1 study remains separate: 60 runs and $4.391054, including all model-review attempts. v1 used different tasks/harness details and output limits. Its change from v1 to this probe is not a causal prompt-repair estimate. The two underlying families, not the 16 runs, determine the breadth of this experiment. No population confidence claim is made.'),
    p('For reviewers: complete the anonymous packet before looking at the model-specific table on the next page. The reviewer already knows the hypothesis, so this is identity-masked review, not fully blinded independent validation.','small'),
])]
rows=[]
for g in S['groups']:
    name='Claude Sonnet 5.5' if g['model'].startswith('anthropic') else 'GPT-6.1 Sol'
    arm='Baseline' if g['arm']=='baseline' else 'Evidence check'
    rows.append([name+' / '+arm,f"{g['decision_passes']}/4",f"{g['artifact_constraint_passes']}/4",f"${g['solver_cost_usd']:.4f}"])
pages.append(('Read the result at the right level','Mechanical checks are diagnostics; human acceptance is the product metric',[
    table(['System / prompt','Valid facts','Artifact pass','API cost'],rows,[238,80,94,87]),
    p('Each row contains two families with two repeats. The artifact gate means one valid DOCX, a successful render and compliance with the page requirement. It does not assess reasoning. In GPT, one paired page pass was lost and one gained; Claude lost one. A lower token bill does not establish lower cost per accepted deliverable.'),
    p('Use these decision metrics','head'),
    table(['Metric','Definition and decision use'],[
        ['Accepted deliverable rate','Human-reviewed substantive usability under the brief, reported with delivery/page gates. Missing output fails acceptance. Keep unreviewed outputs unknown.'],
        ['Consequential-error rate','A supported material decision error, unsupported commitment or approval bypass. Record the exact source, output passage and consequence. Do not label missing output error-free.'],
        ['Total cost per accepted deliverable','Sum all solver attempts, tool costs and actual review minutes times labor rate; divide by human-accepted deliveries. If none are accepted, no finite cost-per-accept can be claimed. Separate study setup costs.'],
        ['Repair effect','Evidence-check minus baseline on the same family/model/trial. Report paired transitions. Use family-level uncertainty only when enough independent families are sampled.'],
        ['Evaluation defects / reviewer agreement','Report unsolvable or ambiguous tasks separately; preserve exclusions and cost. Double-review a prespecified sample. Two cases reviewed by one person do not establish agreement.'],
    ],[156,343]),
    p('Selection rule','head'),
    p('Choose the lowest total cost per accepted deliverable only among configurations meeting customer-approved acceptance and consequential-error thresholds, with uncertainty and permissions accounted for. All of these gates remain open. This small, failure-targeted sample cannot certify a low error ceiling. No model is selected.'),
]))
pages.append(('Human review now changes the evidence','Two old issues confirmed; eight new attempts await full review',[
    p('The project owner volunteered to review purchasing cases and answered <b>Material correction required</b> for both selected v1 issues. The exact replies are stored. No reason, qualification, independence declaration or measured review time was supplied; those fields remain empty.'),
    table(['Issue reviewed','Repair proposed by the assistant'],[
        ['A - Supplier continuity: unknown stock, 21-day cutoff, months to redevelop; table nevertheless says stock and air freight cover the gap.','Replace the assurance with a conditional continuity plan. Confirm usable stock, quantify coverage and preserve residual downtime unless a bridge or qualified alternative is secured.'],
        ['B - Price approval: provisional release names Program and Purchase while the governing rule also requires Finance.','Require all three approvers for provisional release, or maintain a hold until a separately authorized exception is evidenced. An undecided cap does not supply approval.'],
    ],[239,260]),
    p('These judgments support showing two actionable examples in the take-home. They do not support a model-wide consequential-error rate, whole-document acceptance, task validity or independent expert certification. They are also not labels for the new probe.'),
    p('Next review package','head'),
    p('purchasing-review-pack.zip contains every first repeat from the frozen probe: eight attempts, seven final documents and one explicit no-output record. No failed first repeat was replaced by its successful second repeat. Each packet includes the complete task evidence and actual clarification exchanges; model and prompt-arm labels are omitted. The coordinator mapping stays outside the reviewer package.'),
    p('For P01-P08, record accepted yes/no/uncertain, consequential error yes/no/uncertain, evaluation defect yes/no, supporting pages and actual minutes. Record your purchasing role and experience once. For the no-output attempt, acceptance is no; substantive decision error remains unknown unless another supplied record supports it. Do not guess from its paired counterpart.'),
    p('After those judgments, inspect all matched transitions and any disagreements. If a checklist still leaves a confirmed dependency error, test a targeted tool improvement on separate development families: explicit supply-coverage inputs, an approval-state check or renderer feedback. Freeze that design before untouched-family evaluation. Do not keep modifying these test families and claim generalization.'),
]))
pages.append(('Sell a verified workflow diagnostic','Provenance, contamination controls and a bounded research offer',[
    p('Where the data came from','head'),
    p('Public GDPval tasks were pinned to revision 11e7900cdcac61bc4daf59e65feb238acda98fbf. The assistant authored deterministic local transformations and three separate fictional candidate episodes. No teacher-generation API calls created these task facts. Seeds 20261030/20261031 shuffle run order; they do not create semantic diversity or reproducible model sampling.'),
    p('The five GDPval-derived and three original families comprise 24 v2 candidate instances. The 16-run probe uses only two GDPval-derived conflict instances; the full 192-run matrix has not run. A separate v2.1 candidate repairs the impossible copied-note dates in five instances, with original inputs and outcomes preserved. That correction has no model results or independent validation. Original cases include landed cost, release capacity and delivery clarification. They have engineering checks, but domain validation and ownership attestations are pending. No commercial rights-cleared dataset claim is made.'),
    p('How contamination is controlled','head'),
    p('No training was performed. Every current evaluation family and its descendants remain excluded from any later training. Grader truth is outside the solver workspace; frozen hashes and per-run provenance are retained. Public pretraining exposure is unknown. Because the prompts were developed after inspecting v1 issues, these two families are now diagnostic/development evidence; a future generalization claim needs fresh untouched template and scenario lineages.'),
    p('The researcher pitch','head'),
    p('<b>OpenAI:</b> "The agent can state the approved fact and still produce an unusable or internally inconsistent professional deliverable. This small GDPval study gives you inspectable files, paired workflow conditions and evaluator defects. We tested a checklist before proposing training. It did not improve the artifact gate; its business effect awaits review."'),
    p('<b>Anthropic:</b> "Retrieving the governing record was successful in all 16 probe attempts. The remaining question is whether the final workflow preserves that authority and keeps unconfirmed resources conditional. We retain the full context and human judgments so the target is an observable operational failure, not disagreement with a stylistic judge."'),
    p('The commercial ask','head'),
    p('"Start with permissioned tasks from one customer workflow. Agree on acceptance and consequential-error criteria, calibrate reviewers and compare prompt/tool repairs at matched budgets. Select by review-adjusted cost among systems that meet the error threshold. Buy a training-data expansion only for persistent verified failures, using separate training lineages and an untouched transfer test."'),
    p('A 15-minute walkthrough: 2 minutes on the task and study; 4 on the two reviewed failures; 4 on the repair result and limits; 3 on the diagnostic offer; 2 on provenance and model-selection questions. The concrete engineering improvements are explicit provenance, failure evidence and decision gates. No measured superiority over AfterQuery or GDPval is established.'),
    p('Primary research: <link href="https://arxiv.org/html/2510.04374v1" color="#176D77">GDPval</link> motivates professional deliverables and its one-shot/context limitations; <link href="https://arxiv.org/html/2606.09809v2" color="#176D77">Evaluation Cards</link> informs the evidence record. Documentation does not establish rigorous evaluation or dataset superiority. The earlier research report contains the broader literature review.','small'),
]))
build('turing-repair-probe-and-pitch.pdf',pages)

card={
    'schema':'local-evidence-card-repair-probe-01-not-official-schema',
    'status':'mechanical_results_complete_human_output_review_pending',
    'summary_view':{'measures':'A matched prompt repair on two selected purchasing conflict tasks; strict audit fields and native document constraints.', 'main_caveat':'All 16 attempts share a chronological inconsistency in the task evidence. Two selected, previously inspected families; no independent task validation or full-output human acceptance.', 'intended_use':'A take-home failure analysis and prompt-repair diagnostic, not model release certification or a training-value claim.'},
    'evidence':{'protocol':'../../config/repair_probe_01.json','summary':'summary.json','per_run_scores':'scores.json','task_defects':'task_defects.json','unrun_correction':'../../data/paired_v2_1/manifest.json','raw_runs':'runs/','costs':'ledger.json','rendered_pages':'artifact_qa/page_checks.json','human_review':'../../reviews/repair_probe_01/reviewer_files/review_form.template.json','historical_issue_judgments':'../../reviews/purchasing_calibration/review_assignment.json'},
    'measurements':{'runs':16,'business_families':2,'valid_output_and_targeted_facts':15,'artifact_constraint_pass':5,'consequential_error_rate':None,'expert_acceptance_rate':None,'human_full_output_reviews':0,'known_task_defect_attempts':16,'historical_user_issue_judgments':sum(c['judgment'] is not None for c in R['cases'])},
    'budget':{k:S[k] for k in ['probe_reported_cost_usd','campaign_charged_or_reserved_usd','unresolved_reservations','campaign_cap_usd']},
    'validation':{'independent_task_review':False,'reviewer_qualification':None,'commercial_rights_attestation':False,'tests':'13 runner tests and 18 v2 behavioral tests passed before final packaging; 108 candidate preflight checks.'},
    'contamination':{'training_steps':0,'current_families_training_eligible':False,'public_pretraining_exposure':'unknown','generalization_holdout':'These inspected families cannot serve as an untouched test of this repair. Fresh scenario/template lineages are required.'},
    'selection':{'recommended_model':None,'reason':'Expert acceptance, consequential-error labels, customer thresholds, review labor cost and representative validation remain incomplete.'}
}
(BASE/'evaluation_card.json').write_text(json.dumps(card,indent=2)+'\n')
print(json.dumps({'one_page':'turing-submission-one-page.pdf','report':'turing-repair-probe-and-pitch.pdf','report_pages_intended':len(pages),'card':'output/repair_probe_01/evaluation_card.json'}))
