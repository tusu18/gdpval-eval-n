"""Build reviewer-only and coordinator archives, checking identity/secret leakage."""
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SECRET=re.compile(rb'sk-or-v1-[a-fA-F0-9]{20,}')
MODEL=re.compile(rb'(?:anthropic[/_]|openai[/_]|claude[-_ ]sonnet|gpt[-_ ]6\.1)',re.I)

def check_secret(name,blob):
    if SECRET.search(blob):raise RuntimeError('Credential scan failed; archive not published.')
    if name.endswith('.docx'):
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            for n in z.namelist():
                if SECRET.search(z.read(n)):raise RuntimeError('Credential scan failed in document.')

def write_archive(path,payloads,purpose,extra=None):
    for name,blob in payloads.items():check_secret(name,blob)
    manifest={'purpose':purpose,'sha256':{n:hashlib.sha256(b).hexdigest() for n,b in sorted(payloads.items())},**(extra or {})}
    contents={**payloads,'PACKAGE_MANIFEST.json':(json.dumps(manifest,indent=2)+'\n').encode()}
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,blob in sorted(contents.items()):z.writestr(name,blob)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for name,digest in manifest['sha256'].items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
    return {'file':str(path),'members':len(contents),'bytes':path.stat().st_size,'manifest_verified':True,'credential_scan_passed':True}

def main():
    reviewer_root=ROOT/'reviews/repair_probe_01/reviewer_files'
    reviewer={str(p.relative_to(reviewer_root)):p.read_bytes() for p in reviewer_root.rglob('*') if p.is_file()}
    for name,blob in reviewer.items():
        assert 'private_coordinator' not in name and not MODEL.search(name.encode())
        if name.endswith('.docx'):
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for n in z.namelist():
                    if n.endswith('.xml'):assert not MODEL.search(z.read(n)),'Model label in reviewer document'
        elif name.endswith(('.json','.txt')):assert not MODEL.search(blob),'Model label in review form'
    a=write_archive(ROOT/'output/purchasing-review-pack.zip',reviewer,'Eight prespecified anonymous first-repeat attempts for human purchasing review; no scores or coordinator identities.')
    base=ROOT/'output/turing-takehome-and-next-study.zip'
    with zipfile.ZipFile(base) as z:payloads={n:z.read(n) for n in z.namelist() if n not in ['README.md','PACKAGE_MANIFEST.json']}
    patterns=['output/repair_probe_01/**/*.json','output/repair_probe_01/**/*.docx','output/repair_probe_01/**/*.pdf','reviews/purchasing_calibration/*.json','reviews/purchasing_calibration/*.pdf','reviews/repair_probe_01/**/*.json','reviews/repair_probe_01/**/*.docx','reviews/repair_probe_01/**/*.pdf','reviews/repair_probe_01/**/*.txt','output/paired_v2/*.json','config/repair_probe_01.json','tests/test_repair_probe.py']
    patterns.extend(['data/paired_v2_1/**/*.json','tests/test_workspace_chronology.py','scripts/repair_workspace_chronology.py'])
    paths={p for pattern in patterns for p in ROOT.glob(pattern) if p.is_file()}
    paths.update(ROOT/'scripts'/n for n in ['run_repair_probe.py','render_probe_artifacts.mjs','render_probe_docs.py','score_repair_probe.py','prepare_probe_review.py','prepare_purchasing_calibration.py','build_repair_update.py','package_repair_update.py','build_paired_v2.py'])
    paths.update(ROOT/'output/pdf'/n for n in ['turing-submission-one-page.pdf','turing-repair-probe-and-pitch.pdf','purchasing-calibration-review.pdf'])
    for path in paths:payloads[str(path.relative_to(ROOT))]=path.read_bytes()
    payloads['README.md']=(ROOT/'README.md').read_bytes()
    payloads['REPAIR_PROBE_REPRODUCTION.txt']=b'''CURRENT START: output/pdf/turing-submission-one-page.pdf
CURRENT RESULTS / PITCH: output/pdf/turing-repair-probe-and-pitch.pdf

Separate studies: v1 = 60 runs, five source families, $4.391054.
repair_probe_01 = 16 runs, two selected families, $0.7751035.
Campaign total $5.1661575. Full v2 matrix has NOT run. No training.
All 16 probe attempts share a chronology defect: notes claim to copy a future
proposal. See task_defects.json. Mechanical counts are descriptive only.
data/paired_v2_1 contains a separate, unrun date correction (five instances).
No corrected-task outcome or independent task validation is asserted.
Earlier next-study PDFs/archives are pre-probe historical snapshots.

Offline scoring (no API calls): python3 scripts/score_repair_probe.py
Read output/repair_probe_01/summary.json and evaluation_card.json.
Actual cost ledger has no unresolved reservations. Inspect every raw attempt.
Do not rewrite the frozen config, runner or solver inputs to rerun this study.
The paid runner requires explicit --execute and a key read at runtime; none
is included. It enforces a $6 probe stage / $25 cumulative API limit.

Review outputs are under reviews/repair_probe_01/reviewer_files. Give only
that directory to reviewers. The separate purchasing-review-pack.zip is a
convenient copy. Do not expose the private coordinator key, model table or
raw runs until human labels are saved. The reviewer knows the hypothesis;
identity masking is not fully blind independent validation.
Copy the review-form template before filling. No new human output labels
have been supplied. Two exact user issue judgments concern old v1 cases only.
The user's qualifications, independence, reasons and minutes are undeclared.

Dependencies: offline scoring and runner tests use Python standard library.
PDF reports require reportlab; PDF inspection pypdf and Poppler. DOCX export
uses the bundled docx Node package; rendering uses the Codex documents
skill render_docx.py. Paths in render scripts reflect the authoring machine.
Saved native DOCX/PDF artifacts are included for environment-independent review.
Useful test commands: python3 -m unittest discover -s tests -p test_repair_probe.py
and python3 -m unittest discover -s tests -p test_paired_v2.py.
Generators recreate templates; preserve completed reviewer responses separately.

Private coordinator archive: source/task reuse rights are not certified.
All current scenario/template descendants are excluded from later training;
these inspected families are not an untouched test of the repair.
Provider pretraining exposure is unknown. No model has been selected.
'''
    # Existing base already redacted provider account IDs. Ensure additions do not
    # introduce account identifiers; never print their values during inspection.
    for name,blob in payloads.items():
        if name.startswith('output/repair_probe_01/') and name.endswith('.json'):
            assert b'"user_id"' not in blob and b'"api_key"' not in blob,'Sensitive identifier in new raw metadata'
    b=write_archive(ROOT/'output/turing-current-evidence-kit.zip',payloads,'Private coordinator evidence: unchanged v1, candidate v2 and separately completed repair probe.',{'base_pre_probe_archive_sha256':hashlib.sha256(base.read_bytes()).hexdigest()})
    print(json.dumps({'reviewer':a,'coordinator':b},indent=2))

if __name__=='__main__':main()
