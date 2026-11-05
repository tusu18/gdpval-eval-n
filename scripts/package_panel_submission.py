"""Package current private submission and a separate identity-masked review kit."""
import io
import json
from pathlib import Path
import re
import zipfile
from package_repair_update import write_archive

ROOT=Path(__file__).resolve().parents[1]
MODEL=re.compile(rb'(?:anthropic[/_]|openai[/_]|claude[-_ ]sonnet|gpt[-_ ]6\.1)',re.I)
def main():
    review={}
    for p in (ROOT/'site/review').rglob('*'):
        if p.is_file():review['review/'+str(p.relative_to(ROOT/'site/review'))]=p.read_bytes()
    for name,blob in review.items():
        if name.endswith(('.js','.json')):assert not MODEL.search(blob),'Explicit model label leaked into review data'
        if name.endswith('.docx'):
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for n in z.namelist():
                    if n.endswith('.xml'):assert not MODEL.search(z.read(n)),'Model identity in review document'
    review['index.html']=b'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Turing human review</title><body style="font:18px/1.6 system-ui;max-width:780px;margin:50px auto;padding:20px"><h1>Your evidence review</h1><p>Open the calibration queue first. It contains 20 valid outputs, with models and prior judge labels omitted. Then review the 35 flagged attempts for the taxonomy. There are 43 distinct attempts because the queues overlap.</p><p><a href="review/index.html?queue=purchasing">Start with the 12 purchasing calibration cases</a> or <a href="first-case.pdf">read the complete first case as a PDF</a></p><p>Read the complete task and native files. Supply only your own judgments, actual minutes and source/output evidence. Uncertain and task-defect labels are allowed. The two earlier purchasing judgments concern specific issues and are not completed output reviews.</p><p>Export the JSON when finished. This app saves locally; it does not submit data or call a model. Keep the exported file. To obtain a second reviewer, send this kit without the main study report, panel assessments, coordinator mapping or prior judge scores. The study hypothesis may be known; this is identity masking, not a guarantee of full blinding.</p></body></html>'''
    review['first-case.pdf']=(ROOT/'output/pdf/purchasing-calibration-first-case.pdf').read_bytes()
    review['REVIEW-INSTRUCTIONS.txt']=b'''Extract the ZIP before opening index.html. Open the calibration queue first.
20 calibration outputs + 35 taxonomy candidates = 43 distinct attempts.
Model identity, prior judge labels and coordinator mapping are omitted.
Task evidence and complete observable final outputs are preserved.
Raw transcripts omit provider-internal reasoning and account metadata.
Review labels are initially empty. Record role, evidence and actual minutes.
Export turing-human-reviews.json and return it to the project owner.
The investigator has already seen model results; this is not fully blind review.
Use a second qualified reviewer before claiming inter-rater reliability.
'''
    reviewer_result=write_archive(ROOT/'output/turing-human-review-kit.zip',review,'Human review only; 43 identity-masked attempts, no coordinator mapping or previous grader labels.')
    base=ROOT/'output/turing-current-evidence-kit.zip'
    with zipfile.ZipFile(base) as z:payloads={n:z.read(n) for n in z.namelist() if n not in ['README.md','PACKAGE_MANIFEST.json']}
    paths=set()
    for pattern in ['output/submission_audit/*.json','output/panel_review/*.json','site/**/*.html','site/**/*.js','site/review/files/**/*','config/native_file_control.proposed.json','tests/test_human_submission_reviews.py','reviews/purchasing_calibration/review_assignment.json','output/research_next_step/*.json','data/contract_repair_01/**/*.json','tests/test_contract_repair.py','output/anthropic_defense/**/*','data/grader_challenges_01/*.json','tests/test_compare_human_reviews.py','tests/test_grader_challenges.py']:
        paths.update(p for p in ROOT.glob(pattern) if p.is_file())
    paths.update(ROOT/'scripts'/n for n in ['prepare_submission_review.py','score_human_submission_reviews.py','build_panel_submission.py','build_evidence_site.py','package_panel_submission.py','prepare_contract_repair.py','prepare_research_next_step.py','build_research_next_step_pdf.py','compare_human_reviews.py','prepare_grader_challenges.py','build_anthropic_defense.py'])
    paths.update(ROOT/'output/pdf'/n for n in ['turing-submission-one-page.pdf','turing-panel-review-and-pitches.pdf','turing-anthropic-pitch.pdf','turing-next-research-step.pdf','turing-anthropic-evidence-defense.pdf','purchasing-calibration-first-case.pdf'])
    for p in paths:payloads[str(p.relative_to(ROOT))]=p.read_bytes()
    payloads['README.md']=(ROOT/'README.md').read_bytes()
    payloads['PANEL-HANDOFF.txt']=b'''Primary audience: Anthropic (user-confirmed; not a reviewer affiliation).
Current evidence defense: output/pdf/turing-anthropic-evidence-defense.pdf
Start: output/pdf/turing-anthropic-pitch.pdf
One-page submission: output/pdf/turing-submission-one-page.pdf
Full audit and two distinct researcher pitches: output/pdf/turing-panel-review-and-pitches.pdf
Next research work: output/pdf/turing-next-research-step.pdf
Unrun contract candidate: data/contract_repair_01/manifest.json
Current local website: site/index.html
Human review: site/review/index.html (or separate turing-human-review-kit.zip)
Two independent AI reviews: output/panel_review/*.json (not human/lab endorsements).

No new API calls in this revision. Campaign cost remains USD 5.1661575.
35 candidate taxonomy assignments are not human-confirmed model failures.
Only two prior user issue labels exist; full-output labels remain unmeasured.
Ten of twelve model-judge critical agreements were all shared negatives.
New tracker/output-count scope conflict affects the 12 change-control attempts.
Original results are preserved; no replacement performance is imputed.

After human review: python3 scripts/score_human_submission_reviews.py <export.json>
This writes a new summary without changing frozen inputs or old scores.
Two reviewers: python3 scripts/compare_human_reviews.py first.json second.json
Tests: python3 -m unittest discover -s tests -p test_human_submission_reviews.py
Task-family, expert, rights and customer-threshold validation remain pending.

Native-file control and fresh private-data plan are UNRUN PROPOSALS.
The $391.11-per-family figure is illustrative economics, not a measured rate.
No SFT/RL, external submission, message or public publication was performed.
The static page can open locally; links expect this directory structure.
This PRIVATE coordinator kit contains model identities and judge opinions;
do not give it to reviewers before collecting their independent labels.
'''
    coordinator_result=write_archive(ROOT/'output/turing-panel-submission-kit.zip',payloads,'Private revised submission, source evidence, code, audit and separate pending human reviews.')
    defense={str(p.relative_to(ROOT/'output/anthropic_defense')):p.read_bytes() for p in (ROOT/'output/anthropic_defense').rglob('*') if p.is_file()}
    defense['START-HERE.pdf']=(ROOT/'output/pdf/turing-anthropic-evidence-defense.pdf').read_bytes()
    for p in (ROOT/'data/grader_challenges_01').glob('*.json'):defense['constructed-grader-checks/'+p.name]=p.read_bytes()
    defense['READ-ME.txt']=b'Private coordinator evidence, not a blinded human-review kit. Three full observable transcripts and native files come from one source family. Prior case commentary is included. Constructed grader checks are assistant-authored, unvalidated and unrun; no judge reliability or training benefit is established. Use the separate turing-human-review-kit.zip for independent labels. API cost remains USD 5.1661575.\n'
    defense_result=write_archive(ROOT/'output/turing-anthropic-defense-kit.zip',defense,'Private Anthropic evidence defense; three actual traces, native outputs and unrun constructed grader checks.')
    print(json.dumps({'reviewer':reviewer_result,'coordinator':coordinator_result,'defense':defense_result},indent=2))

if __name__=='__main__':main()
