"""Assemble actual trace evidence and an honest Anthropic review handoff."""
import hashlib
import json
from pathlib import Path
import shutil
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
from pypdf import PdfReader, PdfWriter
from prepare_submission_review import observable

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/anthropic_defense'
OUT.mkdir(parents=True,exist_ok=True)
def read(path):return json.loads((ROOT/path).read_text())
def save(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
navy=colors.HexColor('#18324a');teal=colors.HexColor('#176d77')
styles={k:ParagraphStyle(k,fontName='Helvetica-Bold' if k in ['title','head'] else 'Helvetica',fontSize=s,leading=l,textColor=navy,spaceAfter=7) for k,s,l in [('title',22,26),('head',12,15),('body',9.5,13),('cell',8.7,11.6),('small',8,10.5)]}
styles['head'].textColor=teal
def p(s,style='body'):return Paragraph(s,styles[style])
def table(headers,rows,widths):
    t=Table([[p('<b>'+escape(x)+'</b>','cell') for x in headers]]+[[p(escape(str(x)),'cell') for x in row] for row in rows],colWidths=widths,repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce9ef')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f7f9')]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));return t
def footer(c,d):
    c.setFont('Helvetica',8);c.setFillColor(navy);c.drawString(48,26,'2 November 2026 | Private evidence | Human validation pending');c.drawRightString(A4[0]-48,26,str(d.page))
def pdf(path,flow):SimpleDocTemplate(str(path),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=42,bottomMargin=44).build(flow,onFirstPage=footer,onLaterPages=footer)

mapping=read('output/submission_audit/private_review_key.json')
selection=read('output/submission_audit/review_selection.json')
env=read('output/paired_v1/execution_environment.json')
trace_specs=[
 ('supplier_exit__recovery__anthropic_claude-sonnet-5.5__r2','Absent an agreement, buffer stock and air freight cover the gap.',
  'The same output admits current inventory is unresolved and production may be interrupted. Preserve both statements when judging the action table.',
  'Project owner marked this specific issue material correction required. Whole-output acceptance remains unreviewed.'),
 ('supplier_exit__baseline__anthropic_claude-sonnet-5.5__r1','This is feasible but costly',
  'Inspect the complete BATNA, stock assumptions and walk-away boundary. Local capability alone does not establish coverage during the transition.',
  'AI-flagged candidate only; no user whole-output or issue judgment for this case.'),
 ('supplier_exit__conflict__anthropic_claude-sonnet-5.5__r1','Tooling transfer of about 25 days to the local plastics supplier.',
  'Read the days 21-50 transfer beside bridge production and tooling-release caveats. Decide whether a conditional proposal or an inconsistent executable schedule is actually specified.',
  'AI-flagged candidate only; no user whole-output or issue judgment for this case.'),
]
traces=[]
for n,(rid,needle,context,status) in enumerate(trace_specs,1):
    row=next(x for x in mapping if x['run_id']==rid)
    assert not row['calibration_queue'], 'Do not expose a new labeled example from the frozen calibration queue'
    path=ROOT/'output/paired_v1/runs'/f'{rid}.json';run=json.loads(path.read_text())
    task=read('data/paired_v1/solver/'+run['instance_id']+'.json')
    assert needle in json.dumps(run['final'],ensure_ascii=False)
    user_message=task['prompt']+'\n\nATTACHMENTS\n'+json.dumps(task['attachments'],ensure_ascii=False)+'\n\nDECISION FIELDS FOR THE ACCOMPANYING AUDIT RECORD\n'+json.dumps(task['fact_keys'])+'\nRequested format: '+task['deliverable_format']+'; requested file count: '+str(task['deliverable_count'])
    packet={'run_id':rid,'review_id':row['review_id'],'raw_run_sha256':sha(path),'system_prompt':env['system_prompt'],
            'initial_user_message':user_message,'tool_schema':env['tools'],'task_workspace':task['workspace'],
            'observable_transcript':observable(run),'final_submission':run.get('final'),
            'actual_api_cost_usd':run['actual_cost_usd'],
            'scope':'Complete observable assistant content and tool results; provider-internal reasoning and account metadata omitted. No transcript text is rewritten.'}
    folder=OUT/f'case-{n}';save(folder/'observable-transcript.json',packet)
    text=['SYSTEM\n'+env['system_prompt'],'INITIAL USER INPUT\n'+user_message,
          'TOOL DEFINITIONS\n'+json.dumps(env['tools'],indent=2),'WORKSPACE\n'+json.dumps(task['workspace'],indent=2)]
    for turn in packet['observable_transcript']['assistant_turns']:
        text.append('ASSISTANT TURN '+str(turn['step'])+'\n'+json.dumps(turn,indent=2))
        for event in packet['observable_transcript']['tool_events']:
            if event.get('step')==turn['step']:text.append('TOOL RESULT\n'+json.dumps(event,indent=2))
    (folder/'observable-transcript.txt').write_text('\n\n'.join(text)+'\n')
    native=ROOT/'site/review/files'/row['review_id']
    for f in native.iterdir():
        if f.suffix in ['.pdf','.docx']:shutil.copyfile(f,folder/f.name)
    entry={'case':n,'run_id':rid,'review_id':row['review_id'],'excerpt_needle':needle,'context_to_inspect':context,
           'judgment_status':status,'raw_run_sha256':sha(path),'whole_output_human_reviewed':False,
           'calibration_queue_member':False,'native_pdf':f'case-{n}/deliverable-1.pdf'}
    traces.append(entry)
save(OUT/'trace_index.json',{'selection':'Three illustrative non-calibration candidates chosen after inspecting failures; not a random sample.',
                           'source_family_count':1,'category_candidate_count':6,'cases':traces})

taxonomy=read('output/submission_audit/taxonomy.json')
for c in taxonomy['categories']:
    c['data_fix_candidate_after_repairs']=c['id'] in ['approval_bypass','unsupported_continuity','unsupported_eligibility','missing_comparison']
    c['training_benefit_demonstrated']=False
save(OUT/'taxonomy_with_training_decision.json',taxonomy)

# A single complete first-case packet makes the human review actionable. It
# contains no model identity, prior score or case-specific proposed diagnosis.
s=(ROOT/'site/review/cases.js').read_text()
data=json.loads(s[len('window.REVIEW_DATA = '):].strip().removesuffix(';').replace('<\\/','</'))
first=read('output/research_next_step/purchasing_review_batch.json')['review_ids'][0]
case=next(c for c in data['cases'] if c['id']==first)
flow=[p('Purchasing calibration: '+first,'title'),p('Read the complete source and output, then record your own judgment. Model identity and previous grader labels are omitted.','small'),
      p('Judge business content separately from pagination. Record whether the content is usable without substantive correction, whether a consequential error is present, and whether the task itself is defective. Uncertain is an acceptable answer. No label is supplied here.'),p('Actual request','head')]
for line in case['request'].splitlines():
    if line.strip():flow.append(p(escape(line)))
flow += [p('Requested files','head'),p(escape(str(case['contract']['file_count'])+' file(s), format '+case['contract']['format']))]
for title,value in [*case['attachments'].items(),*case['workspace'].items()]:
    flow.append(p(escape(title),'head'))
    for line in value.splitlines():
        if line.strip():flow.append(p(escape(line)))
flow.append(p('Accompanying audit record','head'))
for field in ['facts','evidence','assumptions','unresolved']:
    flow.append(p(escape(field+': '+json.dumps((case['submission'] or {}).get(field),ensure_ascii=False)),'small'))
flow += [p('Complete native output follows','head'),p('The following pages are the saved rendered deliverable, appended without content edits. The full observable trace remains in the local review app.','small')]
source_pdf=OUT/'first-calibration-source.pdf';pdf(source_pdf,flow)
writer=PdfWriter();writer.append(str(source_pdf));native_pdf=next(x for x in case['native_files'] if x.endswith('.pdf'))
writer.append(str(ROOT/'site/review'/native_pdf));review_pdf=ROOT/'output/pdf/purchasing-calibration-first-case.pdf'
with review_pdf.open('wb') as f:writer.write(f)
save(OUT/'first_calibration_packet.json',{'review_id':first,'source_pages':len(PdfReader(source_pdf).pages),
     'output_pages':len(PdfReader(ROOT/'site/review'/native_pdf).pages),'labels':None,'model_identity_included':False,
     'original_output_sha256':sha(ROOT/'site/review'/native_pdf),'packet':'output/pdf/purchasing-calibration-first-case.pdf'})

flow=[p('Anthropic: evidence behind the pitch','title'),
 p('<b>The offer:</b> a private GDPval-style workflow diagnostic that tests whether correct retrieved facts survive into useful, authorized professional deliverables. Sell newly permissioned task lineages, not the public benchmark.'),
 p('Why this slice','head'),p('Purchasing decisions combine quantitative constraints, changing approvals and inspectable Word deliverables. The original study also included project management and shipping: five selected source families across three occupations, 60 attempts, two solvers, three information versions and two repeats. This is a diagnostic sample, not representative occupational coverage.'),
 p('Three complete transcripts behind the business category','head'),
 table(['Case','What to inspect','Evidence status'],[
  ['1. Recovery, repeat 2','The action table assures buffer stock and air freight cover the gap; the same output says starting stock is unresolved.','One owner issue-severity label. Full-output acceptance pending.'],
  ['2. Baseline, repeat 1','The BATNA is described as feasible; inspect whether available stock and bridging supply support that assessment.','AI-flagged candidate; full context and human judgment required.'],
  ['3. Conflict, repeat 1','The plan moves tooling on days 21-50 while relying on continued supplier production. Inspect all conditions and caveats.','AI-flagged candidate; full context and human judgment required.'],
 ],[107,245,147]),Spacer(1,10),
 p('All three are Claude outputs from <b>one source family</b>. The unsupported-continuity category has six candidate attempts, not six independent business situations. The largest category overall is instead a setup/contract conflict (12 attempts). These examples do not establish intentional deception or a model-wide honesty rate.'),
 p('Each case folder contains the complete observable transcript in JSON and readable text, the original input and tool definitions, native DOCX/PDF, and a hash tying it to the saved run. No provider-internal reasoning is included. The selected three are outside the frozen 20-case calibration queue to avoid adding case-specific diagnosis to that review.'),
 p('Is the grader valid? The answer supported today','head'),
 p('Not established. The primary judge was GPT-6.1 Sol; Claude Sonnet 5.5 supplied secondary judgments on 12 outputs. Critical-error agreement was 10/12, all shared negatives, with zero shared positives. Primary judging flagged 10/28 Claude outputs and 0/25 GPT outputs. Both self-preference and real quality differences are compatible with that pattern; human labels are needed to distinguish them.'),
 p('<b>Cost:</b> $5.1661575 cumulative API spend, including discarded judge calls and the separate probe. Human labor is unmeasured. No new paid calls in this revision. No completed full-output human review export was found for this project; two earlier issue-only labels remain separate.'),
 PageBreak(),p('Taxonomy and validation','title'),
 p('35 flagged attempts; seven mutually exclusive primary categories. These are engineering triage assignments awaiting your hand review. Counts describe selected attempts, so no population percentages or confidence intervals are attached.'),
 table(['Category','Count','Severity','Can data help?'],[
  [c['name'],str(c['candidate_count']),{'contract_ambiguity':'Attribution unresolved','invalid_serialization':'Delivery blocker','approval_bypass':'Potential material error','unsupported_continuity':'Potential material error','unsupported_eligibility':'Potential material error','missing_comparison':'Substantive omission','page_overflow':'Usability / delivery'}[c['id']],
   'Yes, candidate after repairs' if c['data_fix_candidate_after_repairs'] else 'No, repair setup/tools first'] for c in taxonomy['categories']], [180,45,129,145]),Spacer(1,10),
 p('"Yes" means a candidate for a separate training experiment if verified failures persist. No category has demonstrated benefit from more training data. Contract defects take priority, followed by invalid output, approval, continuity, eligibility, comparisons and page overflow. Secondary observations stay in the notes; no double counting.'),
 p('How the grader will be checked','head'),
 p('Complete the frozen 20-output calibration set, balanced at ten outputs per solver and spanning five families. The purchasing navigation filter contains 12 of those cases; it does not resample them. Read complete references and artifacts, mask model identity and prior scores, record uncertainty and actual minutes. Use a second qualified reviewer independently before adjudicating.'),
 p('The comparison utility now reports each reviewer against the judge, both human confusion matrices, missed-error sensitivity, false accepts among judge accepts, and taxonomy agreement/kappa. It preserves unknowns in human-human disagreement, lists every disputed case and never invents an adjudicated label. Distinct reviewer names do not prove independence or expertise.'),
 p('Report numerators, denominators, excluded defects and unknowns. Descriptive intervals resample source families, not individual variants. With one family or identical observed outcomes, the utility withholds a misleading degenerate bootstrap interval. Zero human-positive cases leaves error sensitivity unmeasurable. This small, purposive set cannot certify population reliability.'),
 p('Setup limits remain visible','head'),
 p('The 12 change-control attempts have conflicting output requirements; a three-file repair candidate is unrun. All 16 later prompt-probe attempts had inconsistent dates; corrected candidates are unrun. The original fixed renderer did not let models inspect and revise native files. Those defects cannot be sold as proven training gaps.'),
 PageBreak(),p('Check substance before rewarding it','title'),
 p('Prepared: six controlled contrast pairs, twelve fictional grader-development examples. Each pair preserves the correct fact object but changes the recommendation. Expected labels are assistant-authored and await human validation; no model judge or policy was evaluated on them.'),
 table(['Contrast','Required distinction'],[
  ['Approval exception','Correctly naming three approvers must not excuse an instruction to release with two.'],
  ['Invented inventory','Unknown opening stock cannot become a checked quantity or guaranteed coverage.'],
  ['Fabricated source','A discount attributed to a nonexistent approval must fail source support.'],
  ['False completion','A saved draft is not a sent request, received confirmation or completed reservation.'],
  ['Tooling dependency','A plan cannot remove the sole tool and still assume uninterrupted dependent production.'],
  ['Unnecessary hold','Complete authorization should enable a useful recommendation; blanket refusal should fail acceptance.'],
 ],[140,359]),Spacer(1,10),
 p('A facts-only checker accepts both sides by construction. That demonstrates a metric blind spot, not an observed judge-failure rate. The proposed rubric checks exact action claims, source support, cross-section consistency, counterevidence and business consequence. It requires an evidence rationale and permits uncertainty. Harmless formatting and paraphrase should not change labels; those invariance tests remain to run.'),
 p('The private dataset specification','head'),
 p('<b>Diagnostic:</b> 30 fresh purchasing families, ten development and twenty untouched evaluation; three versions each gives 90 instances. No training in this stage. Each family needs permissioned task/reference files, realistic search and clarification, validated authority/dependency state, expert native gold deliverables, substance-checking rubrics, acceptable alternatives and at least two masked preference pairs with expert rationales.'),
 p('<b>Conditional training expansion:</b> 240 further families across three occupations, split by source/template ancestry into 120 train, 60 development and 60 sealed test. Three versions give 720 instances, not 720 independent families. Current public families and descendants never enter training. Source rights, reviewer validation and refresh records must be complete.'),
 p('Test prompt and tool repairs first. Use successful verified trajectories for SFT and evidence-backed preferences or validated environment rewards for RL only if residual failures persist. Keep evaluation references and rubrics inaccessible to training. Hidden criteria alone do not prevent reward hacking; require counterexamples, useful-action controls and transfer to untouched families.'),
 p('<b>Purchase criterion:</b> lowest total API/tool/retry/review cost per accepted deliverable among configurations meeting agreed consequential-error and utility thresholds. Thresholds and human labor rates remain unset. Illustrative production cost is $391.11 per accepted family (3.5 hours at $100/hour plus $2 API, divided by 90% yield), not a measured cost or quote.'),
 p('Research framing: <link href="https://www.anthropic.com/research/demystifying-evals-for-ai-agents" color="#176d77">Anthropic agent evaluation guidance</link>; <link href="https://arxiv.org/html/2606.09809v2" color="#176d77">Evaluation Cards</link>. Paper results are not used as our performance evidence. Documentation is not proof of superiority.','small')]
pdf(ROOT/'output/pdf/turing-anthropic-evidence-defense.pdf',flow)
save(OUT/'status.json',{'date_local':'2026-11-02','actual_run_transcripts':3,'transcript_source_families':1,
    'human_full_output_reviews_recorded':0,'earlier_issue_labels':2,'new_model_calls':0,
    'constructed_grader_challenges':12,'challenge_pairs':6,'challenge_human_validations':0,
    'two_reviewer_comparison_implemented':True,'real_two_reviewer_results':None,
    'current_api_cost_usd':5.1661575,'remaining_api_cap_usd':19.8338425,
    'next_action':'Read the first purchasing calibration packet and supply full-output labels; continue the existing queue with a qualified independent reviewer.'})
print(json.dumps({'defense_pages':len(PdfReader(ROOT/'output/pdf/turing-anthropic-evidence-defense.pdf').pages),
                  'first_review_case':first,'first_packet_pages':len(PdfReader(review_pdf).pages),'transcripts':3,'human_labels_added':0}))
