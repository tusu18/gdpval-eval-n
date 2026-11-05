"""Render the finished planning artifacts. Requires ReportLab."""
from pathlib import Path
import json
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/pdf"
OUT.mkdir(parents=True, exist_ok=True)
NAVY = colors.HexColor("#15304B")
TEAL = colors.HexColor("#007F83")
LIGHT = colors.HexColor("#EAF5F4")
GRAY = colors.HexColor("#526174")
STYLES = getSampleStyleSheet()
STYLES.add(ParagraphStyle(name="TitleX", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=NAVY, spaceAfter=12))
STYLES.add(ParagraphStyle(name="SubX", fontSize=11, leading=15, textColor=GRAY, spaceAfter=15))
STYLES.add(ParagraphStyle(name="BodyX", fontSize=9.6, leading=13.2, textColor=NAVY, spaceAfter=8))
STYLES.add(ParagraphStyle(name="SmallX", fontSize=8, leading=10.8, textColor=GRAY, spaceAfter=5))
STYLES.add(ParagraphStyle(name="HeadX", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=TEAL, spaceBefore=9, spaceAfter=6))
STYLES.add(ParagraphStyle(name="CellX", fontSize=8.4, leading=11.1, textColor=NAVY))
STYLES.add(ParagraphStyle(name="TableHeadX", fontName="Helvetica-Bold", fontSize=8.4, leading=11.1, textColor=colors.white))

def P(text, style="BodyX"):
    return Paragraph(text, STYLES[style])

def T(headers, rows, widths=None):
    data = [[P(x, "TableHeadX") for x in headers]] + [[P(str(x), "CellX") for x in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), NAVY), ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F2F6F9")]),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("LINEBELOW", (0,0), (-1,0), .8, TEAL),
    ]))
    return table

def box(text):
    table = Table([[P(text)]], colWidths=[495])
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),LIGHT),("BOX",(0,0),(-1,-1),.5,TEAL),("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    return table

def footer(canvas, doc):
    canvas.saveState()
    w,h=A4
    canvas.setStrokeColor(colors.HexColor("#CFDCE3"));canvas.line(50,43,w-50,43)
    canvas.setFont("Helvetica",8);canvas.setFillColor(GRAY)
    canvas.drawString(50,30,"TURING FDE  /  PLANNING PACK  /  30 OCT 2026")
    canvas.drawRightString(w-50,30,str(doc.page))
    canvas.restoreState()

pages=[]

def page(title, subtitle, blocks):
    pages.append([P(title,"TitleX"), P(subtitle,"SubX")] + blocks)

page("Build the evidence, then sell the data", "Senior FDE / RL engineering plan - $25 API ceiling", [
    box("<b>Recommendation:</b> run a tightly controlled professional-work evaluation, turn observed failures into a small data specification, and sell a measurable pilot. The deliverable today is a plan and preparation toolkit. Model results and training uplift are not yet measured."),
    P("Three possible plans","HeadX"),
    T(["Plan","What it produces","Decision"],[
        ["A. Evaluation first","15 GDPval tasks, one capable model, reviewed artifacts, failure taxonomy, one-page findings.","Recommended. Best fit for the brief and $25."],
        ["B. Paired model study","Same 15 tasks on GPT and Claude, with matched tools and limits.","Optional only if access, token estimates, and review time fit the same cap. Cut reruns before cutting review."],
        ["C. Post-training proof","Fresh training data, same-checkpoint controls, SFT/RL experiments, independent real holdout.","Separate follow-on. GPU training and expert collection are outside this $25 evaluation plan."],
    ],[80,275,140]),
    P("What the attached brief actually asks","HeadX"),
    P("The Turing brief requests an evaluation, manual failure analysis, a simple website or one-page document, code/notebook, and a 15-minute pitch to two researchers. It allows a small occupation slice and emphasizes claims supported by your own results. Those are assignment requirements extracted from the PDF, not new instructions to send mail or publish anything."),
    P("Our proposed question","HeadX"),
    P("Can a capable model produce usable purchasing, project-management, and inventory deliverables under a fixed tool and cost budget? Which failures are repeated, materially important, and plausibly repairable with new data?"),
    P("The strongest commercial claim","HeadX"),
    P("Sell a diagnosis, a verified data intervention, and an independent test of transfer. Do not sell row count or promise an improvement before training has been compared fairly. The public benchmark is a diagnostic stand-in; a commercial product would require original rights-cleared data."),
    P("Completed preparation: the 220-row source index was downloaded at a pinned revision; 15 task IDs and separate solver/grader payloads were prepared; 24 procedural examples were generated and checked. No model call, training run, deployment, or submission occurred.","SmallX"),
])

page("What POsttrain actually teaches us", "Evidence from saved project artifacts; not a claim about AfterQuery's internal pipeline", [
    P("The earlier generation story is precise","HeadX"),
    P("The first contextual-safety training manifest records <b>384 rows from 14 template families</b>: ten paired scenarios with 16 variants per side, plus four ordinary benign templates with 16 variants each. That produces 320 paired rows plus 64 controls. Labels and full responses were assistant-authored; fixed entity, topic, and numeric substitutions expanded them. The manifest states that no teacher-model API calls were made. The exact assistant model used for authorship is not established by that manifest. [L1]"),
    P("A later version improved breadth but exposed the RL bottleneck","HeadX"),
    P("The saved R4B manifest reports 1,200 training rows, 300 scenario families, and 60 templates, plus 240 development rows from 12 different templates. It labels the data model-authored and not independently human verified. Its training-only readiness probe contains 96 prompts with eight samples each: 80 groups all correct, seven all wrong, and only nine with mixed correctness. Thus <b>90.6% had zero reward variance</b> in that probe. This is evidence about that sampled setup, not a universal RL threshold. [L2]"),
    T(["Lesson","Upgrade in this project"],[
        ["Rows are not independent coverage","Report source cases, templates, mechanisms, and variants separately. Keep all descendants together."],
        ["Correct formatting is not task success","Require opened, inspected artifacts and substantive critical checks; do not headline token accuracy."],
        ["A strong baseline matters","Compare with the unmodified model and a simple tool/checklist repair before attributing value to training data."],
        ["Reward must contain useful contrast","Probe success variation before GRPO. Review impossible, broken, and too-easy cases separately."],
        ["No exact overlap is a narrow finding","Add source/template lineage, document-level checks, access isolation, and independent fresh evaluation."],
    ],[155,340]),
    P("How to explain this in an interview","HeadX"),
    P("<i>In the earlier project, the synthetic data came from explicit, assistant-authored scenario templates expanded deterministically. It was not a purchased production corpus or a teacher API distillation set. The random or fixed variants controlled reproducibility; they did not create independent scenario diversity. For this project I would start with rights-cleared workflow cases, compute objective labels from a state model, and validate transfer on fresh real tasks.</i>"),
    P("The saved Mind2Web mock-trial also warns against a weak comparator: its primary adapter scored 18/124 offline actions versus 9/124 for the base but 23/124 for the majority baseline. That was oracle-shortlist action agreement, not live task completion. [L3]","SmallX"),
])

page("The GDPval evaluation to run", "15 tasks / 3 occupations / one frozen model-and-tool configuration", [
    P("Selection is based on inspectability before performance","HeadX"),
    T(["Occupation","N","Why this slice is useful"],[
        ["Project Management Specialists","5","Check schedule, cost, risk, and change-control evidence in spreadsheets, documents, and slides."],
        ["Buyers and Purchasing Agents","5","Inspect supplier comparisons, assumptions, numerical tradeoffs, and sourcing decisions."],
        ["Shipping, Receiving, and Inventory Clerks","5","Inspect inventory joins, shipping decisions, operational instructions, and exception handling."],
    ],[155,40,300]),
    P("The downloaded index has five tasks per occupation. We selected all five in each chosen occupation, rather than choosing by model outcome. The selected tasks list 20 input-file references. This is a purposive diagnostic sample, not a representative estimate of the economy. GDPval's source dataset and paper define the benchmark context. [S1, S2]"),
    P("Run contract","HeadX"),
    P("1. Pin the dataset revision and task IDs. Retrieve the 20 references, hash their bytes, open/render them, and record any unavailable or corrupted file. The preparation package currently lists them; it has not downloaded them."),
    P("2. Give each task a fresh sandbox with the task prompt and permitted reference files only. Mount no source Parquet, gold deliverables, rubrics, prior outputs, or model-specific examples. Preserve native file access and artifact-generation tools."),
    P("3. If a task requires external information, declare allowed sources and an evidence date. Block benchmark/gold retrieval and record retrieved URLs. A fixed evidence packet is useful for comparisons but is a protocol change that must be disclosed."),
    P("4. Start with two tool smoke tests using original fixtures. Freeze prompts, tool versions, effort, limits, and grading rules before the main run. If a pilot on benchmark items changes the setup, label those items development and keep any rerun separate."),
    P("5. Save the first submitted output, complete trace, artifact hashes, errors, usage, wall time, and cost for every scheduled task. Inspect artifacts, not just the model's message saying they were created."),
    P("6. Blind the reviewer to model identity. Review every task because n is small. Validate objective checks with known-good artifacts and deliberate subtle errors; adjudicate uncertain subjective criteria."),
    box("<b>Critical release detail:</b> the current GDPval index includes rubrics and reference deliverables. The prepared solver payload uses a field allowlist and excludes both. Hugging Face names the storage split 'train'; that does not make it appropriate training data for this evaluation. [S1]"),
    P("Pinned revision: 11e7900cdcac61bc4daf59e65feb238acda98fbf. Task IDs and payload hashes are in data/gdpval/manifest.json.","SmallX"),
])

page("Which model, and why?", "Choose for the experiment's role, available tools, and total cost", [
    T(["Role","Proposed choice","Reason and limitation"],[
        ["Primary solver","GPT-6.1 Sol","Current documented professional-work and tool support; $2 input / $10 output per million tokens at standard short-context pricing. Access still needs verification. [S10, S10b]"],
        ["Alternative / cross-provider check","Claude Sonnet 5.5","Documented tool and vision support with $2 / $10 per million token pricing. Use the same tasks and comparable tool access. Equal named effort does not imply equal compute. [S11]"],
        ["Synthetic generator","Procedural engine first; capable LLM for narrative and proposed trajectories","Compute numerical truth in code. Test candidate teachers on accepted-correct yield per dollar, coverage and error rate. A second model is not automatically an independent verifier."],
        ["Later trainable student","Qwen3-8B as a candidate","Open weights and Apache-2.0 model card make a controlled small-model experiment possible. Not the latest or presumed best; test baseline competence and hardware fit first. [S12]"],
    ],[90,125,280]),
    P("The $25 plan","HeadX"),
    T(["Allocation","Ceiling","What it buys"],[
        ["Smoke tests and pilot","$2","Tool/file feasibility and usage estimates."],
        ["Main 15 tasks","$12","Average allowance $0.80 per task, shared across all turns and tools."],
        ["Grading / judge spot checks","$4","Human review remains necessary; API budget does not pay for expert labor."],
        ["Targeted diagnostic reruns","$3","A small repair or stronger-model comparison; clearly separate from first-pass scores."],
        ["Contingency","$4","Usage uncertainty, permitted retries, tool charges; total never exceeds $25."],
    ],[160,55,280]),
    P("Illustrative token estimate, not measured spend: 40,000 total input tokens x $2/M + 12,000 total output/reasoning tokens x $10/M = $0.20 per task before tools, cache-write differences and other fees. Fifteen tasks would be $3 at those token counts. Agent loops can exceed them; count repeated context across every call. [S10b, S11]"),
    P("Start with 12 tool steps and eight minutes per task as feasibility limits. Tight limits may induce truncations; retain them as system outcomes and diagnose separately. Before each serial call, reserve the worst-case remaining token/tool charge. Unknown charges stay reserved. No model credentials were available in the inspected environment; no API calls were attempted."),
    P("Avoid an expensive model tournament. One well-audited model meets the brief. A second model helps show cross-provider failure patterns; it does not prove that new data trains either provider's proprietary model."),
])

page("Metrics that change a decision", "Lead with work completed correctly; keep cost and failure severity visible", [
    T(["Metric","Definition","Why it matters"],[
        ["Primary: usable deliverable rate","Tasks satisfying every mandatory artifact + all critical checks + at most minor non-substantive edits, divided by all scheduled tasks.","Measures whether the work is usable. Timeouts and broken outputs remain in the denominator."],
        ["Critical-error rate","Tasks with at least one predeclared material error / all scheduled tasks.","Prevents attractive formatting or easy rubric points hiding a wrong decision."],
        ["Macro task-rubric score","Normalize within each task using its documented scoring rule, then average tasks; also show occupation means.","Avoids letting a task with many rubric items dominate. Inspect signed penalties before normalization."],
        ["Cost per usable deliverable","All execution and retry cost / number of usable outputs; undefined if none succeed.","Captures economics of actual outcomes. Show grading cost separately and total study cost."],
        ["Judge error counts","False acceptances among human-rejected outputs; false rejections among human-accepted outputs; report counts and denominators.","A judge that rewards plausible wrong work can reverse the conclusion. Agreement alone is insufficient."],
        ["Review burden","Reviewer minutes to identify and repair substantive errors, when actually timed.","Useful business measure, but a tiny pilot cannot support a production ROI claim."],
    ],[105,240,150]),
    P("Define critical before looking at the outputs","HeadX"),
    P("Examples: a chosen supplier violates an explicit capacity constraint; a workbook silently drops required rows; a schedule contradicts a mandatory dependency; a decisive figure is unsupported by the supplied source. Cosmetic layout issues are usually noncritical unless they make the artifact unusable. A competent domain reviewer must confirm task-specific severity."),
    P("Small sample discipline","HeadX"),
    P("At n=15, one task changes the overall rate by 6.7 percentage points; one task changes a five-task occupation rate by 20 points. Show x/n, task-level outcomes, and error examples. A Wilson interval is only a descriptive binomial interval under independence, not proof of population representativeness. Shared employers/templates create dependence."),
    P("For a later A/B study, report per-task paired differences and resample independent source/template groups. With only three occupations, occupation-cluster inference is too unstable to carry a strong claim. Add fresh families and training seeds before claiming a small gain. Multiple generations of one task do not increase the independent task count."),
    P("Keep off the headline: BLEU/ROUGE, average answer length, training loss, raw judge reward, synthetic pass rate alone, and pass@k when deployment gets one attempt. These may diagnose behavior but cannot establish useful professional work."),
])

page("Turn failures into a data product", "A taxonomy is useful only when it changes the proposed intervention", [
    T(["Observed failure","First diagnostic","Data that might help"],[
        ["Missing or unreadable artifact","Check file tooling, dependency versions, output paths, and time limit.","Tool execution and save/reopen demonstrations, if the environment already works."],
        ["Wrong join, total, units, or formula","Recompute from inputs; inspect omitted rows and unit conversions.","Executable cases with verified tables, joins, boundary values, and unit changes."],
        ["Unsupported conclusion","Trace material claims to exact source cells or passages.","Evidence-linked decisions, conflicting sources, and justified uncertainty."],
        ["Constraint or workflow violation","Separate missed explicit requirement from missing domain knowledge.","Paired near-misses and valid solutions; explicit constraint checks and multi-step dependencies."],
        ["Failure to detect missing information","Verify whether the task is underspecified or the input is absent.","Answerable/unanswerable cases, bounded assumptions, and appropriate clarification."],
        ["Polished but professionally weak work","Blind domain review; do not equate fluency with quality.","Expert demonstrations and reviewed preference pairs with criterion-specific reasons."],
        ["Grader wrongly accepts/rejects","Replay known-good, subtle-error, equivalent-answer and adversarial fixtures.","Evaluator repair first; do not train against an untrustworthy reward."],
    ],[130,175,190]),
    P("Capture a failure record","HeadX"),
    P("Record task ID; violated criterion; artifact location/cell/page; observed versus required behavior; severity; primary cause; secondary causes; confidence; whether a tool/checklist fix resolves it; proposed data family; and acceptance test. Keep infrastructure failures distinct while retaining them in the system-success denominator."),
    P("Prioritize with evidence, not a universal magic score","HeadX"),
    P("Rank gaps by observed frequency, consequence, breadth across tasks, plausible data repairability, and verification cost. Use an ordinal table when those inputs are uncertain. Three materially wrong supplier choices with a shared constraint mechanism may justify a pilot more than many font inconsistencies."),
    P("A high-value confounder test","HeadX"),
    P("On a few failed tasks, rerun with a general artifact-validation checklist and the same model. If this repairs the failure, sell the workflow improvement or test whether it can be distilled later. Do not call the repair evidence that weight training or synthetic data already helped. These reruns are diagnostic and use previously exposed tasks."),
])

page("Where the synthetic data comes from", "Separate the source seed, specification, random seed, and generated artifact", [
    P("Four meanings of 'seed'","HeadX"),
    T(["Seed type","Concrete example","What it establishes"],[
        ["Source case","A licensed procurement workbook or a freshly authored expert workflow.","Provenance, realism, rights, and the independent source unit."],
        ["Task specification","Select a supplier subject to lead time, capacity, certification, and total cost.","The behavior being taught and the allowed variation."],
        ["Sampling seed","Integer 100 used by a fixed procedural generator.","Repeatable sampling. It does not prove diversity or cleanliness."],
        ["Training seed","RNG initialization for an optimizer/run.","A replication variable. It is not the generation source."],
    ],[90,245,160]),
    P("Proposed production pipeline","HeadX"),
    P("<b>1. Acquire and register.</b> Obtain permission for real workflow examples or commission expert cases. Record source ID, author, permitted uses, redactions, document hashes, and acquisition date. No customer corpus has been acquired for this plan."),
    P("<b>2. Partition before expansion.</b> Assign whole source, template, and near-duplicate components to train/development/holdout. Treat shared organizations and task mechanisms according to the desired generalization claim. Never random-split sibling variants."),
    P("<b>3. Build a structured world.</b> Represent inputs as data, constraints, and state transitions. Solve numerical truth deterministically, including infeasible cases, ties, missing fields, and exceptional paths. Render spreadsheets/documents from that world."),
    P("<b>4. Add language and trajectories.</b> A capable model may propose natural requests, explanations, or tool sequences from training-only specifications. Execute/replay the actions; preserve tool errors and recovery where authentic. Treat generated rationales as synthetic explanations, not evidence of the model's hidden reasoning."),
    P("<b>5. Verify and review.</b> Check schema, files, numerical invariants, answer consistency, and overlap; independently review ambiguous cases. Track accepted and rejected examples by family. Audit rejected examples to detect excessive filtering."),
    P("<b>6. Select and freeze.</b> Use development/training probes to target recurring, learnable errors while retaining coverage quotas and a random exploration sample. Record generation cost, acceptance yield, provenance, model snapshot if used, prompt hash, code hash, and verifier version."),
    box("<b>Implemented example:</b> 24 procedural supplier-choice cases from three original specifications. The generator model is <b>none</b>: Python expands assistant-designed rules and recomputes answers independently. No benchmark prompt or answer is read by the generator. These are demonstration fixtures, not expert gold or independent evaluation evidence."),
])

page("Contamination controls you can defend", "State the boundary you controlled and the uncertainty that remains", [
    T(["Leakage route","Control","Evidence to retain"],[
        ["Gold in solver context","Allowlist prompt/reference fields; mount no grader directory or raw dataset; separate tasks and caches.","Exact request/tool payloads, mounted-path inventory, access logs."],
        ["Benchmark reused as a seed","Generator receives training-only sources and aggregate capability briefs; no benchmark paraphrasing.","Input manifest, generator prompt hash, source lineage, denied-access checks."],
        ["Sibling or source leakage","Partition source/template components before augmentation; all descendants inherit the split.","Lineage graph and explicit overlap report; do not rely on different random seeds."],
        ["Text/document duplication","Hashes, normalized text, n-gram candidates, document/table fingerprints, semantic retrieval plus manual adjudication.","Threshold calibration on known overlaps/non-overlaps; candidate decisions and counts."],
        ["Test used for selection","Freeze model/recipe on development; independent final evaluator; log every test access.","Protocol timestamp or external commitment, selection history, run count."],
        ["Teacher/provider memorization","Fresh private tasks, source isolation, provider retention settings, and lineage checks.","Disclosure that unknown base/teacher pretraining exposure is not ruled out."],
    ],[100,225,170]),
    P("The right claim","HeadX"),
    P("<i>We prevented direct evaluation-item access in our own generation and adaptation path, checked source and template ancestry, and audited lexical and semantic candidates. We cannot establish that a public benchmark was absent from a proprietary model's pretraining. GDPval is therefore a public diagnostic; the confirmatory result would come from a fresh, independently authored holdout.</i>"),
    P("Important distinctions","HeadX"),
    P("Reading failures and using their mechanisms to design data makes that evaluated slice development evidence. A same-session 'hidden' file is not an independently sealed holdout. A different generator model does not guarantee independence. A hash protects bytes but does not prove when they were frozen. Benchmark canaries can detect some exposure paths; they cannot certify absence of exposure."),
    P("Apply your linked paper carefully","HeadX"),
    P("Evaluation Cards composes model, benchmark, and run metadata and surfaces reproducibility, completeness, provenance, and comparability. Its appendix says structured contamination controls remain future work, with contamination currently in free-text limitations. Add explicit exposure/access/overlap fields as <b>our extension</b>; do not claim the paper provides a contamination detector or that complete documentation proves a sound evaluation. [S3]"),
    P("The included lexical/lineage checker and folder separation are working preparation checks. Semantic deduplication, an access-enforced sandbox, independent authoring, and provider-retention validation remain implementation work.","SmallX"),
])

page("Prove the data improves a model", "A follow-on experiment, separate from the $25 take-home diagnostic", [
    P("Predeclare the hypothesis","HeadX"),
    P("Replacing a fixed fraction of generic training tokens with verified workflow data improves usable deliverable rate on fresh source/template-disjoint real tasks, without increasing critical errors, under a fixed starting checkpoint, training recipe, and inference budget. The minimum useful improvement and acceptable regression margin must be agreed before testing."),
    T(["Arm","Purpose","Keep fixed / report"],[
        ["Base checkpoint","Measures the unadapted starting point.","Same inference harness and evaluation."],
        ["Generic SFT","Controls for merely doing more training.","Same trainable parameters, optimizer, token exposure and selection budget."],
        ["Random verified workflow SFT","Tests the domain-data contribution.","Same starting checkpoint and training-token budget."],
        ["Targeted verified workflow SFT","Tests failure-guided selection versus random domain data.","Match training tokens; separately report teacher generation/selection spend."],
        ["Optional RL after SFT","Tests whether on-policy exploration adds value.","Match rollout/training compute within RL comparisons; SFT and RL steps are not equivalent."],
    ],[120,185,190]),
    P("Choose SFT, DPO, or RL by the signal","HeadX"),
    P("<b>SFT first</b> when the failure is missing procedures or skills and you can verify demonstrations. <b>DPO</b> when there are trustworthy chosen/rejected pairs for subjective professional quality; randomize ordering and control length/style bias. <b>RLVR/GRPO</b> only when the environment can be replayed and the reward survives adversarial checks. An open-ended rubric judge is not equivalent to an exact numerical verifier."),
    P("Before GRPO, run repeated completions on a stratified training probe. Measure fraction of groups with mixed correctness, invalid output rate, false reward acceptance, rollout tokens, and tool failures. All-correct and all-wrong groups offer no within-group correctness contrast in the standard centered group-relative signal. This is the direct lesson from the POsttrain readiness probe. Do not repair it with a format-only reward."),
    P("The experiment's success measures","HeadX"),
    P("Headline paired change in real-heldout usable work and critical-error rate. Also show teacher/generation cost, accepted-correct cases per dollar, number of unique families, total train/rollout tokens, wall time, and regressions. Repeat the chosen recipe across at least three training seeds when feasible; report all seeds, not the best. Budget and size this phase after a power/precision pilot."),
    P("A second provider's baseline result demonstrates the relevance of a gap across providers. It does not demonstrate that a dataset improves either proprietary model's weights. That requires the customer's own controlled training run."),
])

page("Research that changes this design", "Targeted primary-source review through 30 October 2026; newest is not automatically most applicable", [
    P("Evaluation Cards - June 2026 [S3]","HeadX"),
    P("<b>Use:</b> report each claim with model identity, task path, setup, grading, cost and uncertainty. <b>Boundary:</b> its four signals describe reporting context, not certification of capability or contamination. We extend the reporting idea with explicit contamination controls and attempted-run history."),
    P("Towards Active Synthetic Data Generation - revised February 2026 [S4]","HeadX"),
    P("The study compares iterative student-guided generation with static/random generation on mathematical and logical tasks. Simple uncertainty-based selection often performs well, and teacher-based scoring can consume budget better spent generating data. <b>Use:</b> compare targeted selection with random verified data at matched budgets. <b>Boundary:</b> the work studies SFT, not professional-artifact RL; reliable teachers are assumed in parts of the study. Our transfer is a hypothesis."),
    P("Detecting RL Post-training Contamination - ICLR 2026 [S5]","HeadX"),
    P("Self-Critique investigates entropy-based signals of RL training-set membership and introduces RL-MIA. <b>Use:</b> do not assume a likelihood-based pretraining contamination check covers RL. <b>Boundary:</b> evaluated primarily on math/logic and 0.5B-7B models; output probability access may be needed. It is an optional forensic probe, not our prevention mechanism or proof that a frontier model is clean."),
    P("Reasoning-Driven Synthetic Data Generation / Simula - TMLR 2026 [S6]","HeadX"),
    P("The authors describe controllable, reasoning-driven, seedless agentic generation and evaluate intrinsic and downstream properties. <b>Use:</b> a task specification can guide generation even without a large example corpus. <b>Boundary:</b> seedless generation does not supply professional realism, correct labels, or contamination guarantees. We prefer source-grounded workflows and deterministic truth for this project. Review depth here: official research abstract, not a reproduced experiment."),
    P("Demystifying evals for AI agents - Anthropic, January 2026 [S7]","HeadX"),
    P("The engineering guidance emphasizes inspecting transcripts and combining evaluation layers. <b>Use:</b> evaluate final artifacts alongside traces and objective checks; distinguish task, trial, grader, and environment. <b>Boundary:</b> this is engineering guidance, not evidence that our dataset or proposed model is superior."),
    P("Research discipline: paper outcomes support design choices and hypotheses. They must never be presented as results of this take-home. No downloaded paper was used as a source of benchmark performance claims for our run.","SmallX"),
])

page("The newest findings, with limits", "Three recent papers reinforce coverage and real-world validation", [
    P("When Does Training on Synthetic Data Provably Work? - 20 October 2026 [S8]","HeadX"),
    P("The paper studies binary-classifier transfer under assumptions including a shared conditional label distribution. It shows why good synthetic risk may fail to control real error when real data occupies regions absent from the synthetic distribution; additional assumptions permit bounds. <b>Use:</b> preserve real task coverage and validate on real cases. <b>Boundary:</b> classification theory and image experiments do not prove a GDPval or LLM-RL scaling law. We reviewed the primary abstract; no experimental reproduction was performed."),
    P("Synthetic Data with Verification - 29 October 2026 [S9]","HeadX"),
    P("In a linear-regression framework, verification threshold, generation noise, accepted sample size, and partial versus full fine-tuning interact. Tighter filtering does not uniformly lower risk. <b>Use:</b> record what the verifier rejects and whether accepted data loses coverage; test selection policies on development. <b>Boundary:</b> this very recent preprint is not a universal instruction to add noise or weaken safety/correctness gates in LLM training."),
    P("Synthetic versus Authentic RAG Queries - September 2026 [S13]","HeadX"),
    P("A university information-system case study finds synthetic and authentic queries differ in length, topics, coverage and retrieval behavior. <b>Use:</b> include messy, underspecified real workflows and assess which failures synthesis misses. <b>Boundary:</b> one RAG setting does not establish the same quantitative gap for professional deliverables; it motivates a transfer check rather than predicting our effect size."),
    P("What to take into the interview","HeadX"),
    T(["Tempting statement","Defensible statement"],[
        ["More synthetic data will help.","I will compare learning curves at matched token and generation budgets, then test transfer on real cases."],
        ["Our filter removes all bad data.","I will measure false acceptance, false rejection, accepted-family coverage, and downstream utility."],
        ["No duplicates means no contamination.","Exact duplication is one path; source ancestry, semantic variants, test-driven selection and pretraining exposure need separate treatment."],
        ["The latest paper proves our method.","It motivates this design under stated assumptions; our own experiment must establish the practical effect."],
    ],[185,310]),
    P("Publication status matters: the October 20 and October 29 items are new arXiv preprints. The September RAG paper states acceptance at CIKM 2026. The relevance of their methods is more useful here than their recency alone.","SmallX"),
])

page("Sell a research decision", "Same underlying evidence; different entry points for the two role-play audiences", [
    P("The core pitch","HeadX"),
    box("<i>We help you locate costly professional-work failures, build verified practice around those mechanisms, and test whether that practice transfers to fresh real tasks. Every proposed data family comes with source lineage, observable success checks, and a matched-budget experiment. The pilot earns expansion through measured improvement.</i>"),
    P("OpenAI researcher: lead with professional task outcomes","HeadX"),
    P("<i>I used a controlled GDPval slice to examine whether the model produces usable professional artifacts. I will show the exact failed requirements, distinguish tool constraints from data gaps, and propose fresh workflow families for the failures that persist. The purchase test is whether your chosen training recipe improves those behaviors on independent tasks at fixed compute and inference settings.</i>"),
    P("Show three pieces of evidence after the run: a correct-looking but materially wrong artifact, its traceable failed check, and an original training-family specification that teaches the missing behavior. GDPval itself is a public stand-in, not exclusive data to resell. This is an audience emphasis grounded in the benchmark, not a claim to know an internal roadmap. [S2]"),
    P("Anthropic researcher: lead with agent reliability and grading validity","HeadX"),
    P("<i>I will show where the agent's final artifact diverges from its apparent completion, how tool failures and recoveries affect outcomes, and whether the grader recognizes subtle but important errors. The proposed data includes realistic exceptions and recoverable failures, with independent checks so improved reward cannot hide worse work.</i>"),
    P("Use the same data and denominators. Emphasize trace inspection, final-state checks, and reliable grading, consistent with published agent-evaluation guidance. Do not assume the customer's objective is simply 'safety' or that OpenAI only cares about scale. [S7]"),
    P("A 15-minute run of show","HeadX"),
    T(["Time","Content"],[
        ["0-2 min","Problem, chosen population, exact protocol and one honest outcome headline."],
        ["2-5 min","Two or three inspected failures; materiality and evidence."],
        ["5-8 min","Data specification, seeding, verification, contamination boundary."],
        ["8-11 min","OpenAI and Anthropic pitches; connect each to the same measured evidence."],
        ["11-15 min","Cost/uncertainty, objections, proposed controlled pilot, questions."],
    ],[75,420]),
    P("Why buy instead of generate internally? The defensible value is rights-cleared expert workflow coverage, trustworthy labels, reproducible environments, and evidence of marginal training value. AfterQuery already publicly markets expert data, verifiers and RL environments; those features alone do not establish differentiation. [S14]"),
])

page("Answers to the questions you were asked", "Use past tense only for verified work; use future tense for the proposed pipeline", [
    P("Where was the data generated?","HeadX"),
    P("<i>For the earlier contextual-safety prototype, it was authored as explicit scenarios and expanded in local Python. The manifest records 384 rows from 14 families and no teacher API calls. The later R4B set expanded scenario and template coverage, but its labels were still not independently human verified. For Turing, the evaluation comes from pinned public GDPval data; any proposed training data comes from separate original or licensed workflows.</i>"),
    P("How was it seeded?","HeadX"),
    P("<i>The substantive seeds are source workflows and scenario specifications. Fixed variants or random seeds only reproduce expansion. I keep the source, template, sibling variants, and generated outputs linked, and assign the family to a split before generating descendants.</i>"),
    P("Which model generated it? Why that model?","HeadX"),
    P("<i>The earlier manifest says assistant-authored, with deterministic expansion and no separate teacher API. It does not identify an exact authoring model, so I would not invent one. In the new procedural example there is no generation-model API at all. For language and trajectories, I would compare teachers on independently verified yield and coverage per dollar; the teacher's brand does not establish label quality.</i>"),
    P("Why this evaluation model?","HeadX"),
    P("<i>I need a model capable of working with the actual files so failures are informative. GPT-6.1 Sol is the proposed primary at a documented moderate price; Sonnet 5.5 is the alternative if access or tool fit is better. I freeze its version and configuration and report the model-plus-harness result. I am not claiming it is the best model before the pilot.</i>"),
    P("How did you avoid evaluation contamination?","HeadX"),
    P("<i>I separate solver inputs from grader answers and rubrics, prevent evaluation items entering generation or training, and split by source/template ancestry rather than rows. I audit overlap and freeze selection before a fresh final test. Public benchmark pretraining exposure remains unknown. If I use an evaluation's failures to design data, I call that evaluation development and obtain a new confirmation set.</i>"),
    P("How is your data better? Why not just use RL?","HeadX"),
    P("<i>Better means more useful work on unseen real tasks at a matched cost, with no unacceptable critical-error regression. I test it against generic and randomly selected verified data, not just the original model. I start with SFT when reliable demonstrations teach the missing skill. I use RL only when the policy has something useful to explore and the verifier provides trustworthy contrast. The POsttrain probe showed why that readiness check matters.</i>"),
    P("What if the pilot finds no benefit?","HeadX"),
    P("<i>That is a valid outcome. I report it, check whether the intervention addressed the actual failure, and distinguish insufficient coverage, flawed labels, an incapable student, and a harness problem. I would not sell an unmeasured gain.</i>"),
])

page("What needs to happen next", "A concrete handoff from planning to a defensible take-home", [
    T(["Stage","Work","Exit evidence"],[
        ["Prepared now","Pinned selection, solver/grader data separation, procedural example, research review, protocol and metrics.","15 tasks / 20 reference pointers; 24 recomputed examples; nine preparation checks passed."],
        ["First 30-45 min","Configure model access; download/hash references; implement a fresh sandbox and cost ledger; smoke-test artifact creation.","A real file opens correctly, usage is recorded, and solver cannot read grading files."],
        ["Next 45-75 min","Freeze the settings, run the selected slice with cost reservations and trace capture.","One first-pass result or explicit failure for every scheduled task; actual spending reconciled."],
        ["Next 60-90 min","Open all artifacts; apply critical checks and rubric; classify failures; audit judge errors.","Task-level evidence table, checked denominators, two or three compelling cases."],
        ["Final 30-45 min","Replace the proposal with measured one-page findings, verify code, rehearse both pitches.","Claim-to-artifact links, exact cost, limitations and an original data-pilot specification."],
    ],[85,230,180]),
    P("Timing is an estimate","HeadX"),
    P("The brief estimates two to four focused hours. The sequence above can exceed that if file setup or review is slow. Prefer two complete occupations (ten tasks) with careful review if needed, and disclose that feasibility reduction before seeing model scores. Keep all failures; do not remove difficult tasks after the fact."),
    P("Hard boundaries for this iteration","HeadX"),
    P("The $25 ceiling covers API usage, not a full training study, expert acquisition, or paid GPU time. The current package includes preparation code but no paid provider runner. API credentials were absent from the inspected environment. Access, rendering tools, execution isolation, tool pricing, and task-specific critical checks still need validation before the first evaluation call."),
    P("An evaluation card for every measured claim","HeadX"),
    P("Capture run status and date; dataset revision and slice rule; task IDs and count; model snapshot; complete prompt; effort and sampling parameters; tool/environment versions; file hashes; step/token/time limits; retry policy; raw outputs; grading rules and versions; reviewer method; denominator; per-task results; uncertainty assumptions; costs; known exposure; overlap checks; and every attempted or aborted run. The supplied JSON is a proposed extension inspired by Evaluation Cards, not an assertion of compatibility with its canonical schema. [S3]"),
    box("<b>Submission gate:</b> do not submit the proposal as completed findings. The final one-pager must contain actual x/n results, actual cost, documented grading, inspected failure examples, a dataset opportunity, and limitations. Sending it to the address in the PDF is a separate action not performed here."),
])

SOURCES = [
    ("S1", "GDPval dataset, pinned index and dataset card", "https://huggingface.co/datasets/openai/gdpval"),
    ("S2", "GDPval: Evaluating AI Model Performance on Real-World Economically Valuable Tasks (2025)", "https://arxiv.org/abs/2510.04374"),
    ("S3", "Evaluation Cards: An Interpretive Layer for AI Evaluation Reporting, v2 (9 June 2026), especially Appendix B", "https://arxiv.org/html/2606.09809v2"),
    ("S4", "Towards Active Synthetic Data Generation for Finetuning Language Models, v2 (9 February 2026)", "https://arxiv.org/html/2512.00884v2"),
    ("S5", "Detecting Data Contamination from Reinforcement Learning Post-training for Large Language Models, v2 (18 March 2026), ICLR 2026", "https://arxiv.org/html/2510.09259v2"),
    ("S6", "Reasoning-Driven Synthetic Data Generation and Evaluation (Simula), Google Research / TMLR 2026", "https://research.google/pubs/reasoning-driven-synthetic-data-generation-and-evaluation/"),
    ("S7", "Demystifying evals for AI agents, Anthropic (9 January 2026)", "https://www.anthropic.com/research/demystifying-evals-for-ai-agents"),
    ("S8", "When Does Training on Synthetic Data Provably Work? (20 October 2026), preprint; abstract reviewed", "https://arxiv.org/abs/2610.28036"),
    ("S9", "Statistical Analysis of Synthetic Data with Verification: A Linear Regression Framework (29 October 2026), preprint", "https://arxiv.org/html/2610.40254v1"),
    ("S10", "OpenAI GPT-6.1 Sol model documentation and current pricing", "https://developers.openai.com/api/docs/models/gpt-6.1-sol"),
    ("S10b", "OpenAI API pricing; standard short-context rates checked 30 October 2026", "https://developers.openai.com/api/docs/pricing"),
    ("S11", "Anthropic model overview; Sonnet 5.5 capabilities and rates checked 30 October 2026", "https://platform.claude.com/docs/en/models/overview"),
    ("S12", "Qwen3-8B official model card", "https://huggingface.co/Qwen/Qwen3-8B"),
    ("S13", "Beyond Benchmark Scores: How Synthetic and Authentic Query Distributions Diverge in RAG Evaluation (13 September 2026)", "https://arxiv.org/html/2609.14579v1"),
    ("S14", "AfterQuery public product descriptions; company claims, not independently validated comparative performance", "https://www.afterquery.com/products"),
]

source_blocks=[]
for sid,title,url in SOURCES:
    source_blocks.append(P(f'<b>{sid}.</b> {escape(title)}<br/><link href="{escape(url)}" color="#007F83">{escape(url)}</link>', "SmallX"))
page("Sources and evidence boundaries", "Primary research, official model documentation, and the user's supplied brief", source_blocks)

project=Path("/Users/tusu18/.codex/.chatgpt-projects/g-p-6abd92c607008191b0be9fe57801c360")
localsources=[
    ("L1", "Initial synthetic training manifest", project / "xstest-experiment/gpu/data/train_manifest.json"),
    ("L2", "R4B generation manifest and readiness probe summary", project / "xstest-experiment/guard_training/data_r4b_v1/manifest.json"),
    ("L3", "Mind2Web mock-trial measured results", project / "mock-trial/outputs/results.md"),
    ("L4", "Guard training evaluation and overlap limitations", project / "xstest-experiment/guard_training/EVALUATION.md"),
    ("L5", "Nemotron-3 selection protocol; observed failure tradeoff and baseline", project / "xstest-experiment/guard_training/selection_protocol.json"),
]
localblocks=[P("These are saved artifacts from POsttrain, reviewed read-only. Their claims were used within their stated scope. This review did not rerun the old training, open its sealed holdout, or establish the current final status of every older experiment.")]
for sid,title,path in localsources:
    relative=str(path.relative_to(project))
    localblocks.append(P(f"<b>{sid}. {escape(title)}</b><br/>{escape(relative)}", "SmallX"))
localblocks += [P("Source root", "HeadX"), P(str(project).replace("/g-p-", "/<br/>g-p-"),"SmallX"),
    P("What the previous model choice actually meant","HeadX"),
    P("The saved Nemotron-3 protocol picked a research target rather than the baseline winner: WildGuard led the recorded balanced-accuracy comparison, while Nemotron-3 showed 199/200 unsafe detections and 83/250 benign false alerts. That motivated reducing false alerts subject to preserving unsafe detection. It did not make Nemotron-3 universally better. Preserve that distinction when asked 'why this model?' [L5]"),
    P("Measured here versus proposed", "HeadX"),
    P("Measured here: source index row counts, task selection, generated-fixture counts, deterministic answer checks, and preparation tests. Proposed: model execution, artifact grading, user-work success metrics, independent expert review, semantic overlap audit, SFT/RL training, and transfer evaluation. No proposed outcome is represented as measured."),
    P("Project scope", "HeadX"),
    P("This plan improves the rigor of the earlier preparation. It does not establish that our work is superior to AfterQuery's private products or research. The original brief is 'Field-Engineer-Take-Home-Project (1) (1).pdf', supplied from the user's Downloads folder. Its submission directions were treated as context; no message was sent.")]
page("Local evidence and honest claims", "A useful interview answer is specific about what was observed and what was not", localblocks)

def build():
    story=[]
    for i,p in enumerate(pages):
        if i: story.append(PageBreak())
        story.extend(p)
    doc=SimpleDocTemplate(str(OUT / "turing-fde-plan.pdf"),pagesize=A4,rightMargin=50,leftMargin=50,topMargin=47,bottomMargin=58,title="Turing FDE: Evaluation, Synthetic Data and Research Plan",author="Prepared for Tushar Singh")
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    one=[P("Professional work, verified", "TitleX"), P("Turing FDE take-home | ONE-PAGE PROPOSAL | 30 October 2026", "SubX"),
        box("<b>Question:</b> Where does a capable model produce professionally unusable artifacts, and which failures could targeted, verified training data close? <b>Status: preparation complete; evaluation results pending.</b>"),
        P("Proposed experiment", "HeadX"),
        P("Evaluate all five GDPval tasks in each of three occupations: purchasing, project management, and inventory/shipping (15 total). Use GPT-6.1 Sol as the primary, with Claude Sonnet 5.5 as an access-dependent alternative. Freeze tools, effort, limits, and grading; inspect every artifact. Solver receives prompts and input files only. [1]"),
        T(["Report","Definition"],[
            ["Usable deliverable rate","All required artifacts + no critical failure + at most minor edits; x/15."],
            ["Critical errors","Tasks with a material wrong decision, omitted requirement, or unsupported decisive claim."],
            ["Economics and reliability","Total execution cost per usable output; infrastructure failures; grader false accept/reject counts."],
        ],[145,350]),
        P("Proposed data product", "HeadX"),
        P("Original or licensed workflow seeds -> source/template split -> structured case generation -> executable answers and replayable trajectories -> independent verification -> frozen data release. Sell a controlled pilot against generic and random verified data. Compare fresh real-task outcomes at matched training and inference budgets."),
        P("Trust and contamination", "HeadX"),
        P("Keep gold/rubrics outside solver access; never seed from GDPval questions or answers. Track source ancestry, exact/near overlaps, and every test exposure. GDPval is public diagnostic evidence; base-model contamination remains unknown. A training-uplift claim requires a fresh independent holdout. Reporting follows the Evaluation Cards idea with explicit exposure fields added. [2]"),
        P("Budget and next decision", "HeadX"),
        P("Hard planned API cap: $25 ($2 smoke/pilot, $12 main run, $4 grading, $3 diagnosis, $4 reserve). After access and sandbox checks, run, inspect failures, and replace this proposal with measured findings. No model calls or API spending have occurred. GPU training and expert labor are outside this cap."),
        P('<b>Evidence prepared:</b> pinned dataset revision, 15 task IDs, 20 reference pointers, separate solver/grader payloads, 24 procedural fixtures and nine passing checks. No model performance is implied.',"SmallX"),
        P('[1] <link href="https://huggingface.co/datasets/openai/gdpval" color="#007F83">GDPval source</link> | [2] <link href="https://arxiv.org/html/2606.09809v2" color="#007F83">Evaluation Cards</link>. Full references, metrics, POsttrain lessons and pitch in the companion report.',"SmallX")]
    SimpleDocTemplate(str(OUT / "turing-one-page-plan.pdf"),pagesize=A4,leftMargin=50,rightMargin=50,topMargin=40,bottomMargin=55,title="Turing FDE One-Page Proposal").build(one,onFirstPage=footer,onLaterPages=footer)

if __name__=="__main__":
    build()
    print("Created planning report and one-page proposal.")
