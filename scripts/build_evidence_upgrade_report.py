"""Produce the current implementation brief and a local coordinator bundle."""
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/evidence_upgrade_01'
status = json.loads((OUT / 'status.json').read_text())
release = json.loads((ROOT / 'data/evidence_upgrade_01/manifest.json').read_text())
verification = json.loads((OUT / 'verification.json').read_text())
budget = status['budget']
navy = colors.HexColor('#182d40'); teal = colors.HexColor('#176d77')
styles = {name: ParagraphStyle(name, fontName='Helvetica-Bold' if name in ('title','head') else 'Helvetica',
    fontSize=size, leading=leading, textColor=navy, spaceAfter=8)
    for name,size,leading in [('title',22,26), ('head',12,16), ('body',10,14), ('cell',9,12), ('small',8.2,11)]}
styles['head'].textColor = teal


def p(text, kind='body'):
    return Paragraph(text, styles[kind])


def table(headers, rows, widths):
    t = Table([[p('<b>' + escape(x) + '</b>', 'cell') for x in headers]] +
              [[p(escape(str(x)), 'cell') for x in row] for row in rows], colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dce9ef')),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f2f6f8')]),
        ('VALIGN',(0,0),(-1,-1),'TOP'), ('LEFTPADDING',(0,0),(-1,-1),8),
        ('RIGHTPADDING',(0,0),(-1,-1),8), ('TOPPADDING',(0,0),(-1,-1),7),
        ('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    return t


def footer(canvas, doc):
    canvas.setFillColor(navy); canvas.setFont('Helvetica',8)
    canvas.drawString(48,26,'3 November 2026 | Anthropic research discussion | Development evidence')
    canvas.drawRightString(A4[0]-48,26,str(doc.page))


flow = [p('Evidence before a model claim', 'title'),
    p('<b>Anthropic pitch:</b> evaluate whether an agent produces a supportable professional decision when facts are missing, sources conflict, or an action lacks approval. The product offer is a private, freshly sourced evaluation set with auditable failures and calibrated graders.'),
    p('This implementation strengthens the diagnostic foundation. It does not yet establish a model ranking, expert acceptance, training uplift or a benchmark advantage.'),
    table(['Implemented','Evidence and scope'],[
        ['Evidence maps','15 variants across five selected development families; 87 criterion records link source quotations and hashes to business requirements and deliverable locations. Three families are purchasing. Maps are excluded from solver inputs.'],
        ['Task repairs','Preserved earlier chronology and three-file repairs. Added a fixed scenario clock, removed the remaining completed-versus-blank form conflict, and corrected the delivery log authority chronology. No missing inventory or new approval was invented.'],
        ['Grader checks','Reads submitted DOCX/XLSX content; requires complete criterion coverage and exact source/output quotations. Separates task defects, unknowns, missing files, content judgments and native rendering checks. Critical failures cannot be averaged away.'],
        ['Challenge suite','36 constructed fixtures in nine families: a supported answer, a faulty answer, an unchanged control and a cosmetic control per family. Added numeric, freight-unit and cross-file approval errors. Zero judge runs and zero human-validated challenge labels.'],
    ],[109,390]), Spacer(1,11),
    p('What can be claimed today', 'head'),
    p(f'<b>{verification["tests_passed"]} project tests pass</b>, including {verification["new_tests"]} new tests. All 15 candidate maps pass source/contract checks. {status["historical_files_checked"]} protected historical records retain their original hashes. These are engineering results, not estimates of model accuracy.'),
    p(f'<b>Budget:</b> ${budget["charged_or_reserved_usd"]:.7f} recorded API spend; ${budget["remaining_cap_usd"]:.7f} remains under the $25 total cap. New API spend: $0. No unresolved reservations. Human review and correction labor are still unmeasured.'),
    p('Human evidence remains two issue-only material-correction judgments and one partial case with uncertain usability/error labels. There are zero completed full-output reviews. Do not call the current acceptance or grader sensitivity expert-validated.', 'small'),
    PageBreak(), p('How evidence reaches a decision', 'title'),
    p('Worked example: original supplier landed-cost family. This is the author reference logic, not a new model result.'),
    table(['Link','Evidence map'],[
        ['Professional objective','Recommend a qualified supplier for 500 enclosures by project day 17. Do not place an order.'],
        ['Authority','A2 approved on 19 October: Alder freight $2,600 per order. A3 dated 22 October proposes $1,200 but is unconfirmed and unapproved. Scenario date: 23 October; A2 valid until 5 November.'],
        ['Recovery route','Search/read the workspace decision register and approved record. Recovery starts without freight in the brief; conflict starts with the forwarded $1,200 estimate. The same workspace is available in every version.'],
        ['Derivation','Alder: 500 x $42 + $2,600 = $23,600. Beacon: 500 x $46 = $23,000. Both meet the deadline; Beacon saves $600 at approved prices.'],
        ['Artifact checks','Inspect the comparison table, executive recommendation, conditions and citations together. A correct audit field cannot rescue a $22,600 total or an unapproved supplier recommendation in the actual memo.'],
        ['Limits','Original assistant-authored fictional family; independent domain validation and rights attestation are pending. All variants belong to one development family, not three independent observations.'],
    ],[109,390]), Spacer(1,10),
    p('Task repair boundaries', 'head'),
    p('<b>Supplier continuity:</b> day 0 is explicit; the 21-day cutoff is unchanged. Starting stock and negotiated extensions remain unknown. <b>Sourcing:</b> Finance, Program and Purchase remain mandatory across exception paths. <b>Change control:</b> one SOP DOCX, one blank-form DOCX and one tracker XLSX are explicit. <b>Delivery:</b> the log directs a real scripted clarification; it does not itself grant an appointment.'),
    p('Old runs remain historical diagnostics. New task wording, contracts or sources require new execution. The 15 candidates do not expand the underlying study to 15 independent families. Three other existing families are outside this release.', 'small'),
    p('Research translated into implementation', 'head'),
    p('<link href="https://www.alphaxiv.org/pdf/2610.37161" color="#176d77">WorkFactory</link>: dependency/evidence maps and bounded repairs. '
      '<link href="https://arxiv.org/pdf/2611.03412" color="#176d77">DeliverBench</link>: check the whole artifact package and cross-file consistency. '
      '<link href="https://arxiv.org/html/2609.38923v3" color="#176d77">GraphForge</link>: test subtle numeric/citation mutations, not just conspicuous omissions. '
      'These inform design; their reported performance is not evidence for our system.', 'small'),
    PageBreak(), p('Validate the judge before selling it', 'title'),
    p('The new code verifies evidence provenance and enforces decision rules. A quotation can be real while the judge interprets it incorrectly. That is why human-grounded calibration remains the next evidence gate.'),
    table(['Metric','Decision use and denominator'],[
        ['Human acceptance','Accepted without substantive correction / all prespecified attempts on validated tasks. Keep unreviewed and uncertain outputs visible; report their effect on the bounds. Never replace human labels with automatic passes.'],
        ['Consequential error','Confirmed consequential-error outputs / fully adjudicated outputs, with no-output, unknown and task-defect counts separate. Critical business errors outrank presentation quality.'],
        ['Judge misses','Human-confirmed errors the judge misses / human-confirmed errors with comparable judge labels. With no positive human cases, sensitivity is unmeasurable.'],
        ['False accepts','Judge-accepted outputs rejected by the human / judge-accepted outputs with comparable human labels. Report false alarms on supported and cosmetic controls separately.'],
        ['Useful completion','Track unjustified holds in cases with sufficient facts and authorization. Refusing everything must not create a misleading safety score.'],
        ['Total unit cost','All generation, judging, tool/retry and measured human review/correction costs / accepted deliverables. Zero accepted outputs gives no finite observed unit cost.'],
    ],[109,390]), Spacer(1,10),
    p('The next execution order', 'head'),
    p('1. Review the five task maps and challenge constructions; finish full-output calibration with source/output evidence and actual minutes. Keep expertise and independence unspecified until documented.'),
    p('2. Complete the native file create/render/recalculate/inspect/revise loop. The new extractor is a grader component; it does not repair the solver tool setup or prove files render correctly.'),
    p('3. Price a small solver-and-judge smoke test, then freeze matched prompts, tools and limits. Prefer more distinct task families before repeats. Keep diagnostic error hunting separate from the random sample used for headline rates; analyze uncertainty by source family.'),
    p('4. Collect fresh, permissioned held-out families before making a selection claim. Select the lowest total cost per accepted deliverable meeting agreed error and acceptance thresholds. Use separate SFT/RL lineages only if verified failures persist after prompt/tool repair.'),
    p('No paid experiment is launched by this package. The old unexecuted 36-attempt proposal is superseded by measured-cost sizing and more distinct families before repeats. A third judge adds diversity, not ground truth; same-family self-preference and shared errors still require human checks.', 'small'),
    p('<link href="https://arxiv.org/html/2606.09809v2" color="#176d77">Evaluation Cards</link> guides this evidence record. Good documentation does not substitute for rigorous evaluation.', 'small')]

pdf = ROOT / 'output/pdf/turing-anthropic-evidence-upgrade.pdf'
pdf.parent.mkdir(parents=True, exist_ok=True)
SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=42, bottomMargin=44).build(flow, onFirstPage=footer, onLaterPages=footer)

instructions = {
    'purpose': 'Local coordinator kit for evidence maps, repaired development tasks and grader checks. Contains private author expectations; do not upload the complete kit as solver or blinded-judge context.',
    'current_brief': str(pdf.relative_to(ROOT)),
    'task_release': 'data/evidence_upgrade_01', 'grader_challenges': 'data/grader_challenges_02',
    'commands': [
        'python3 scripts/check_evidence_upgrade.py',
        'python3 -m unittest discover -s tests -v',
        'python3 scripts/evidence_grader.py prepare --task data/evidence_upgrade_01/solver/original_supplier_landed_cost__conflict.json --maps data/evidence_upgrade_01/grader/evidence_maps.json --artifacts PATH_TO_SUBMITTED_FILES --out PATH_TO_PACKET.json',
        'python3 scripts/evidence_grader.py score --packet PATH_TO_PACKET.json --judgment PATH_TO_JUDGE_RESPONSE.json --out PATH_TO_SCORE.json'],
    'run_policy': 'No automatic API calls. Future stages must use all three historical ledgers, campaign lock, price bounds and readiness checks. Reservation cap includes solver and judge calls.',
    'protocol_update': 'The previous unexecuted 36-attempt proposal is superseded: measure smoke-test cost, then prioritize distinct families before repeats within the remaining campaign cap.',
    'separation': {'solver': 'Only solver task request, attachments and allowlisted workspace tool replies.',
                   'judge': 'Native-artifact packet plus relevant private evidence map; omit solver identity, fact-audit answer, challenge key and pair/member metadata.',
                   'human': 'Full sources and native deliverables; independent first-pass labels before exposing automatic grades.',
                   'training': 'None of these inspected development families is untouched evaluation or training data.'},
    'limitations': status['remaining_work']}
(OUT / 'usage.json').write_text(json.dumps(instructions, indent=2) + '\n')

paths = list((ROOT / 'data/evidence_upgrade_01').rglob('*.json')) + list((ROOT / 'data/grader_challenges_02').rglob('*.json'))
paths += [ROOT / 'scripts' / name for name in ('build_evidence_upgrade.py','evidence_grader.py',
    'build_grader_challenges_v2.py','check_evidence_upgrade.py','build_evidence_upgrade_report.py',
    'prepare_contract_repair.py','repair_workspace_chronology.py','workflow_workspace.py',
    'prepare_grader_challenges.py','run_repair_probe.py')]
paths += [ROOT / 'tests/test_evidence_upgrade.py', pdf] + [p for p in OUT.glob('*.json') if p.name != 'package_manifest.json']
paths += [OUT / 'test-results.txt', ROOT / 'output/current_research_state.json']
paths += [ROOT / 'output/research_next_step/literature_review_2026-11-03.json']
manifest = {'file_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
            'scope': 'Implementation and review materials. Historical ledgers/source snapshots stay in the project; this is not a standalone reproduction of the original campaign.'}
(OUT / 'package_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
bundle = ROOT / 'output/turing-evidence-upgrade-kit.zip'
with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in sorted(set(paths + [OUT / 'package_manifest.json'])):
        z.write(path, str(path.relative_to(ROOT)))
print(json.dumps({'brief': str(pdf), 'bundle': str(bundle), 'files': len(set(paths)) + 1}))
