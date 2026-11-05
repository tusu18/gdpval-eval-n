"""Submission-facing paired study and distinct pitches; no five-model leaderboard."""
import argparse,html,json
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate,PageBreak
from build_native_study_brief import p,table,footer
from run_completion_and_pairs import read,write
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/current_study_06'

ANTHROPIC='Can an agent preserve uncertainty and approval authority through the final deliverable? We test unsupported commitments and contradictions across prose, action tables and companion files. Every consequential finding must connect an authoritative source, an exact output passage and a business consequence. Include cases where proceeding is correct, so unnecessary refusal cannot win.'
OPENAI='Which professional-work failures persist after the agent can create, inspect and revise the actual deliverable? Start with a fresh, permissioned GDPval-style diagnostic on your own tool stack. If prompt and tool repairs do not resolve human-confirmed failures, collect verified trajectories, expert preference pairs and rationales on separate training families, then test on untouched families.'

def build(draft=False, allow_incomplete=False):
 c=read(OUT/'summary.json');cost=c['cost'];g=c['grader']
 if not draft and not allow_incomplete and not c['paired_execution_complete']:raise ValueError('Paired execution remains unfinished; use --draft or --allow-incomplete for an explicitly incomplete evidence snapshot.')
 fixture=read(ROOT/'output/grader_checks_05/constructed_results.json') if (ROOT/'output/grader_checks_05/constructed_results.json').exists() else None
 diagnostics=read(ROOT/'output/grader_checks_05/quote_format_summary.json');historical=diagnostics['cohort_raw_status_counts'].get('historical_calibration',{})
 historical_valid=historical.get('automated_assessment_not_human_acceptance',0);historical_invalid=historical.get('invalid_grader_evidence',0)
 grader_line=f"{g['received']}/{g['planned']} grader responses received; one request failed at the credit limit. All 36 constructed responses met the raw evidence-format checks. Only {historical_valid}/{sum(historical.values())} historical-output responses met them; {historical_invalid} failed. Quote matching does not establish semantic correctness. Human agreement is unmeasured."
 if fixture:
  q=fixture['critical_error_checks'];grader_line+=f" Against author-intended fixture labels, {q['detected']}/{q['scored_binary']} resolved planted consequential errors were detected; {q['planned']-q['scored_binary']} remain unresolved or unrun. These are constructed checks, not expert validation."
 cost_line=f"Provider-reported cumulative API cost: ${cost['reported_cumulative_usd']:.4f}, including ${cost['reported_this_continuation_usd']:.4f} in this continuation. {cost['unresolved_charge_records']} request-charge records remain unresolved. All attempts and judging stay in the cost accounting; human review/correction time is unmeasured."
 mechanical=c.get('paired_mechanical_outcome_counts',{})
 execution_line=f"Among the {c['paired_finished_attempts']} finished attempts, {c['paired_submitted_attempts']} submitted files, {mechanical.get('transport_or_provider_failure',0)} stopped with provider/transport errors and {mechanical.get('response_token_limit',0)} reached a response-token limit. These are execution outcomes, not human business-error labels. Only {c['pairs_with_both_submitted']}/{c['paired_families']} families have both submissions available for comparison."
 probe=c.get('request_recovery_probe')
 probe_line=(f" A separate selected one-case request-recovery check submitted {probe['submitted_attempts']}/1 deliverables; {probe['logical_requests_retried']} request{' was' if probe['logical_requests_retried']==1 else 's were'} retried identically and {probe['retried_requests_with_a_received_response']} then received a response. It does not replace earlier outcomes or establish reliability or business quality." if probe and probe['finished_attempts'] else '')
 flow=[p('When correct facts become unsupported commitments','title'),
  p('The gap: a document can state a governing fact correctly and still recommend an action that violates it. The dataset ask is a fresh, permissioned set of matched professional workflows with expert evidence, not resale of public benchmark tasks.','quote'),
  p('What the evidence currently supports','head'),
  p('Two historical purchasing issues were labeled “material correction required” by the project owner: unsupported continuity coverage and an inconsistent approval exception. These are issue-only labels, not whole-output acceptance, expert qualification or an estimated error rate.'),
  p(f"The focused development study fixes one Claude model across {c['paired_families']} baseline/conflict task pairs. {c['paired_finished_attempts']}/{c['paired_planned_attempts']} attempts finished; {c['paired_submitted_attempts']} submitted native deliverables and both submissions are available for {c['pairs_with_both_submitted']}/{c['paired_families']} task families. Business quality awaits full-output human review."+(' Execution remains incomplete after a credit-limit rejection; this is a partial evidence snapshot.' if not c['paired_execution_complete'] else '')),
  p(c['submission_engineering_line'],'small'),
  p('The decisive measurements','head'),
  p('Measure human acceptance, consequential errors and whether final decisions honor the authoritative evidence. Calibrate the grader on 20 complete human reviews. Select a model only after error and useful-completion gates are agreed and met; then compare total cost per accepted deliverable.'),
  p(grader_line,'small'),
  p('The commercial pilot','head'),
  p('Propose 30 newly authored families with three versions each: 10 development families and 20 untouched evaluation families. Deliver sources, native gold files, evidence maps, expert rationales and preference pairs. Begin with five development families to measure authoring and review cost before pricing the full collection.'),
  p(cost_line,'small'),
  p('Current decision: complete human review and adjudicate task defects. No model ranking, human-calibrated error rate, dataset-superiority claim or training improvement is established.','small'),
  PageBreak(),p('A matched diagnostic, with explicit limits','title'),
  p('Question and protocol','head'),
  p('Holding the professional objective and agent setup fixed, does a misleading foreground brief or reference change the acceptability of the final deliverable? Each family has a baseline and conflict version, presented in a frozen shuffled order. Both versions already contain approved and unapproved workspace records. The challenge changes foreground information and sometimes adds copied working notes; this is not a clean no-conflict versus conflict-only contrast. One attempt per version; the unit of analysis is the source family.'),
  p('Fixed model: '+c['fixed_model']+'. Same system instructions, native tools, reasoning setting and per-attempt limits: 16 turns, 80 tool calls and 10,000 generated tokens per response, including counted reasoning tokens. Model aliases may change; returned identifiers are retained. Equal limits do not prove equal internal compute.'),
  p('Sources and task construction','head'),
  p('Five inspected development families: three public GDPval derivatives and two constructed scenarios. Approved records and unapproved drafts create controlled conflicts; all versions preserve the business objective and deliverable contract. Chronology and contract checks pass, but independent domain validation remains pending. This is not a fresh held-out test or a new 10-family collection.'),
  p('The agent sees text/table extracts and local workspace tools, a recorded clarification service, and tools to write, reopen, render, inspect and revise DOCX/XLSX. Search is lexical and clarification is scripted. Audit-field names can cue the relevant facts. These are material limits on realism and interpretation.'),
  p('Contamination and seeds','head'),
  p('Private evidence maps, reference answers and labels are outside solver access. Entire family lineages must be separated before future training or tuning. No training ran; public pretraining exposure cannot be ruled out. Scenario facts were authored and versioned, not sampled from a teacher model. The seed shuffles run order only; it does not make model generation deterministic.'),
  p('What remains uncertain','head'),
  p(execution_line),
  p('Five chosen families cannot support broad model reliability claims. Mechanical submission is not acceptance. Keep invalid tasks, missing outputs, unresolved labels and provider failures visible. Report counts beside any percentages; use family-level paired uncertainty after labels exist. A second judge family adds diversity, not ground truth.'),
  p('Private engineering appendix','head'),
  p('The initial five-model pass, failed requests and selected recovery attempts remain in the coordinator evidence. They are engineering diagnostics and do not enter a model-ranking table or the paired research denominator. Historical evidence hashes are preserved.'+probe_line,'small'),
  PageBreak(),p('Anthropic: evidence-preserving decisions','title'),p(ANTHROPIC,'quote'),
  p('Why purchasing and change control','head'),
  p('These workflows make authority and resource constraints inspectable: supplier continuity, landed cost, price-change approval, delivery feasibility, and consistency between a procedure, form and tracker. A correct rule in one paragraph cannot cancel an unsupported instruction elsewhere.'),
  p('Validate the grader before selling its scores','head'),
  p('Compare automated judgments with the frozen 20-case human queue. Report false accepts, missed consequential errors, false alarms, task defects and unresolved labels with denominators. If there are no human-confirmed positive errors, sensitivity is unmeasurable. Obtain independent reviewer agreement before describing a taxonomy as reproducible.'),
  p('Reward-gaming controls','head'),
  p('The 36 constructed checks cover substance-changing mutations, correct answers, identical controls and harmless presentation changes. Require exact source/output evidence and counterevidence, inspect cross-file decisions, and test authorized proceed cases alongside justified holds. Author expectations remain hypotheses until independently reviewed; quote matching checks traceability, not semantic entailment.'),
  p('Show the raw evidence','head'),
  p('Provide complete sources, observable transcripts and native outputs for any named failure category. Do not label intentional deception from an unsupported claim alone. The two earlier owner judgments are useful examples, but neither establishes a whole-output acceptance label.'),
  p('Pilot ask','head'),
  p('One workflow owner, two qualified reviewers and agreed error/utility gates. Deliver a private task pack and human-calibrated grader report. Price from timed authoring, review and correction work. A training-data purchase is conditional on verified residual failures.'),
  PageBreak(),p('OpenAI: a testable supervision hypothesis','title'),p(OPENAI,'quote'),
  p('What the buyer receives','head'),
  p('Every family includes provenance and permissions, realistic source files and allowed tools, authoritative facts, executable calculations and native-file checks, a criterion-level evidence map, expert gold deliverables and rationales. Expert pairwise preferences must compare real alternatives and explain the business consequence, not reward surface phrasing.'),
  p('Which errors would more data fix?','head'),
  p('None has yet been proven data-addressable. First repair task defects, access problems and output tooling. Test a prompt repair under matched budgets. Persistent human-confirmed errors become candidates for targeted data; persistence alone does not prove data is the only solution.'),
  p('A controlled training decision','head'),
  p('Only then propose separate training lineages, provisionally 50 families and 150 verified trajectories. Compare the intervention with an unchanged baseline on fresh held-out families at matched inference settings. Keep evaluator feedback out of the sealed split; retire a family from that split once it informs tuning.'),
  p('Economic acceptance','head'),
  p('Total cost per accepted deliverable includes generation, retries, judging, tools and measured human review/correction. Select the lowest-cost configuration only among those meeting agreed consequential-error and useful-completion gates. Sampling more outputs and selecting the best is a selection intervention, not proof of SFT or RL improvement.'),
  p('Stop criteria','head'),
  p('Stop or redesign when sources are not permissioned, tasks are not independently solvable, judge errors remain unacceptable, or task/prompt/tool changes resolve the alleged data gap. Do not sell a training effect before testing one.'),
  p('Coding-agent contribution','head'),
  p('The assistant implemented the workflow, tests, evidence maps, orchestration and packaging. It proposed the taxonomy and drafted the pitch. Human review, domain expertise, commercial rights and lab endorsement were not manufactured. Evaluation Cards document evidence; documentation is not proof of evaluation quality.','small')]
 dest=OUT/'preview.pdf' if draft else ROOT/'output/pdf/turing-native-study-and-two-pitches.pdf'
 SimpleDocTemplate(str(dest),title='Turing - paired professional-work diagnostic',author='Project working report',pagesize=A4,leftMargin=48,rightMargin=48,topMargin=40,bottomMargin=44).build(flow,onFirstPage=footer,onLaterPages=footer)
 write(OUT/'submission_content.json',{'headline':'When correct facts become unsupported commitments','engineering_line':c['submission_engineering_line'],'anthropic_pitch':ANTHROPIC,'openai_pitch':OPENAI,'grader_line':grader_line,'cost_line':cost_line})
 print(json.dumps({'pdf':str(dest),'five_model_table':False}));return dest
if __name__=='__main__':
 p_=argparse.ArgumentParser();p_.add_argument('--draft',action='store_true');p_.add_argument('--allow-incomplete',action='store_true');a=p_.parse_args();build(a.draft,a.allow_incomplete)
