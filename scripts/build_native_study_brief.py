"""Build a current, evidence-linked briefing and separate lab pitches."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/native_workflow_01'
styles={
 'body':ParagraphStyle('body',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=8),
 'title':ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=23,leading=27,spaceAfter=13),
 'head':ParagraphStyle('head',fontName='Helvetica-Bold',fontSize=13,leading=17,spaceBefore=10,spaceAfter=7,keepWithNext=True),
 'small':ParagraphStyle('small',fontName='Helvetica',fontSize=8.2,leading=11,spaceAfter=6),
 'quote':ParagraphStyle('quote',fontName='Helvetica',fontSize=12,leading=17,leftIndent=12,rightIndent=12,spaceBefore=6,spaceAfter=12),
}
def p(t,s='body'):return Paragraph(escape(t),styles[s])
def table(headers,rows,widths):
 t=Table([[p(str(x),'small') for x in row] for row in [headers]+rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
 t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9eef1')),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#aebec7')),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f7f9fa')])]))
 return t
def footer(c,d):
 c.saveState();c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#536475'));c.drawString(48,25,'Turing take-home | Development evidence | 4 November 2026');c.drawRightString(A4[0]-48,25,str(d.page));c.restoreState()

def build(draft=False):
 a=json.loads((OUT/'engineering_audit.json').read_text());m=json.loads((ROOT/'reviews/calibration_ready_01/manifest.json').read_text())
 c=json.loads((OUT/'combined_study.json').read_text())
 if (not a['complete'] or not c['recovery']['execution_finished']) and not draft: raise ValueError('Finish execution before building the final briefing.')
 cost=c['cost']; modelrows=[]
 for r in c['by_model']:
  modelrows.append([r['model'],f"{r['initial_submitted']}/{r['initial_attempted']}",f"{r['recovery_submitted']}/{r['recovery_attempted']}",f"${r['reported_api_cost_usd']:.4f}",r['unresolved_charge_records']])
 failures={}
 for r in a['runs']:
  if r['status']!='submitted':failures[r['mechanical_attribution']]=failures.get(r['mechanical_attribution'],0)+1
 flow=[p(('IN PROGRESS: ' if draft else '')+'Measure reliable professional work','title'),
  p('The gap: a correct retrieved fact does not guarantee a usable, authorized final deliverable. The commercial ask is a fresh, permissioned GDPval-style diagnostic pilot with expert evidence, not resale of the public benchmark.','quote'),
  p('What we can demonstrate today','head'),
  p(f"The first pass produced {a['submitted_attempts']}/20 native submissions across five model families and four development tasks; {a['attempts_with_authored_native_files']} attempts wrote at least one native file. Fourteen slots failed for infrastructure reasons. Sequential recovery produced {c['recovery']['submitted_attempts']}/{c['recovery']['finished_attempts']} submissions from 14 selected restarts. Business acceptance remains unmeasured."),
  table(['Requested model','Initial*','Recovery*','API cost**','Unresolved'],modelrows,[202,63,71,76,87]),
  p('* Native submissions / attempted slots in that phase. Recovery restarts only infrastructure-failed slots; it is post-hoc and cannot establish a model ranking or causal repair effect. ** Provider-reported costs include both phases and failed attempts. Unresolved requests may add charges.','small'),
  p('What changed and why','head'),
  p('Models now create actual Word and Excel files, read them back, view rendered pages and revise them. Spreadsheets recalculate and reopen. Submission requires the exact file contract and current-revision inspection. These controls make file failures observable; they do not certify substantive correctness.'),
  p(f"Non-submission attribution: {json.dumps(failures,sort_keys=True)}. Full traces retain the provider responses and tool errors. These are engineering outcomes, not model honesty scores.",'small'),
  p(f"Recovery stopped on another account rejection; {c['recovery']['unattempted_count']} selected slots were not attempted. The service reported an in-flight credit limit. This does not establish the account cash balance or a model capability limit.",'small') if c['recovery']['account_or_rate_stop'] else p('Recovery execution status is recorded separately from the initial pass.','small'),
  p(f"Reported API cost: initial ${cost['initial_api_usd']:.6f}, recovery ${cost['recovery_api_usd']:.6f}, historical ${cost['historical_api_usd']:.7f}; cumulative ${cost['reported_cumulative_usd']:.7f}. Unresolved charge records: {cost['unresolved_charge_records']}. The user removed the former $25 cap. The two phases were bounded to 20 initial attempts and 14 infrastructure-only recovery slots.",'small'),
  p('Decision today: complete human calibration before selecting a model or selling a training-effect claim. No full-output human review, reliable consequential-error rate, or lowest cost per accepted deliverable is established.','body'),
  PageBreak(),p('OpenAI: sell a testable data hypothesis','title'),
  p('Opening pitch','head'),
  p('“We are testing which professional-work failures remain after the agent can inspect and revise real deliverables. Our public-task development study is a diagnostic. The product is a fresh, permissioned set with executable checks, expert preferences and source-grounded rationales. First establish that the failures survive your own tool and inference setup. Only then test whether targeted supervision helps on untouched task families.”','quote'),
  p('What the buyer gets','head'),
  p('Propose 30 newly authored task families, each with baseline, information-recovery and conflicting-evidence versions: 90 episodes. Allocate 10 families to development and 20 families to an untouched evaluation split. Preserve the objective and expected work across each triplet. This is a proposed diagnostic scale, not a guarantee of power or a collection already built.'),
  p('Every family includes a provenance and permission record, realistic workspace, allowed tools, authoritative facts, executable calculations and file checks, an expert rubric, native gold deliverables and a written rationale. Collect blind expert preference pairs from genuine alternative outputs; do not generate preferences merely by asking a model to prefer its own wording.'),
  p('The training decision','head'),
  p('Use matched prompt and tool repairs first. If human-confirmed substantive failures persist, build a separate training collection with distinct source organizations, templates and scenario lineages. A provisional second phase could contain 50 training families and at least 150 verified trajectories. Price and size that phase from measured authoring, review and correction time. Keep all evaluation family derivatives out of SFT, RL and prompt tuning.'),
  p('Success criteria','head'),
  p('Measure accepted deliverables, consequential errors, justified information recovery, and total cost. For a training intervention, compare pre/post or randomized systems at matched inference settings on fresh held-out families, with family-level paired uncertainty. Gains from selecting the best of several samples are selection gains, not training gains.'),
  p('Hard question: “Which failures would more data fix?”','head'),
  p('Current answer: none has been proven data-addressable. Two historical issues were judged to require material correction, but those were issue-only labels. This study supplies observable native work and a route to a controlled intervention. I would stop the data sale if task repair, tools or compute resolve the problem.'),
  p('Pilot ask: begin with five of the proposed development families on your own agent stack. Measure expert authoring and review effort before quoting the full 30-family collection. Retire evaluation families from the untouched pool once their feedback informs tuning.','small'),
  PageBreak(),p('Anthropic: sell auditable decisions','title'),
  p('Opening pitch','head'),
  p('“Can the agent preserve uncertainty and authority all the way into the final document? We test unsupported commitments, conflicting approvals, invented resources and claims of completed work. Each finding must connect a source to an exact output passage and a business consequence. We also include cases where proceeding is correct, so a system cannot earn a good score simply by withholding useful work.”','quote'),
  p('Why this slice','head'),
  p('Purchasing exposes concrete decisions: total landed cost, delivery feasibility, supplier continuity and who may authorize a price change. A polished memo can repeat the approved rule and still undermine it in an action table. Project change control adds cross-file consistency between a procedure, request form and tracker. Coverage remains these selected workflows, not entire occupations.'),
  p('What we actually know','head'),
  p('The project owner labeled two historical issues “material correction required”: an unsupported continuity assurance and an approval-exception inconsistency. These are not whole-output acceptance labels and do not establish intentional deception. In 12 historical dual-judge cases, the 10 agreements were all shared negatives; each judge flagged a different positive. This does not validate error detection.'),
  p('The grader contract','head'),
  p('Require exact source and output evidence for a consequential-error claim. Validate the judge against the frozen 20-case human calibration queue; report the full confusion matrix, missed consequential errors and false accepts with their denominators. No positive human cases means sensitivity is unmeasurable. A different judge family adds diversity, not ground truth or proof against self-preference.'),
  p('Reward-gaming controls','head'),
  p('Use substance-changing mutations, equivalent paraphrases, cosmetic controls and legitimate proceed/hold pairs. A real quotation alone cannot earn a pass if the interpretation is wrong. Compare source-consistent decisions across every delivered file. The existing 36 constructed challenge cases are engineering checks awaiting independent semantic validation, not proof the judge is robust.'),
  p('Hard questions','head'),
  p('“Can another reviewer reproduce the taxonomy?” Unknown: obtain independent labels, report category counts, agreement and adjudicated disputes. “Show three traces behind the top category.” The packets contain observable transcripts; name a top human-confirmed category only after review. The current taxonomy remains assistant-generated triage.'),
  p('Pilot ask: one purchasing workflow owner, two qualified reviewers and agreed error/acceptance gates. Deliver a private task pack and a human-calibrated grader report before considering a training-data order.','small'),
  PageBreak(),p('Make the metrics decision-relevant','title'),
  table(['Metric','Definition and decision use'],[
   ['Human acceptance','Usable without substantive correction / prespecified attempts on valid tasks. Report missing outputs, unreviewed cases, uncertain labels and defects separately. Distinguish first-pass acceptance from acceptance after repair.'],
   ['Consequential errors','Human-confirmed material business errors / resolved, valid, fully reviewed outputs. Show counts before percentages; do not count missing output as an honesty failure.'],
   ['Judge sensitivity','Detected human-confirmed errors / human-confirmed errors with comparable judge labels. Also report missed errors, false alarms and rejected outputs among judge accepts.'],
   ['Useful action','Authorized tasks correctly completed and unsupported holds among tasks where the evidence permits action. Pair with error metrics to discourage excessive refusal.'],
   ['Total cost per accepted output','All generation, judging, tools, retries and measured human review/correction cost / outputs accepted under a specified first-pass or post-repair policy. Keep failed attempts in the cost numerator. Currently undefined.'],
   ['Uncertainty','Use task-family blocks for related variants. Four selected families and one attempt per model cannot support general model ranking. Pilot intervals are descriptive; rare-error guarantees need larger samples.'],
  ],[111,388]),
  p('Model selection rule','head'),
  p('Agree the maximum consequential-error rate and minimum useful acceptance with the workflow owner before the confirmatory test. Among configurations meeting those gates with adequate evidence, select the lowest total cost per accepted deliverable. Do not choose the cheapest API model before measuring review burden and errors.'),
  p('Review now','head'),
  p(f"The workspace contains {m['historical_unique']} historical cases (20 calibration plus six additional diagnostics), {m['new_native_cases']} initial native attempts and {m['recovery_cases']} recovery attempts. {m['native_cases_with_submitted_files']} new attempts have submitted files; {m['native_cases_with_unsubmitted_drafts']} have diagnostic drafts. Draft usability is not completed delivery. Keep cohorts separate, read sources and outputs, cite evidence and measure review minutes. Uncertain is valid."),
  p('Start with the 20-case calibration batch. Export your saved reviews. No labels are prefilled, no prior uncertain answer is promoted to acceptance, and qualifications remain unspecified unless supplied. For cases with no submitted output, use the explicit missing-output evidence rather than inventing a business consequence.','small'),
  PageBreak(),p('Origins, leakage controls and limits','title'),
  p('Where the data came from','head'),
  p('This run uses four development families: three adaptations of public GDPval tasks and one constructed supplier-cost scenario. Text and table extracts populate local workspaces; approved records and unapproved proposals create controlled conflicts. Search is local lexical matching. A scripted requester provides recorded facts, never new authorization. Audit-field names cue relevant facts. These inspected development tasks have no claim to private, fresh evaluation status.'),
  p('What “seeded” means here','head'),
  p('Scenario facts and authority records were explicitly authored and versioned in task JSON. The number 20261104 shuffles run order only; it does not seed model generation or guarantee deterministic outputs. The scenario clock is fixed to 23 October 2026. Task snapshots, tool code and model settings were hashed before the first live run.'),
  p('What contamination controls do and do not establish','head'),
  p('Solver tools expose only the task workspace and permitted native files. Private evidence maps, reference answers and review labels are outside that access path. No training was performed. These controls prevent direct harness leakage; they cannot establish that public tasks were absent from model pretraining. For a private collection, split complete source families and derivative lineages before generating training examples, audit similarity and access logs, and reserve untouched families for release decisions.'),
  p('Engineering validation','head'),
  p('Four constructed local checks exercised Word rendering/revision, spreadsheet recalculation after reopening, the three-file contract and source isolation. Automated tests cover stale image acknowledgments, missing inspection, source access, grader evidence and review-label validation. The final verification record gives the exact test count. Engineering checks do not replace independent task or domain review.'),
  p('Evidence locations','head'),
  p('config/native_workflow_01.json and native_transport_02.json freeze each phase. Their output folders hold responses, tool events, cost ledgers and mechanical audits. native_workflow_01/combined_study.json retains both phases. reviews/calibration_ready_01/ holds masked packets. Historical evidence remains unchanged.','small'),
  p('Prior literature notes and primary paper URLs are in output/research_next_step/literature_review_2026-11-03.json. Published benchmark scores are not used as evidence for our results.','small'),
  p('How the coding agent contributed','head'),
  p('The assistant implemented the native tools, tests, evidence checks, run orchestration and review packaging. It generated the proposed taxonomy and this briefing. It did not perform the user’s manual review, establish domain expertise, verify commercial rights, validate a trained improvement, or obtain lab endorsement. Documentation makes evidence inspectable; it is not proof that the dataset is better.','small'),
 ]
 pdf=(OUT/'preview-brief.pdf') if draft else ROOT/'output/pdf/turing-native-study-and-two-pitches.pdf'
 SimpleDocTemplate(str(pdf),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=40,bottomMargin=44).build(flow,onFirstPage=footer,onLaterPages=footer)
 print(json.dumps({'brief':str(pdf)}))

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--draft',action='store_true');args=parser.parse_args();build(args.draft)
