"""Create the research findings report and one-page sales brief from saved evidence."""
import json,statistics
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'output/paired_v1';OUT=ROOT/'output/pdf'
S=json.loads((BASE/'summary.json').read_text());ROWS=json.loads((BASE/'scores.json').read_text())
NAVY=colors.HexColor('#18324A');GRAY=colors.HexColor('#526274');ACC=colors.HexColor('#176D77')
styles=getSampleStyleSheet()
for name,size,leading,color in [('TitleP',23,27,NAVY),('SubP',10.5,14,GRAY),('BodyP',9.8,13.6,NAVY),('HeadP',12,15,ACC),('CellP',8.8,12,NAVY),('SmallP',8.2,11,GRAY)]:
 styles.add(ParagraphStyle(name=name,fontName='Helvetica-Bold' if name in ['TitleP','HeadP'] else 'Helvetica',fontSize=size,leading=leading,textColor=color,spaceAfter=8))
def P(x,style='BodyP'):return Paragraph(x,styles[style])
def T(headers,rows,widths):
 t=Table([[P('<b>'+escape(str(x))+'</b>','CellP') for x in headers]]+[[P(escape(str(x)),'CellP') for x in r] for r in rows],colWidths=widths,repeatRows=1)
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#DCE9EF')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F4F7F9')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));return t
def foot(c,d):
 c.setFont('Helvetica',8);c.setFillColor(GRAY);c.drawString(48,29,'GDPval paired workflow pilot | Research findings | 31 October 2026');c.drawRightString(A4[0]-48,29,str(d.page))
def build(path,pages):
 flow=[]
 for i,(title,sub,items) in enumerate(pages):
  if i:flow.append(PageBreak())
  flow.extend([P(title,'TitleP'),P(sub,'SubP'),Spacer(1,5),*items])
 SimpleDocTemplate(str(path),pagesize=A4,rightMargin=48,leftMargin=48,topMargin=45,bottomMargin=48).build(flow,onFirstPage=foot,onLaterPages=foot)
def model(m):return 'GPT-6.1 Sol' if m.startswith('openai') else 'Claude Sonnet 5.5'
cost=S['total_api_reported_cost_usd'];reserved=S['total_api_charged_or_reserved_usd'];passed=sum(r['decision_pass'] for r in ROWS);wrong=sum(r['explicit_wrong'] for r in ROWS);incomplete=sum(r['status']!='completed' for r in ROWS)
clean=[r for r in ROWS if not r['known_task_defect']];cleanaccept=sum(r['provisional_acceptance'] is True for r in clean)
pagefails=S['artifact_summary']['page_constraint_failures'];agree=S['review']['agreement']['critical_error']
table=[[model(g['model']),g['variant'],f"{g['passes']}/{g['decision_denominator']}",f"{g['provisional_acceptances']}/{g['clean_denominator']}",f"${g['cost_usd']:.3f}"] for g in S['groups']]
pages=[]
pages.append(('Correct facts are only one gate','Executed evidence, with uncertainty and evaluation defects retained',[
 P(f'<b>{S["saved_runs"]} solver runs, five source families, three occupations, two models, two trials.</b> The study used ${cost:.3f} in reported API charges, below the $25 cap. There are no unresolved cost reservations. Review costs include invalidated review attempts.'),
 T(['System','Condition','Decision checks','Provisional usable*','Solver cost'],table,[112,70,91,124,102]),
 P(f'<b>What happened:</b> {passed}/{len(ROWS)} runs passed all structured critical-decision checks. There were {wrong} explicit wrong decision records and {incomplete} incomplete/invalid final submissions. Correct audit fields therefore must not be read as full task success.'),
 P(f'*Provisional usable means decision checks, model-judged substantive content, native output files and stated page constraints all passed. The denominator excludes four EV conflict runs affected by an intervention-design defect. It is <b>not independent expert acceptance</b>. There were {pagefails} page-constraint failures under the fixed renderer.' ,'SmallP'),
 P('The supported conclusion','HeadP'),
 P('This implementation can trace information recovery, artifact production and evaluation defects separately. It has not established that missing-information or conflict interventions reliably expose additional consequential errors. A small, simple, explicitly signposted workflow can saturate.'),
 P('Use this as a research prototype and a customer discovery demonstration. Do not claim superiority over GDPval, production reliability, contamination-free evaluation, or post-training uplift.'),
]))
pages.append(('The paired experiment','Same professional objective; controlled changes in access and authority',[
 T(['Task family','Operative fact','Why a wrong answer matters'],[
 ['EV assembly proposal','110,000 packs/year for five years','An incorrect forecast inflates the investment case. Conflict condition quarantined for coupled pricing ambiguity.'],
 ['Supplier exit strategy','21-day cutoff; 800 sets/month','Continuity plans can fail before replacement qualification.'],
 ['Sourcing governance','Finance + Program + Purchase approve price changes','An attractive fast track can bypass required financial authority.'],
 ['Change control SOP','Formal review for overage strictly > $5,000','A $6,000 change can bypass review under an obsolete $50,000 rule.'],
 ['Shipment manifest','Freight costs $150, with $225 benchmark','Using the $110 draft overstates customer savings by $40.'],
 ],[113,165,221]),
 P('Baseline keeps the source facts in the request/reference extracts. Recovery moves one operative fact behind an accessible workspace tool. Conflict supplies a stale value and working notes; an approval registry identifies the operative record. A newer draft remains unapproved. The registry and record tools are identical across conditions.'),
 P('Each run starts with fresh conversation state. Tools can only list or read three exact in-memory records. They cannot read the filesystem, gold deliverables, rubrics, another trial or the web. The professional output is produced through a common structured document/workbook renderer.'),
 P('Selection and settings','HeadP'),
 P('Five purposively selected public families: three purchasing, one project-management and one shipping. Fifteen instances x two systems x two repeats = 60 runs. The public release contains only five tasks per occupation: 30 source tasks require at least six occupations; three occupations yield at most 15.'),
 P('Both solvers: medium reasoning, at most five responses, 6,500 completion tokens per response, 55,000 input bytes per request. Standard token-price caps are $2/M input and $10/M output. Provider routing is restricted to the named vendor and responses retain actual model/provider identifiers. Equal named effort does not establish equal compute.'),
 P('Why these models','HeadP'),
 P('GPT-6.1 Sol and Claude Sonnet 5.5 provided two available tool-capable systems within the declared price ceiling. This is a cross-system mechanism check, not a search for a leaderboard winner. Choose a deployment model only after expert-calibrated acceptance, critical-error limits, latency and total review cost are measured on the customer workflow. The current model-judge results cannot settle that choice.'),
]))
pages.append(('Metrics that support a decision','Use separate gates; do not collapse evidence into a single quality score',[
 T(['Measure','Definition and use'],[
 ['Critical decision pass','All frozen numeric/approval fields correct. A cheap mechanism diagnostic; it does not inspect every artifact claim.'],
 ['Explicit critical error','Wrong material decision or unsafe commitment supported by an exact artifact quote/cell. Separate observed numerical failures from provisional model-judge flags.'],
 ['Recovery / authority resolution','Correct result plus trace showing operative-record access; registry access adds evidence of authority checking. Reading alone is not successful use.'],
 ['Deliverable acceptance','All required files, verified calculations, mandatory business requirements and usability constraints. Current proxy uses model review and deterministic file/page gates; expert acceptance is unmeasured.'],
 ['Cost per accepted deliverable','All solver attempt costs divided by usable outputs; keep review cost separate. Never substitute cost per generated row or token for outcome economics.'],
 ['Review time and grader error','Human minutes, false acceptances/false rejections and severity agreement against adjudicated experts. Currently unmeasured, not zero.'],
 ['Evaluation-defect burden','Broken source inputs, intervention ambiguity, tool failures and reviewer mistakes, with affected-run counts and dispositions.'],
 ],[135,364]),
 P('Uncertainty and causal attribution','HeadP'),
 P('Average variant-minus-baseline differences within each source family, then across families. Resample families, keeping variants and repeats together. Raw comparisons use five families; the clean conflict comparison uses four after the EV defect exclusion. Both are saved. A zero-width bootstrap interval when every observed family behaves identically is not evidence of equivalence.'),
 P('Repeated runs improve stability checks but do not turn five business problems into 60 independent problems. Output-limit failures may reflect the harness budget rather than inability to resolve evidence. No training experiment was conducted, so the study cannot establish data value through model improvement.'),
 P('Observed clean decision-pass differences: recovery minus baseline was 0 percentage points for each system. Conflict minus baseline was +12.5 points for each system across four families, driven by one extra parseable output per system. These results do not demonstrate that the interventions increase critical-fact errors. The exact pairs and descriptive intervals are in summary.json.','SmallP'),
]))
pages.append(('Audit the evaluator as well as the model','Observed defects and defensible dispositions',[
 T(['Finding','Disposition'],[
 ['Inventory location source mismatch','Receiving IDs do not join to the location register. The specially mentioned item has no received quantity. Excluded before model evaluation.'],
 ['Workload registry mismatch','Ellen Zhu appears in timesheets but not the 23-person registry. Period/capacity conventions also need clarification. Excluded before evaluation.'],
 ['EV conflict mutation changes cost context','The changed volume becomes attached to the unit-cost quotation. Four runs retained but excluded from the clean conflict estimate. No solver answers regenerated.'],
 ['Reviewer v1 lacks operating records','Valid citations were called unsupported. All judgments invalidated; raw outputs and charges retained.'],
 ['Reviewer v2 lacks actual variant brief','Canonical-only context can make a supported price-basis caveat look invented. All v2 judgments invalidated. v3 includes canonical and actual context.'],
 ['Long SOP outputs / document lengths','Retained as system outcomes under the declared output budget and renderer. Do not relabel these as evidence that authority resolution failed.'],
 ],[191,308]),
 P('Review evidence','HeadP'),
 P(f'Valid v3 primary reviews: {S["review"]["valid_primary"]}. Valid second reviews: {S["review"]["valid_secondary"]}. Critical-error agreement: {agree["agree"]}/{agree["double_graded"]}. These are model judges, including vendors that also solved the tasks; agreement is not expert correctness.'),
 P('Investigate every critical flag and disagreement against the actual source and rendered output. A plausible negotiation strategy can still contain an infeasible bridge or unsupported walk-away threshold. A correct savings calculation can coexist with an unsupported compliance assurance. Keep those hypotheses distinct from the paired critical-fact metric.'),
 P('Release gate for an external claim: independent domain review must confirm source solvability, intervention equivalence, consequence severity and grader correctness. The current investigator review is assistant-led, not independent expert validation.'),
]))
pages.append(('Where the data came from','A precise answer to provenance, seeding and contamination questions',[
 P('<b>Source:</b> public GDPval tasks at revision 11e7900cdcac61bc4daf59e65feb238acda98fbf. Twenty referenced input files were fetched and hashed. Source gold deliverables were never downloaded into the solver workspace. Native file content was supplied as text/table extracts, which changes the modality relative to official GDPval.'),
 P('<b>Generation:</b> the assistant wrote a deterministic Python transformation for each family. Approved business values came from the source. Stale values, synthetic revision metadata and approval records were specified explicitly in code. No teacher API generated the task facts, and no expert-authorship claim is made.'),
 P('<b>Seeding:</b> 20261030 randomizes run order only. It does not create semantic variety or new independent cases. The five business families are the units of coverage. Model sampling was repeated twice without claiming exact seed-based replay.'),
 P('<b>Isolation:</b> all five source families and all descendants are evaluation-only. There was no SFT or RL and no benchmark-derived training set. Solver-visible payloads exclude rubrics, truth labels, gold paths and other outputs. The task author did inspect public task and grader context; author independence is therefore not claimed.'),
 P('<b>Remaining contamination uncertainty:</b> public GDPval content may already be in provider training data. No access to provider pretraining corpora exists here. Family isolation and local hashes cannot certify absence of pretraining contamination. These results are public diagnostics, not sealed-holdout evidence.'),
 P('How a later training pipeline would differ','HeadP'),
 P('Collect new rights-cleared workplace episodes in source families disjoint from every evaluation family. Preserve document lineage, template lineage, policy version, license and reviewer identity. Generate state and numerical truth procedurally; use a capable teacher only for language and candidate trajectories. Verify calculations and authority choices independently, and audit a sample with domain experts.'),
 P('Test prompt/tool repairs before training. Then compare equal-budget base, SFT and an appropriate RL alternative on the same held-out families. Reward correct authorized outcomes, evidence use and valid deliverables; do not reward merely opening the right file. Probe per-task reward variation before GRPO. Two repeats in this pilot are not a sufficient RL-readiness study.'),
 P('No explicit dataset license or license metadata was found. Commercial adaptation and redistribution rights remain unverified. Keep copied source assets local until permissions are resolved. Training rights, evaluation rights and public redistribution rights must be checked separately.','SmallP'),
]))
pages.append(('What to build next','A research plan with decision gates, not promised uplift',[
 T(['Stage','Work and stop rule'],[
 ['1. Validate the mechanism','Repair volume/price coupling; test invariant objective and reachable truth; independently review each original/recovery/conflict triplet. Quarantine unresolved tasks.'],
 ['2. Increase meaningful difficulty','Add realistic file search, superseded approvals, partial tool failures and targeted clarification while keeping the same deliverable. Freeze a new version before new results; retain v1.'],
 ['3. Expand families','Use 15 source tasks across three occupations only if every task is valid, or 30 across at least six occupations. Prefer original rights-cleared episodes for the final customer test. Size a confirmatory study from observed discordant-pair rates and a business-relevant minimum effect.'],
 ['4. Establish expert calibration','Two blinded domain reviewers grade a prespecified sample and every critical disagreement. Measure false acceptance and review minutes. Adjudicate without revealing model identity.'],
 ['5. Test the cheapest repair','Compare the frozen baseline with an evidence-checking prompt/tool repair under matched budgets. Only create training data for persistent, verified failures.'],
 ['6. Measure training transfer','Keep source families disjoint. Compare base, repair-only, SFT and RL as resources permit. Require improved acceptance and critical-error rate on fresh expert-reviewed tasks, with uncertainty and no unacceptable regression.'],
 ],[129,370]),
 P('Upgrade over the earlier POsttrain work','HeadP'),
 P('The earlier saved project expanded assistant-authored templates and showed why row count is not coverage and reward saturation is a problem. This prototype adds paired interventions, source lineage, constrained access, outcome cost, actual artifacts, repeated runs and an explicit evaluator-defect ledger. Those are engineering improvements over that protocol, not evidence of superiority over AfterQuery as a company.'),
 P('Success gate: a customer can name the exact workflow failure, inspect the source and artifact evidence, reproduce its occurrence, and measure whether a specific repair reduces it on fresh tasks. Until then, sell a diagnostic pilot rather than a performance guarantee.'),
]))
pages.append(('How to sell it to researchers','Lead with the decision they cannot confidently make today',[
 P('The 45-second pitch','HeadP'),
 P('We are building a paired extension of professional-work evaluation. We keep the business objective fixed, then change whether critical information is directly available, recoverable or contradicted by an unapproved draft. The product is a reproducible failure diagnosis: the source evidence, agent trace, consequential error, evaluator confidence and cost of producing usable work. Our first pilot shows why that distinction matters: correct audit facts can coexist with unusable documents, and incomplete grader context can manufacture failures. We are now validating harder, rights-cleared cases with domain experts before claiming a dataset advantage.'),
 P('For an OpenAI researcher','HeadP'),
 P('Offer a complementary workflow slice around GDPval, not a replacement leaderboard. Show the same source task in three versions and a trace that separates retrieval, authority choice, calculation and artifact delivery. Ask whether the paired failure is stable across configurations and whether a repair transfers to untouched families.'),
 P('For an Anthropic researcher','HeadP'),
 P('Show a workflow where the system must distinguish an approved record from a newer draft and withhold an unsupported commitment. Emphasize explicit tool state, full evidence for graders, task validity, and expert calibration of consequential errors. Offer auditable trajectories and a reproducible counterexample, not a generic safety score.'),
 P('Customer value and proof','HeadP'),
 T(['Buyer question','Evidence to sell'],[
 ['Will this reduce expensive mistakes?','Expert-validated critical-error reduction on the customer\'s actual workflow, with uncertainty and a clear denominator.'],
 ['Is this cheaper than human review?','Review minutes avoided at a fixed false-acceptance ceiling; report total system + review cost per accepted task.'],
 ['Why buy your data?','Failure-specific coverage, rights, verified state/labels and measured transfer beyond a prompt/tool fix. Row volume alone is not the value.'],
 ['Why trust the evaluation?','Inspect the rejected tasks, grader defects, raw first attempts and disputed judgments as well as the successful cases.'],
 ],[160,339]),
 P('Do not quote a revenue lift, dollar loss avoided, training uplift or superiority result from this pilot. Those require customer baselines, frequency/severity data and a validated intervention.'),
]))
pages.append(('Evidence and research references','The evidence card documents this study; it does not validate the study',[
 P('The downloadable evidence card links the frozen protocol, source selection, per-run metrics, raw responses, artifacts, review versions, defect adjudications and separate cost ledgers. The short view states what is measured, the main caveat and intended use. The detailed view exposes the configuration and evidence behind every claim.'),
 P('Research decisions','HeadP'),
 P('<b>GDPval:</b> the paper identifies limits of precisely specified, one-shot work and also studies reduced context. This prototype adds a recovery mechanism and authority state, so the intended contribution is beyond shortening a prompt. Our extraction and renderer mean scores are not directly comparable with official GDPval. [1]'),
 P('<b>Evaluation Cards:</b> documentation quality does not establish rigorous evaluation. We apply that distinction by exposing invalid graders, unresolved rights, small family counts, public exposure and missing expert validation. A well-filled card is not evidence the dataset is better. [2]'),
 P('<b>Agent evaluation practice:</b> inspect trajectories and actual artifacts, combine objective checks with calibrated judgment, and treat the harness as part of the system. A final claim of success is insufficient. [3]'),
 P('<b>Post-training implication:</b> active synthetic-data selection work motivates choosing informative cases rather than maximizing rows. Its results are task-dependent; this pilot measures no training gain. [4]'),
 P('Sources','HeadP'),
 *[P(f'<b>[{i}] {label}</b><br/><link href="{url}" color="#176D77">{escape(url)}</link>','SmallP') for i,label,url in [
 (1,'GDPval paper and public dataset','https://arxiv.org/html/2510.04374v1'),
 (2,'Evaluation Cards v2, including documentation limits','https://arxiv.org/html/2606.09809v2'),
 (3,'Anthropic, Demystifying evals for AI agents','https://www.anthropic.com/research/demystifying-evals-for-ai-agents'),
 (4,'Active synthetic data generation, v2','https://arxiv.org/html/2512.00884v2'),
 (5,'Pinned GDPval source','https://huggingface.co/datasets/openai/gdpval/tree/11e7900cdcac61bc4daf59e65feb238acda98fbf'),
 (6,'OpenRouter live model catalog, snapshotted locally','https://openrouter.ai/api/v1/models'),
 (7,'OpenRouter usage accounting','https://openrouter.ai/docs/cookbook/administration/usage-accounting')]],
 P('Model selection used current catalog availability and supported tools; prices were also constrained per request. Study files preserve fetched catalog, API-reported usage and actual provider/model fields. No human reviewer labor cost is included.','SmallP'),
]))
OUT.mkdir(parents=True,exist_ok=True);build(OUT/'paired-pilot-research-and-sales.pdf',pages)
one=[('A paired test of workplace reliability','Research pilot and commercial proposition',[
 P('<b>Question:</b> can an agent recover an omitted fact and reject an unapproved draft before producing a professional deliverable? The baseline, recovery and conflict versions retain the same business objective.'),
 P(f'<b>Executed:</b> {S["saved_runs"]} runs, five public GDPval families, three occupations, two systems, two trials. Reported API spend ${cost:.3f}, within $25. No unresolved cost reservations.'),
 T(['Observed result','What it supports'],[
 [f'{passed}/{len(ROWS)} structured decision passes','Recovery/authority checks often succeed; this does not establish full deliverable success.'],
 [f'{incomplete} incomplete outputs; {pagefails} page-limit failures','Output budgets and artifact constraints need separate measurement.'],
 ['Two source families quarantined; four EV conflict runs flagged','Defect accounting prevents invalid tasks and ambiguous interventions from becoming model-failure claims.'],
 [f'{cleanaccept}/{len(clean)} provisional usable outputs','Model-reviewed content + file/page gates; independent expert acceptance remains unmeasured.'],
 ],[202,297]),
 P('What we sell','HeadP'),
 P('A customer-specific diagnosis linking consequential errors to source evidence, tool behavior and measurable outcome cost. Follow with a verified prompt/tool or training-data intervention, evaluated on fresh task families.'),
 P('Next paid pilot','HeadP'),
 P('Validate the triplets with domain experts; expand to new rights-cleared families; compare a repair against the frozen baseline; report accepted deliverables, critical errors, review time and cost. No training uplift, commercial dataset rights or better-than-GDPval claim is established today.'),
 P('Evidence: frozen protocol, first-attempt traces, native artifacts, source and grader defect ledger, model-review disagreements, costs and a two-view Evaluation Card. The card makes these claims inspectable; it does not certify evaluation quality.','SmallP')])]
build(OUT/'paired-pilot-one-page.pdf',one)
print(json.dumps({'reports':['paired-pilot-research-and-sales.pdf','paired-pilot-one-page.pdf']}))
