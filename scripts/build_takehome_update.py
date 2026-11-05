"""Focused take-home submission and a separately labeled next-study/pitch guide."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/pdf'
S=json.loads((ROOT/'output/paired_v1/summary.json').read_text())
PREFLIGHT=json.loads((ROOT/'output/paired_v2/preflight.json').read_text())
NAVY=colors.HexColor('#18324A');TEAL=colors.HexColor('#176D77');GRAY=colors.HexColor('#526274')
styles={name:ParagraphStyle(name,fontName='Helvetica-Bold' if name in ['title','head'] else 'Helvetica',fontSize=size,leading=leading,textColor=color,spaceAfter=7) for name,size,leading,color in [('title',22,26,NAVY),('head',12,15,TEAL),('body',9.7,13.4,NAVY),('small',8.2,11,GRAY),('cell',9,12,NAVY),('sub',10,14,GRAY)]}

def p(text,style='body'):return Paragraph(text,styles[style])
def table(headers,rows,widths):
    t=Table([[p('<b>'+escape(str(x))+'</b>','cell') for x in headers]]+[[p(escape(str(x)),'cell') for x in row] for row in rows],colWidths=widths,repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCE9EF')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F7F9')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    return t
def footer(c,d):
    c.setFont('Helvetica',8);c.setFillColor(GRAY);c.drawString(48,28,'Turing FDE take-home | 31 October 2026 | Local research evidence');c.drawRightString(A4[0]-48,28,str(d.page))
def build(name,pages):
    flow=[]
    for i,(title,subtitle,items) in enumerate(pages):
        if i:flow.append(PageBreak())
        flow.extend([p(title,'title'),p(subtitle,'sub'),Spacer(1,5),*items])
    SimpleDocTemplate(str(OUT/name),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=43,bottomMargin=47).build(flow,onFirstPage=footer,onLaterPages=footer)

cost=S['total_api_reported_cost_usd']
one=[('Correct facts can still yield an unworkable plan','GDPval evaluation | Failure analysis | A specific data opportunity',[
    p(f'<b>Study:</b> Five public GDPval task families across purchasing, project management and shipping. Three versions per task, two models and two repeats: <b>60 runs; ${cost:.2f} total API spend</b>, including all review attempts. Models: GPT-6.1 Sol and Claude Sonnet 5.5. This controlled text/tool harness differs from official GDPval.'),
    table(['Measured result','Interpretation'],[
        ['53/60 targeted decision checks passed','Every parseable output gave the approved tested facts; seven final submissions were incomplete or invalid.'],
        ['18/35 bounded documents failed page constraints','Correct audit fields did not ensure a deliverable that met the original brief. All 12 shipment workbooks passed exported-value checks.'],
        ['21/56 provisionally usable outputs','Combined model content review and artifact gates. Four task-defective EV conflict runs excluded. This is not expert acceptance.'],
    ],[192,307]),
    p('A consequential failure candidate','head'),
    p('A supplier-exit plan correctly used the 21-day cutoff and 4-5-month redevelopment time. Its action table nevertheless said: <i>"Absent an agreement, buffer stock and air freight cover the gap."</i> The same output identified current inventory as unknown and admitted possible production interruption. That contradiction matters to an executive using the action table. Independent severity adjudication is pending.'),
    p('What better data would contain','head'),
    p('Verified workflow episodes coupling demand, usable inventory, production capacity, tooling dependencies and approvals. Include a correct conditional plan, plausible but unsupported commitments, source citations, and expert-labeled consequences. Evaluate on separate episode/template families. The measured gap motivates this data design; no training gain has been demonstrated.'),
    p('The offer to an AI lab','head'),
    p('<b>OpenAI:</b> a complementary professional-work slice showing when correct audit facts coexist with inconsistent deliverables, with paired traces and grader calibration. <b>Anthropic:</b> authority and dependency cases where newer drafts or proposed resources must not become commitments. For both: test a prompt/tool repair first, then require fresh-family transfer before buying a training-data expansion.'),
    p('<b>Limits:</b> Five purposively selected families; text extracts and a fixed renderer; model judges, not independent experts. Critical-label agreement was 10/12 double-reviewed outputs. Recovery did not reduce targeted decision passes relative to baseline. Public-source pretraining exposure and commercial reuse rights are unverified. Evaluation Cards document this evidence; they do not certify dataset quality.','small'),
    p('Evidence: paired-pilot-evidence-kit.zip and output/paired_v1/summary.json. The separate v2 candidate package is prepared but has no new model results. No training or external submission has been performed.','small'),
])]
build('turing-submission-one-page.pdf',one)

pages=[]
pages.append(('Keep the take-home as the product','Executed GDPval evidence first; next-study improvements second',[
    p('The assignment asks for an evaluation on public GDPval, careful failure analysis, a researcher-readable website or one-page document, and a 15-minute pitch. The final one-page document now leads with the observed gap between correct facts and executable professional work. The proposed new data remains a follow-up opportunity, not a replacement for the assigned dataset.'),
    table(['Assignment requirement','Evidence now available'],[
        ['Run and grade a focused public slice','60 runs on five selected GDPval families across three occupations. Frozen inputs, two systems, repeated trials, full costs and per-run records.'],
        ['Inspect important failures','Concrete artifact and output failures; assistant inspection of two substantive contradictions; disputed severity retained for domain review.'],
        ['Explain the data opportunity','State- and dependency-aware workplace episodes, with verified constraints and conditional decisions, rather than extra copies of the same prompt.'],
        ['Pitch to two researcher audiences','Audience-specific scripts on page 5, using the same measured evidence and explicitly separating evaluation value from unproven training value.'],
    ],[148,351]),
    p('What is ready and what is not','head'),
    p('<b>Ready:</b> a final one-page submission, raw v1 results, repaired v2 candidate inputs, original supplemental episodes, task-local search and clarification, blinded expert-review packets, and a model-selection rule that includes review cost.'),
    p('<b>Not completed:</b> independent domain review, rights attestations, customer error thresholds, a new model experiment, or any training. The code does not fill these gaps with model-judge opinions. No new paid calls were made.'),
    p(f'<b>Budget:</b> ${cost:.6f} already charged or reserved; ${25-cost:.6f} remains under the existing $25 campaign cap. A later executor must enforce that cumulative cap. The v2 preparation contains no paid execution path.'),
    p('The original five families and every v1 result are preserved. v2 is labeled a candidate protocol, not a completed or independently validated benchmark. A change in harness or output budget also prevents interpreting v1-v2 score changes as the causal effect of a repair.'),
]))
pages.append(('Show the evidence, including disagreement','A failure taxonomy tied to actual outputs',[
    table(['Type','Concrete evidence','Disposition'],[
        ['Output completion','Five GPT change-control outputs ended at the 6,500-token response limit. Two further submissions were invalid/non-JSON.','Seven missing outputs are execution outcomes; not proof of failed authority reasoning.'],
        ['Deliverable constraints','18 of 35 bounded buyer documents failed the 2-3-page requirement under the fixed renderer.','Measured usability constraint; record renderer dependence. Do not equate pagination with a wrong business decision.'],
        ['Unsupported continuity assurance','Supplier-exit recovery, Claude trial 2, page 2: buffer stock and air freight are said to cover the gap although inventory is unknown.','Candidate consequential contradiction, inspected in the rendered file. Human severity review pending.'],
        ['Approval exception inconsistency','Sourcing conflict, Claude trial 1, page 4: provisional price release names Program and Purchase; the next paragraph requires Finance too.','The two model reviewers disagreed on criticality. Preserve both readings for independent adjudication.'],
        ['Evaluation defect','EV conflict changed the volume attached to the quoted cost basis. Four affected runs remain in raw results.','Exclude those runs from the clean conflict contrast; repair the task, not the historical score.'],
    ],[105,221,173]),
    p('Why the supplier case is worth showing','head'),
    p('The plan knows the cutoff is 21 days and localization needs months. It also explicitly warns that production may be interrupted. The problem is an actionable timeline entry that contradicts those caveats. A correct fact checklist misses cross-section consistency and the difference between a proposed bridge and a confirmed supply plan.'),
    p('What would falsify the diagnosis','head'),
    p('If an independent reviewer can identify confirmed opening stock or a binding supply commitment sufficient to cover the gap, the stronger error interpretation should be revised. If the table is read only as a conditional proposal, severity may be lower. Show the full page and source, not an isolated quotation.'),
    p('Native evidence paths: output/paired_v1/artifact_qa/documents/supplier_exit__recovery__anthropic_claude-sonnet-5.5__r2/ (page 2); sourcing_approvals__conflict__anthropic_claude-sonnet-5.5__r1/ (page 4). Run JSON and both reviewer outputs remain in the evidence kit.','small'),
]))
pages.append(('A bounded next-study candidate','Eight families, 24 task instances; zero new model results',[
    p('The five GDPval-derived families remain a separate stratum. Their new workspace uses folders, search, readable records and scripted clarification. Every condition has the same tools and underlying records. The business objective and required deliverable remain the intended invariants; independent reviewers must verify that they actually do.'),
    p('Repair the EV ambiguity','head'),
    p('Production volume is now stated separately from an explicit, shared per-pack cost assumption. Assembly INR 20,000 and overhead INR 590 are held fixed at either forecast volume. This is clearly labeled an added synthetic assumption, not a newly discovered GDPval fact. It prevents the mutation from silently changing the quotation basis, but still requires a realism review.'),
    table(['Original supplemental episode','Recoverable fact and consequential choice'],[
        ['Supplier landed cost','500 units: approved Alder freight makes its order $23,600; Beacon costs $23,000. A newer, unapproved freight draft would reverse the recommendation.'],
        ['Release capacity','A sequential 6-hour rehearsal and 8-hour verification need 14 hours. Only 12 are approved. Proposed 24-hour capacity does not justify committing the release.'],
        ['Receiving appointment','Ground costs $90 but arrives Monday; Express costs $165 and arrives Friday. A targeted clarification confirms Friday 16:00 as the deadline.'],
    ],[160,339]),
    p('Provenance and rights','head'),
    p('These three episodes are original assistant-authored fictional cases with no copied external files and no teacher-generation API calls. They are candidates for rights clearance, not certified rights-cleared data. Owner attestation and independent domain review are empty, explicit fields. GDPval-derived commercial permissions remain unverified. No family is eligible for training.'),
    p(f'Automated preflight: {len(PREFLIGHT["checks"])} checks passed, covering frozen hashes, shared tools, deliverable contracts, access boundaries, arithmetic and reachable clarification. Eighteen behavioral tests cover leakage, unauthorized paths, uncertainty and model selection. These checks are engineering validation, not expert validation.'),
    p('The environment is still a small deterministic simulation, not a full enterprise filesystem. It is more structured than the three-record v1 workspace but should not be marketed as proven workplace realism. Seed 20261031 changes run order only; it does not generate independent semantic cases.','small'),
]))
pages.append(('Validation and model-choice gates','Make a release decision only when the evidence supports it',[
    p('<b>Task validation:</b> Two independent domain reviewers examine each triplet for unchanged objective, unchanged deliverable, reachable truth, clear authority, plausibility and supported consequences. Disagreements need adjudication. The author and automated checker cannot sign as independent reviewers.'),
    p('<b>Output review:</b> 60 blinded v1 packets and 59 native deliverables are prepared. Reviewers receive complete actual task evidence, including operational records; prior model scores and model identity are withheld. Conditions may still be inferred from the content. Record accepted/not accepted, consequential error, evaluation defect, exact evidence and actual review minutes.'),
    table(['Metric','Decision use'],[
        ['Expert acceptance','Required deliverable is substantively usable under the original brief; cosmetic preference alone is not a consequential failure.'],
        ['Consequential-error rate','Materially wrong recommendation, unsupported commitment or mandatory approval bypass. Every label needs source/output evidence.'],
        ['Total cost per accepted deliverable','All solver attempts plus measured expert-review cost, divided by accepted outputs. Report study setup cost separately.'],
        ['Uncertainty and reviewer disagreement','Keep variants and repeats within family. A small perfect sample is not proof of a low failure rate.'],
    ],[165,334]),
    p('The selector currently returns no recommendation','head'),
    p('Customer error and acceptance thresholds, reviewer labor cost and representative-sampling approval are unset. No independent expert labels exist. Once supplied, the rule compares the same prespecified family exposures across model/prompt configurations and selects the lowest total cost only among configurations meeting both uncertainty-adjusted thresholds.'),
    p('For optional release selection, one conflict trial per family is prespecified. Exact bounds assume independent sampled families; simultaneous bounds adjust for both endpoints and all compared configurations. Repeats cannot inflate n. Even 0 errors in 8 independent families gives an unadjusted one-sided 95% upper bound of about 31%; candidate-selection adjustment is stricter. This pilot cannot certify a 1% error ceiling.'),
    p('Prompt/tool repair before training','head'),
    p('Compare the baseline prompt with a generic evidence/dependency checklist using identical v2 tasks, tools and budgets. The checklist contains no task-specific answers. Freeze approved inputs before running. Only persistent, expert-confirmed failures justify separate training families. Later compare repair-only, SFT and RL on untouched evaluation lineages; require transfer and no unacceptable regression before making a training-value claim.'),
]))
pages.append(('The 15-minute researcher conversation','Specific to each audience; grounded in the same measured study',[
    table(['Time','What to show'],[
        ['0:00-2:00','State the business problem, public GDPval slice, $4.39 spend and narrow claim. Show the one-page result table.'],
        ['2:00-6:00 - OpenAI','Show correct audit facts beside the contradictory supplier action table. Explain paired task families and acceptance beyond fact extraction.'],
        ['6:00-10:00 - Anthropic','Show the approved-record trace and the provisional-release exception. Surface the reviewer disagreement and the distinction between retrieved policy and authorized action.'],
        ['10:00-12:00','Offer a scoped diagnostic pilot and a prompt/tool repair comparison. Explain what a training-data expansion would need to prove.'],
        ['12:00-15:00','Answer provenance, seeds, contamination, model choice, grader reliability and data-rights questions directly.'],
    ],[156,343]),
    p('OpenAI audience script','head'),
    p('"The model can state the right facts and still deliver an inconsistent professional plan. We ran a paired GDPval slice and preserved the actual files, traces and evaluator defects. I would use this data to measure the gap between fact correctness and deliverable acceptance, then test whether an evidence-checking repair closes it on new families. The pilot does not prove a general model ranking or training gain."'),
    p('Anthropic audience script','head'),
    p('"The agent retrieved the approved rule, but its proposed exception can undermine that rule in the final workflow. We expose the authority trail, exact artifact language and disagreement about severity. I would test whether your agent keeps proposed resources and approvals conditional through the whole deliverable. We would validate the cases and graders before calling the observed issues consequential failures."'),
    p('The commercial ask','head'),
    p('"Start with a paid workflow diagnostic on a small set of your actual, permissioned tasks. Agree on consequential-error and acceptance thresholds, calibrate expert review, and compare a targeted repair at equal budget. Expand to training data only where verified failures persist and fresh-family results show transfer. Buy inspectable coverage and verified outcomes, not row volume."'),
    p('Answering the hard questions','head'),
    p('<b>Where generated?</b> Local deterministic transformations of pinned GDPval inputs; the new supplemental episodes are separately authored fiction. <b>What seed?</b> Run order only. <b>Why these models?</b> Two available tool-capable vendors within the original price ceiling, not leaderboard selection. <b>Contamination?</b> No training here; public pretraining exposure unknown. <b>Better?</b> Better auditability is implemented; superior dataset or training performance is not established.'),
    p('Evaluation Cards inform the evidence structure, not the validity claim: https://arxiv.org/html/2606.09809v2. GDPval supplies the professional task source: https://arxiv.org/html/2510.04374v1. Both were reviewed in the earlier research report.','small'),
]))
build('turing-next-study-and-pitch.pdf',pages)
print(json.dumps({'one_page':'turing-submission-one-page.pdf','guide':'turing-next-study-and-pitch.pdf','guide_pages_intended':len(pages)}))

