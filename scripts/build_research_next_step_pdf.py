"""Human-readable next research decision, paired with the draft JSON protocol."""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[1]
plan = json.loads((ROOT/'output/research_next_step/protocol.draft.json').read_text())
navy = colors.HexColor('#18324a'); teal = colors.HexColor('#176d77')
styles = {k: ParagraphStyle(k, fontName='Helvetica-Bold' if k in ('title','head') else 'Helvetica',
                           fontSize=s, leading=l, textColor=navy, spaceAfter=8)
          for k,s,l in [('title',22,26),('head',12,15),('body',10,13.5),('cell',9,12),('small',8.3,11)]}
styles['head'].textColor = teal
def p(t, style='body'): return Paragraph(t, styles[style])
def table(headers, rows, widths):
    t = Table([[p('<b>'+escape(x)+'</b>','cell') for x in headers]] +
              [[p(escape(x),'cell') for x in row] for row in rows], colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce9ef')),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f4f7f9')]),
        ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),
        ('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    return t
def footer(c,d):
    c.setFont('Helvetica',8); c.setFillColor(navy)
    c.drawString(48,26,'31 October 2026 | Anthropic research discussion | Draft; no new model calls')
    c.drawRightString(A4[0]-48,26,str(d.page))

flow=[p('The next result to establish','title'),
 p('Do realistic information gaps cause consequential artifact errors, and which repair removes them?'),
 p('We have a plausible failure mechanism and an auditable pilot. The missing evidence is full-output human acceptance, validated tasks and a clean comparison under adequate tools. The next deliverable is a credible causal diagnostic, followed by a decision about whether training data is needed.'),
 table(['Priority','Work and completion evidence'],[
     ['1. Calibrate the judgments','Review the existing 20-output calibration queue, starting with its 12 purchasing cases. Record source/output evidence, uncertainty and actual minutes. Keep the two prior issue-only judgments separate. Obtain independent qualified review before claiming grader validity.'],
     ['2. Validate tasks and tools','Review corrected dates and the new three-file contract. Demonstrate that the actual file tools can produce, render/recalculate, inspect and revise a reference deliverable. Repair task or grading defects before attributing failures to a model.'],
     ['3. Run one controlled diagnostic','Compare a reference prompt and generic evidence-check prompt with identical tools, task inputs and limits. Use three selected purchasing development families, three versions and two repeats: 36 attempts for one fixed Claude configuration.'],
     ['4. Test fresh transfer','Proposed next collection: 30 permissioned families, ten development and twenty untouched evaluation. Freeze repairs before test access. Include cases where action is authorized so unnecessary holds cannot inflate success.'],
     ['5. Make the purchase decision','Select the lowest total cost per accepted deliverable among configurations meeting agreed error and utility thresholds. Expand to separate SFT/RL data only if verified failures persist.'],
 ],[123,376]), Spacer(1,10),
 p('Completed in this research pass','head'),
 p('Prepared a separate change-control candidate with SOP DOCX, blank form DOCX and tracker XLSX required consistently in prompt, metadata and rubric. All three information variants share that contract. Five regression checks pass. Original source evidence, authority and historical runs are unchanged; independent domain validation is still pending.'),
 p('This family is project management, so the repair improves study integrity but does not add purchasing coverage. The added third-file obligation prevents treating old/new scores as a causal model improvement. The native-file agent loop remains engineering work; the candidate files do not implement it.'),
 p(f'<b>Budget:</b> ${plan["budget"]["charged_or_reserved_usd"]:.2f} spent or reserved; ${plan["budget"]["remaining_cap_usd"]:.2f} remains under the $25 cap. No unresolved reservations. The proposed $6 next-stage ceiling is a planning limit, not a verified cost estimate. Human labor is unmeasured.','small'),
 PageBreak(), p('Protocol and decision rules','title'),
 p('Draft before execution. Freeze the configuration, hashes and analysis after validation; no model is selected today.'),
 p('What the experiment tests','head'),
 p('<b>Information effect:</b> compare recovery and conflict against the complete-information version within each family. <b>Prompt effect:</b> compare evidence-check and reference prompting within the same variant, model and tool setup. Average repeats within families. Report every family-level difference; three selected families do not establish population reliability.'),
 p('The development families are supplier continuity, sourcing approvals and the original landed-cost candidate. All have been inspected or authored in this project and are development-only. Do not change model, tools and prompt together and call the difference a prompt effect. A separate native-tool ablation would need its own matched comparison.'),
 table(['Endpoint','How it changes the decision'],[
     ['Acceptance','Accepted deliverables / all attempts on validated tasks. No output is not accepted; unreviewed work remains unknown. Do not choose a model from facts-only passes.'],
     ['Consequential error','Adjudicated material-error outputs / fully reviewed outputs, with no-output and unknown counts separate. Incomplete review cannot pass an error gate.'],
     ['Useful authorized work','Correct completion and unnecessary holds on prespecified eligible cases; distinguish justified holds. A safer-looking score from refusing everything is not improvement.'],
     ['Judge validity','Full confusion counts against human labels, missed errors and false accepts with denominators. No human-positive cases means error sensitivity is unmeasurable. Report taxonomy double-coding coverage.'],
     ['Total unit cost','All API, tool, retry and measured review/correction costs / accepted deliverables. Include failed attempts. With zero accepted outputs there is no finite observed unit cost.'],
 ],[123,376]), Spacer(1,10),
 p('Stop, repair or expand','head'),
 p('If independent review finds a task defect, repair and revalidate it. If prompt/tool improvements remove the target error on new families, stop the training-data pitch for that failure. If errors persist, collect verified successful trajectories and evidence-backed preferences on separate lineages. Demonstrate transfer before selling training uplift.'),
 p('Do not declare a benchmark advantage when paired effects are null or reversed. Twenty independent error-free evaluation families still leave roughly a 14% one-sided 95% upper risk bound before model-selection adjustment. Acceptance/error thresholds and the reviewer hourly rate remain unset; a pilot cannot certify rare-error reliability.'),
 p('Start here','head'),
 p('The existing human-review kit contains the complete evidence. The purchasing subset IDs are in output/research_next_step/purchasing_review_batch.json. The machine-readable protocol and remaining engineering/human gates are in the same folder. The contract candidate and blank validation form are in data/contract_repair_01/.','small'),
 p('Methodological support: <link href="https://www.anthropic.com/research/demystifying-evals-for-ai-agents" color="#176d77">Anthropic: Demystifying evals for AI agents</link> supports isolated trials, outcome-focused grading, transcript inspection and human calibration. <link href="https://arxiv.org/html/2606.09809v2" color="#176d77">Evaluation Cards</link> supports evidence reporting; documentation alone does not validate a dataset. Our numerical evidence comes from local logs.','small')]
path=ROOT/'output/pdf/turing-next-research-step.pdf'
SimpleDocTemplate(str(path),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=42,bottomMargin=44).build(flow,onFirstPage=footer,onLaterPages=footer)
print(path)
