"""Researcher-facing report, distinct pitches and current local evidence page."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/pdf';AUDIT=ROOT/'output/submission_audit'
def read(p):return json.loads(p.read_text())
S=read(AUDIT/'summary.json');T=read(AUDIT/'taxonomy.json')['categories']
O=read(ROOT/'output/panel_review/openai_review.json');A=read(ROOT/'output/panel_review/anthropic_review.json')
NAVY=colors.HexColor('#18324a');TEAL=colors.HexColor('#176d77');GRAY=colors.HexColor('#526274')
styles={name:ParagraphStyle(name,fontName='Helvetica-Bold' if name in ['title','head'] else 'Helvetica',fontSize=size,leading=lead,textColor=color,spaceAfter=7) for name,size,lead,color in [('title',22,26,NAVY),('head',12,15,TEAL),('body',9.5,13,NAVY),('small',8,10.6,GRAY),('cell',8.6,11.5,NAVY),('sub',10,14,GRAY)]}
def p(t,s='body'):return Paragraph(t,styles[s])
def table(headers,rows,widths):
    t=Table([[p('<b>'+escape(str(x))+'</b>','cell') for x in headers]]+[[p(escape(str(x)),'cell') for x in row] for row in rows],colWidths=widths,repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce9ef')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f7f9')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));return t
def footer(c,d):
    c.setFont('Helvetica',8);c.setFillColor(GRAY);c.drawString(48,27,'Turing FDE take-home | 31 October 2026 | Evidence, not a training-uplift claim');c.drawRightString(A4[0]-48,27,str(d.page))
def build(name,pages):
    flow=[]
    for i,(title,subtitle,items) in enumerate(pages):
        if i:flow.append(PageBreak())
        flow.extend([p(title,'title'),p(subtitle,'sub'),Spacer(1,4),*items])
    SimpleDocTemplate(str(OUT/name),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=42,bottomMargin=46).build(flow,onFirstPage=footer,onLaterPages=footer)

one=[('Correct facts can still hide a broken plan','Anthropic discussion | Authority, uncertainty and useful completion',[
 p('<b>The data ask:</b> a private, permissioned 30-family purchasing diagnostic: task files, authority and dependency state, native reference deliverables, source-linked rubrics, expert preferences and rationales. Use 10 development families and 20 untouched evaluation families. Test tools and prompts before proposing training.'),
 table(['Supplied constraint','Generated operational instruction','Evidence status'],[
 ['Stock unknown; supplier exit in 21 days; replacement takes months.','The action table says buffer stock and air freight cover the gap without an agreement.','Project owner: material correction required.'],
 ['Price changes require Finance, Program and Purchase.','A provisional-release clause names only Program and Purchase; nearby text requires all three.','Project owner: material correction required.'],
 ],[160,208,131]),
 p('Both examples are Claude outputs with correct audit facts. For Anthropic, the question is whether the final artifact preserves authority and uncertainty while completing authorized work. These issue labels do not establish a model ranking or error rate; reviewer qualifications and full-output acceptance remain undeclared.'),
 p('What we ran and learned','head'),
 p('<b>60 attempts / 5 public task families / 3 occupations / 2 models.</b> All 53 parseable outputs passed targeted fact checks. Seven attempts produced no valid final output; five hit the output cap. Eighteen of 35 bounded documents exceeded their page limit. These delivery outcomes are affected by the JSON contract and fixed renderer. All 12 exported workbooks passed value checks.'),
 p('<b>Human-review gap:</b> 35 flagged attempts are organized into seven provisional, nonoverlapping review categories; none has a completed full-output human review. A separate 20-output calibration queue includes judge passes and failures. The 10/12 model-judge critical-label agreements were all shared negatives, with zero shared positives. This is not calibrated error detection.'),
 p('Repair evidence and limits','head'),
 p('The separate 16-run checklist probe had 15 valid fact-check passes and five document/page passes, with no aggregate artifact improvement. <b>All 16 inputs contained a chronology defect.</b> Corrected candidates are unrun. Four earlier EV-conflict attempts also have a task defect. A new audit disputes missing-tracker grades where the runner requested only two Word files.'),
 p(f'<b>Cost:</b> ${S["campaign_api_cost_usd"]:.2f} total API spend, including discarded judge attempts; human labor unmeasured. No new API calls in this audit. No SFT/RL was run. Public pretraining exposure is unknown; current task families are excluded from future training.'),
 p('<b>Decision:</b> buy a validated diagnostic first. Select the lowest total cost per human-accepted deliverable only after agreed consequential-error thresholds are met. Expand to training only for verified residual failures that transfer to fresh, separately held-out lineages.','small'),
])]
build('turing-submission-one-page.pdf',one)

pages=[('Panel audit: strong evidence, unfinished validation','Independent AI perspectives; neither is a human or lab endorsement',[
 p('Two AI reviewers separately read the current report and raw transcripts without seeing each other\'s notes. Both found the audit trail credible and the two purchasing contradictions concrete. Neither found evidence sufficient for a calibrated error rate, model winner or training-data sale. Their scores refer to the pre-revision submission and have not been silently raised after edits.'),
 table(['Dimension','OpenAI perspective','Anthropic perspective'],[
 ['Own-run traceability','4/4 - strong','4/4 - strong'],['Failure taxonomy / hand review','2/4 - partial','2/4 - partial'],['Judge-human validation','1/4 - weak','1/4 - weak'],['Task validity','2/4 - partial','1/4 - weak'],['Audience-specific commercial case','2/4 - partial','2/4 - partial'],
 ],[245,127,127]),
 p('The 0-4 scale is missing / weak / partial / solid / strong. Scores are qualitative AI assessments with overlapping dimensions, so they are not summed. Complete notes and source paths are in output/panel_review/.'),
 p('What changed in this revision','head'),
 p('The main page now starts with the actual artifact contradictions and a specific private-data offer. The stale website is replaced with current evidence. A case-level candidate taxonomy, masked 20-output calibration queue, 35-attempt failure queue, distinct lab pitches, dataset specification and grading utility are ready. Human judgments have not been fabricated.'),
 p('What the scorecard adds beyond the brief','head'),
 p('The brief asks for careful by-hand classification and gives thirty versus three hundred as a quality comparison. It does not prescribe exactly 30 failures, 20 calibration labels or 5-7 categories. Those are useful design targets, not reasons to pad evidence. The brief also permits either a simple website or a one-page document.'),
 p('Public availability does not prove a specific model was trained on these tasks or make all training use categorically impossible. Our operational policy is stricter: do not train on these evaluation families; provider exposure and commercial permissions remain unverified. Sell newly permissioned private lineages, not public GDPval copies.'),
 p('Sources: local Turing brief, pages 1-2; <link href="https://huggingface.co/datasets/openai/gdpval" color="#176d77">official GDPval release</link>; <link href="https://arxiv.org/html/2510.04374v1" color="#176d77">GDPval paper</link>. Paper statistics are background only and are not used as our results.','small'),
])]
pages.append(('Failure taxonomy: a review queue, not a verdict','35 flagged attempts; exactly one primary category per attempt',[
 table(['Primary category','Count','Severity / first intervention'],[[c['name'],str(c['candidate_count']),c['severity']+'; '+c['data_fix']] for c in T],[202,42,255]),
 p('Assignment rule','head'),p('First separate contract defects, then invalid final serialization, approval violations, unsupported resource/dependency plans, unsupported eligibility, missing cost comparisons, and finally page overflow. Secondary symptoms remain in the raw record. Five token-limit failures and one further parse failure fall inside the 12 contract-confounded change-control attempts; they are not counted twice.'),
 p('The 35 are historical provisional nonacceptances after excluding four EV-conflict attempts. They are not 35 independently confirmed model errors. Current case assignments use engineering checks and existing judge evidence; your hand review can change or reject them. The 16 defective repair-probe attempts are outside this taxonomy.'),
 p('Three raw traces behind the largest category','head'),
 p('change_control baseline Claude r1: two native Word files, tracker omitted. change_control conflict GPT r1: two native Word files, tracker omitted. change_control baseline GPT r1: output stops at the token limit. All share the two-Word-file instruction versus the reference\'s tracker request. Their complete observable transcripts, sources and files are in the review app; this category concerns attribution, not a proven training gap.'),
 p('Two material-issue labels from the project owner remain separate. No count here is labeled human-confirmed. If a qualified second reviewer codes the same cases, report category agreement, the full confusion matrix and adjudicated disagreements; do not claim taxonomy reproducibility from this AI proposal.'),
]))
pages.append(('Grader validity and setup controls','Agreement on negatives does not validate error detection',[
 table(['Primary judge / secondary judge','No critical error','Critical error'],[['No critical error','10','1'],['Critical error','1','0']],[255,122,122]),
 p('This is the 12 double-graded v1 outputs: primary GPT-6.1 Sol and secondary Claude Sonnet 5.5. Critical agreement is 10/12 and content agreement 8/12. No output is critical-positive for both judges. Primary GPT flags 10/28 Claude outputs and 0/25 GPT outputs. Real differences and self-preference are both compatible with this pattern; human calibration must distinguish them.'),
 p('The 20-output calibration','head'),
 p('Selected before new human labels, balanced at ten outputs per solver, across all five families, with contrasting judge labels where available. It excludes the two already-discussed user issues and known EV conflicts. Only one valid GPT change-control output exists, so its spare allocation goes to shipping. This is purposive calibration, not a prevalence sample.'),
 p('Review complete source and deliverable with model identity and prior judge labels hidden. Score content acceptability, consequential error and task defect, with exact evidence and actual minutes. Use the same content-only scope as the judge; keep page compliance separate. The scoring utility reports false accepts, false rejects, unknowns, task-defect exclusions and family-level descriptive uncertainty. No agreement is calculated from unreviewed templates.'),
 p('Controls before a training claim','head'),
 table(['Observed issue','Required control'],[
 ['Five responses hit 6,500 tokens','Matched output-budget / staged-deliverable control; retain unsuccessful attempts and cost.'],
 ['JSON failure and 18/35 page failures','Schema validation and actual native file creation, rendering, inspection and revision. Current solver lacked that loop.'],
 ['Disputed missing tracker','Resolve the source/output contract with a reviewer; align prompt, allowed file types, count and grader.'],
 ['Unverified resource/approval claim','Validated inventory/authority state tools plus generic checklist; assess final actions, not just audit fields.'],
 ],[197,302]),
 p('The historical 21/56 provisional acceptance count is model-judged and further affected by the tracker dispute. It is retained for audit, not used for model selection. No .pptx task ran; no slide-generation performance is implied.','small'),
]))
pages.append(('What the private dataset would contain','Proposed product specification; no collection or sale has occurred',[
 table(['Stage','Family-level split and coverage'],[
 ['Diagnostic pilot','30 fresh purchasing scenario families: 10 development, 20 untouched evaluation; three workflow versions each = 90 instances. No training.'],
 ['Conditional expansion','240 further families across purchasing, project management and shipping: 120 train, 60 development, 60 sealed test. Each occupation contributes 40/20/20. Three versions yield 720 instances, not 720 independent tasks.'],
 ],[126,373]),
 p('Each family includes','head'),
 p('A stable professional objective and deliverable contract; permissioned reference files and authority history; explicit missing facts and realistic search/clarification paths; dependency and approval state; native expert reference deliverables; programmatic arithmetic/file checks; source-linked material-error criteria; at least two expert preference pairs with rationales, including acceptable alternative solutions; provenance, revision, reviewer and license records.'),
 p('Prevent leakage and cheap rewards','head'),
 p('Assign source organizations, scenario ancestry and templates to a split before generation. Deduplicate text, structure and business logic, then review near matches. Keep test references and rubrics outside training tooling. Do not train on the inspected public cases or their descendants. Reward accepted, source-consistent deliverables and authorized progress; do not reward opening a file, copying fact fields, checklist words, verbosity or automatic refusal. Audit adversarial outputs that state the right facts but contradict them in the artifact.'),
 p('Expert pairwise preferences must compare outputs under the same task and budget, mask model identity, rotate presentation order and preserve ties. Require an evidence rationale for consequential labels. Counterexamples should include harmless conditional proposals and legitimate authorized actions so excessive abstention cannot win.'),
 p('Production economics - illustrative assumptions','head'),
 p('Assume 3.5 expert hours per authored/reviewed family at $100/hour, $2 API cost and a 90% acceptance yield: ($350 + $2) / 0.9 = <b>$391.11 per accepted family</b>; 30 accepted families imply about $11,733. This is a planning calculation, not a quote, measured cost or spend authorization. Replace every input with pilot time logs and vendor terms. The $25 limit applies to our current API experiment; it does not fund expert data production.'),
 p('Refresh proposal: audit permissions and drift each month; introduce new scenario/template lineages quarterly and after a material workflow change. Version the holdout and reserve a sealed portion. The refresh cadence and sizes are proposals to agree with the buyer. Even zero errors in 20 independent test families would leave a roughly 14% one-sided 95% upper bound before model-selection adjustment; the pilot cannot certify rare-error reliability.','small'),
]))
pages.append(('OpenAI conversation: diagnose residual training signal','Research question: what remains after adequate tools and compute?',[
 p('Opening - about 45 seconds','head'),
 p('"This public GDPval slice exposed a supervision gap: correct audit facts can coexist with a contradictory operational plan. The two owner-reviewed examples are Claude outputs, so I am not claiming a verified deficit in your model. I propose testing the same hypothesis on your own stack using fresh private tasks, native file tools and calibrated human review."'),
 p('What to show','head'),
 p('Show the approved 21-day cutoff, the correct audit field and the unsupported continuity statement in the final document. Then show the five token-limit failures as a counterexample to overclaiming: extra training is not yet their demonstrated remedy. Distinguish the facts-only metric from acceptance of the actual professional artifact.'),
 p('The product and RL question','head'),
 p('"For 30 fresh purchasing families, we deliver complete episodes, native expert outputs, scalable state/file checks, preference pairs and source-grounded rationales. Ten development families support scaffolding; twenty remain untouched. First compare a capable file-tool loop and a dependency/approval tool at matched budgets. Only residual expert-confirmed failures justify a separate training set."'),
 p('"An RL episode needs an initial workplace state, allowed actions, source retrieval and clarification transitions, approval prerequisites and a terminal deliverable. Success is verified authorized work, not a correct facts object. A plausible but unsupported commitment is a negative; an unnecessary hold is also a failure when the evidence supports action. SFT uses verified successful trajectories; RL follows only if the environment and reward can withstand adversarial checks."'),
 p('Hard questions and honest answers','head'),
 table(['Question','Answer supported today'],[
 ['Which OpenAI failure survives tool/compute repair?','None has been human-calibrated as a residual semantic deficit here. That is the next experiment, not an established sales claim.'],
 ['Why buy data rather than an inventory or approval validator?','Buy the diagnostic first. If the validator removes the target errors on fresh tasks, stop the training-data expansion.'],
 ['What is your grader\'s false-accept rate?','Unknown. There are no complete human output labels yet. The prepared 20-output queue includes judge passes and failures.'],
 ['How do you know training transfers?','We do not. Require separate source/template lineages and an untouched test with failure and acceptance endpoints.'],
 ],[224,275]),
 p('Close: "Nominate one workflow owner and two qualified reviewers. Agree the acceptance definition and error threshold before we collect. The first decision is whether there is a data problem worth training on."'),
]))
pages.append(('Anthropic conversation: preserve authority in action','Research question: can the agent be useful without inventing permission?',[
 p('Opening - about 45 seconds','head'),
 p('"In one sourcing draft, the model retrieved the approved three-way price rule, but a provisional-release clause named only two approvers. The next paragraph restored all three. The project owner marked this issue as requiring material correction. I would test whether your agent preserves authority through exceptions and keeps unconfirmed resources conditional, while still completing authorized work."'),
 p('What to show','head'),
 p('Show the full conflicting clause beside its caveat and governing source. Then show the judge disagreement: a valid critique must distinguish a draft proposal awaiting approval from an actionable bypass. Do not call this intentional deception. A third similar transcript is an unconfirmed candidate, not a third human-confirmed failure.'),
 p('Distinct product emphasis','head'),
 p('Build matched episodes with an approved route, a newer unapproved proposal, a targeted clarification and a justified hold. Include cases where sufficient authority is already present, so asking forever or refusing does not earn a high score. Labels capture source fidelity, unsupported commitments, unnecessary holds, accepted work and review burden.'),
 p('Defend the grader and the reward','head'),
 p('"The current 10/12 critical-label agreement is all shared negatives. I would not present it as validation. We need qualified human coding of positive and negative examples, disagreement adjudication and a balanced vendor comparison. A hidden rubric must inspect the recommended action and cross-section consistency; surface checklist compliance cannot earn the reward. We also test paraphrased rules and harmless proposals to detect over-sensitive grading."'),
 table(['Question','Answer supported today'],[
 ['Show three transcripts behind your strongest business category.','Supplier recovery Claude r2 is owner-reviewed. Baseline r2 and conflict r1 show tooling/bridge tensions; those remain candidates requiring full context and human review.'],
 ['Is the ten-versus-zero critical pattern self-preference?','It is compatible with bias or real quality differences. We lack the human labels to separate them.'],
 ['Will another reviewer reproduce your taxonomy?','Unknown. The seven categories are triage; double-code a fixed sample and report a confusion matrix and adjudications.'],
 ['What stops reward hacking or excessive refusal?','Hidden state and artifact checks, expert rationales and positive controls for authorized action. This design is proposed; no RL result is claimed.'],
 ],[224,275]),
 p('Close: "Start with one permissioned workflow and a small calibrated review set. Compare prompt and state-tool repairs. Expand training only if consequential errors persist and useful authorized completion improves on new lineages."'),
]))
pages.append(('The Anthropic call and the remaining work','Primary audience: Anthropic | The OpenAI pitch remains a separate alternative',[
 table(['Time','Action'],[['0-2 minutes','Show the approval contradiction, including its caveat. State the private-data ask, five-family scope and $5.17 API cost.'],['2-5 minutes','Inspect the complete source and deliverable. Separate unsupported commitments, authorized proposals and justified holds.'],['5-8 minutes','Show the judge confusion matrix, human-review gap and task defects. Explain calibration and controls for excessive refusal.'],['8-11 minutes','Offer the 30-family diagnostic and acceptance, consequential-error, useful-completion and total-cost endpoints.'],['11-13 minutes','Explain source-family separation and prompt/tool repairs before any SFT or RL. Show stop-sale criteria.'],['13-15 minutes','Answer objections; ask for one workflow owner, qualified reviewers and agreed decision thresholds.']],[111,388]),
 p('Finish the human portion','head'),
 p('Open site/review/index.html. Complete the calibration queue first, then the failure taxonomy queue. The two queues contain 43 distinct attempts, so saved labels are shared where a case overlaps. Add your domain experience, actual minutes, evidence and uncertainty. Export the JSON. A second qualified reviewer should code a prespecified overlapping sample before claiming taxonomy reliability.'),
 p('Run scripts/score_human_submission_reviews.py on the export. It rejects missing evidence for a positive consequential label and excludes unknown/task-defective cases from comparable judge agreement. It never converts the two old issue labels into acceptance or fills in unreviewed items. Existing human summaries are protected against accidental overwrite.'),
 p('Then resolve the change-control deliverable contract and independently validate corrected task variants before another paid run. Review the unrun native-tool control design at equal budgets. Use fresh, permissioned lineages for a clean transfer result. Current artifacts are a private working submission, not a rights-cleared dataset release.'),
 p('Evidence guide','head'),
 p('output/submission_audit/: triage, sampling, grader confusion and setup audit. output/panel_review/: both independent AI assessments and eight hard questions each. output/paired_v1/: original results and all costs. output/repair_probe_01/: defective probe retained separately. site/review/: masked native outputs, full task evidence and observable transcripts. No model-internal reasoning is used as a review artifact.'),
 p('Research basis','head'),
 p('<link href="https://arxiv.org/html/2510.04374v1" color="#176d77">GDPval</link> recommends expert comparison and describes an experimental automated grader and tool/scaffolding effects. Our metrics and costs come only from our saved logs. <link href="https://arxiv.org/html/2606.09809v2" color="#176d77">Evaluation Cards</link> guides evidence presentation; it does not turn documentation into validity. The <link href="https://huggingface.co/datasets/openai/gdpval" color="#176d77">public dataset</link> is a diagnostic source, not the commercial asset offered here.'),
]))
build('turing-panel-review-and-pitches.pdf',pages)
anthropic_pages=[('Useful work without invented permission','Anthropic discussion brief | Proposed diagnostic, not a validated training product',[
 p('The 45-second opening','head'),
 p('"In our purchasing pilot, a Claude draft correctly stated that price changes need Finance, Program and Purchase approval. Its provisional-release clause then named only Program and Purchase; nearby text restored the three-way rule. The project owner marked that issue as requiring material correction. That is a narrow artifact inconsistency, not evidence of intentional deception or a model-wide failure rate. I propose a private, permissioned diagnostic that tests whether agents preserve authority and uncertainty in the work they deliver, while still completing authorized tasks."'),
 p('Show the evidence before selling the expansion','head'),
 p('Open case B\'s complete source and output, including its draft status, cap decision and three-way caveat. Then show case A: with opening stock unknown, a continuity plan assures that buffer stock and air freight cover the gap. Both labels concern selected issues only. Qualifications, full-output acceptance and consequential-error prevalence remain unmeasured.'),
 table(['Evidence from this project','What it supports'],[
 ['60 main-study attempts; five source families','A small diagnostic across two models, three conditions and two repeats; not 60 independent tasks.'],
 ['53 parseable outputs passed targeted facts','Fact extraction alone misses contradictions in the final artifact.'],
 ['10/12 critical-label judge agreements','All ten were shared negatives. Human calibration and positive-case detection are still unverified.'],
 ['$5.17 cumulative API spend','Includes invalidated judging and the later 16-run probe. Human labor is unmeasured.'],
 ],[216,283]),
 p('The offer and the buying decision','head'),
 p('Start with <b>30 fresh purchasing families</b>: ten development and twenty untouched evaluation families, each with complete-information, recoverable-information and conflicting-evidence versions. Hold the objective and deliverable fixed. Include realistic search and clarification, approved and proposed records, legitimate holds and positive controls where the agent should proceed.'),
 p('Deliver permissioned references, native expert outputs, authority/dependency state, source-linked rubrics, preference pairs and expert rationales. Have qualified reviewers validate realism and solvability before model evaluation. The value to test is detection of consequential artifact errors that facts-only checks miss, plus the cheapest effective remedy. No superiority over GDPval or AfterQuery has been established.'),
 p('<b>Close:</b> "Choose one workflow owner and two qualified reviewers. Agree what counts as accepted work and a consequential error. We will first test prompt and tool repairs; only persistent, verified failures justify separately sourced training data."'),
 p('Private source pointers: reviews/purchasing_calibration/case-B-full-output.pdf and case-A-full-output.pdf; output/paired_v1/summary.json; output/submission_audit/grader_diagnostics.json. Current public source rights are unverified; the proposed commercial product uses new permissioned lineages.','small'),
]),('Metrics that support the purchase decision','Pre-register definitions and thresholds before the fresh evaluation',[
 table(['Metric','Definition and decision use'],[
 ['Expert acceptance - primary utility','Accepted deliverables / all attempts on validated tasks. No final output counts as not accepted; unreviewed work stays unknown. Report counts, family-balanced estimates and correction time.'],
 ['Consequential errors - safety gate','Deliverables with at least one material, source-supported error / fully adjudicated deliverables. Separately report no-output, unknown and task-defect counts. Incomplete coverage cannot pass the gate.'],
 ['Paired workflow effect','For each family, average repeated-trial acceptance in each variant minus baseline; average the family differences. Report counts of baseline-accepted / variant-rejected pairs and their reviewed causes.'],
 ['Useful action and excessive holds','On prespecified cases where authorized completion is possible, report correct completion and unnecessary holds. Separate justified holds. Refusal alone must not improve the score.'],
 ['Judge validity','On the masked calibration set, report the full human-versus-judge matrix, missed consequential errors and false accepts. Include positive/negative counts and double-coded taxonomy agreement.'],
 ['Total cost per accepted deliverable','All attempted API, tool, retry and measured review/correction labor costs / accepted deliverables. If accepted count is zero, no finite unit cost. Disclose data-production costs separately.'],
 ],[140,359]),
 p('How to choose a configuration','head'),
 p('First require valid tasks, complete review coverage and prespecified acceptance, consequential-error and unnecessary-hold thresholds. Then choose the lowest total cost among eligible configurations. Use source-family uncertainty, keeping variants and repeats together; counts and few-family limitations accompany every interval. Twenty evaluation families cannot certify a rare-error target: even 0/20 independent family errors leaves a roughly 14% one-sided 95% upper bound before selection adjustment.'),
 p('Repair, then consider post-training','head'),
 p('Resolve the Word-file versus tracker contract and chronology defects; supply actual native-file creation, rendering and revision. Freeze a generic prompt/state-tool repair on development families and compare at matched budgets. The existing 16-run probe had defective dates in every input, so it cannot establish a clean repair effect. No model is selected today.'),
 p('If verified failures persist, collect successful trajectories for SFT and evidence-backed preferences on separate source/template lineages. Use RL only with validated transitions and rewards checking the actual artifact. Include correct-facts/wrong-action counterexamples and authorized-action controls; test transfer on untouched families. Current public families and descendants never enter training. No SFT/RL or training uplift is claimed.'),
 p('Where did the synthetic data come from?','head'),
 p('The current pilot used local deterministic transformations of public GDPval tasks; no teacher API generated business facts. Seed 20261030 controlled v1 run order only. Three later fictional families remain unvalidated candidates. For the fresh product, split permissioned lineages before generation, track source and transformation ancestry, check near-duplicates and restrict sealed evaluation access. Provider pretraining exposure is unknown; no zero-contamination guarantee is made.','small'),
])]
build('turing-anthropic-pitch.pdf',anthropic_pages)
spec={'status':'proposal_not_collected_or_authorized_for_spend','pilot':{'families':30,'occupation':'purchasing','development':10,'untouched_evaluation':20,'training':0,'variants_per_family':3},'conditional_expansion':{'new_families':240,'occupations':3,'train':120,'development':60,'sealed_test':60,'variants_per_family':3,'excludes_current_public_lineages':True},'cost_assumptions':{'expert_hours_per_family':3.5,'hourly_rate_usd':100,'api_per_family_usd':2,'acceptance_yield':0.9,'cost_per_accepted_family_usd':352/0.9,'pilot_30_accepted_families_usd':30*352/0.9,'measured_or_quoted':False},'refresh_proposal':'Monthly drift/rights review; quarterly new scenario lineages and after material workflow change.','stop_expansion_if':['Prompt/tool controls remove the target failure on fresh tasks.','Independent reviewer agreement is inadequate.','Rights or task validity remain unresolved.','No benefit transfers to untouched lineages.']}
(AUDIT/'private_dataset_proposal.json').write_text(json.dumps(spec,indent=2)+'\n')
print(json.dumps({'one_page':'turing-submission-one-page.pdf','panel_report':'turing-panel-review-and-pitches.pdf','intended_report_pages':len(pages)}))

if __name__=='__main__':pass
