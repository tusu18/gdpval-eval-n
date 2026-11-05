"""Build an assessment handoff with source code and portable offline evidence.

Explicit allowlists keep the complete private archive and account snapshots out
of this package. Frozen project inputs are never edited. No API is invoked.
"""
import argparse
import ast
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'output/turing-assignment-submission.zip'
SECRET=re.compile(rb'(?<![A-Za-z0-9_-])(?:sk-or-v1-[A-Za-z0-9]{32,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{48,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')
FORBIDDEN_NAMES={'account_limit_snapshot.json','model_catalog.json','.env','credentials.json','.DS_Store'}
CODE_FILES=(
 'assignment_evidence.py','reproduce_assignment.py','score_paired_pilot.py',
 'finalize_paired_results.py','run_paired_pilot.py','judge_paired_pilot.py',
 'native_file_workflow.py','native_file_engine.mjs','workflow_workspace.py',
 'evidence_grader.py','run_native_models.py','run_verified_transport_study.py',
 'run_completion_and_pairs.py','openrouter_transport_v3.mjs','openrouter_transport_v4.mjs',
 'run_request_backoff_probe.py','score_current_calibration.py','compare_human_reviews.py',
 'score_human_submission_reviews.py','build_paired_pilot.py','build_evidence_upgrade.py',
 'package_assignment_submission.py','build_assignment_submission.py','build_evaluation_record.py',
 'analyze_judge_robustness_10.py','run_judge_robustness_10.py',
 'judge_agreement.py','build_judge_controls_11.py',
 'build_measurement_update.py',
 'audit_lossless_quotes_13.py','build_strengthening_13.py','inspection_pilot_13.py','inspection_evidence_13.mjs',
 'build_judge_gap_14.py',
)
PATTERNS=(
 'output/paired_v1/runs/*.json','output/paired_v1/judgments_v3/*.json',
 'data/paired_v1/solver/*.json','output/paired_native_08/runs/*.json',
 'output/grader_checks_05/runs/*.json','reviews/assignment_final/exports/*.json',
 'reviews/assignment_final/chat_transcripts/*.json',
 'reviews/assignment_final/review_completion_*.json',
 'reviews/purchasing_calibration/responses/*-C-*.json',
 'reviews/purchasing_calibration/case-C-*-status.json',
 'reviews/purchasing_calibration/review_assignment_*-C-*.json',
 'reviews/purchasing_calibration/packets/*-C-*.pdf',
 'output/judge_robustness_10/runs/*.json','output/judge_robustness_10/packets/*.json',
 'data/judge_controls_11/**/*.json','reviews/judge_controls_11/**/*.html',
 'reviews/judge_controls_11/**/*.json','reviews/judge_controls_11/**/*.txt',
 'output/measurement_update_11/*.json','output/measurement_update_11/*.html',
 'output/judge_robustness_10/first_attempts/*.json',
 'output/strengthening_13/**/*.json','output/strengthening_13/**/*.html',
 'output/strengthening_13/inspection-evidence/**/*.png','output/strengthening_13/inspection-evidence/**/*.pdf',
 'data/agentic_judge_pilot_12/packets/*.json','reviews/agentic_judge_pilot_12/**/*',
 'reviews/inspection_pilot_13/**/*.json',
 'output/strengthening_14/judge-gap.json',
)
FIXED_INPUTS=(
 'data/paired_v1/grader/rubrics.json','data/paired_v1/selection_audit.json',
 'output/paired_v1/defect_adjudications.json','output/paired_v1/artifact_qa/page_checks.json',
 'output/paired_v1/artifact_qa/workbook_checks.json','output/paired_v1/execution_environment.json',
 'output/paired_v1/judge_protocol.v3.json','config/paired_native_08.json',
 'config/grader_checks_05.json','output/grader_checks_05/constructed_results.json',
 'output/current_study_06/paired_task_equivalence_audit.json',
 'output/current_study_06/transport_diagnostics.json',
 'reviews/assignment_final/README.txt',
 'reviews/assignment_final/REVIEW_SEQUENCE.txt',
 'reviews/purchasing_calibration/review_assignment.json',
 'config/assignment_review_minimal_v1.json',
 'config/judge_robustness_10.json','output/judge_robustness_10/audited_summary.json',
 'data/grader_challenges_02/private/author_key.json','data/grader_challenges_02/blind_packets.json',
 'output/assignment_final/evidence.json','output/assignment_final/evaluation-record.json',
 'config/judge_controls_11.proposed.json',
 'data/measurement_update_11/literature_sources.json',
 'config/agentic_judge_pilot_12.proposed.json','config/inspection_pilot_13.json',
)
LEDGERS=('paired_v1/ledger','paired_v1/judge_ledger','repair_probe_01/ledger',
 'native_workflow_01/ledger','native_transport_02/ledger','native_completion_03/ledger',
 'native_completion_07/ledger','paired_native_08/ledger','native_backoff_probe_09/ledger','grader_checks_05/ledger',
 'judge_robustness_10/ledger')


def sha(data):return hashlib.sha256(data).hexdigest()


def require_complete_robustness(root):
    """Refuse a final package while any configured request is still unfinished."""
    cfg_path=root/'config/judge_robustness_10.json'
    cfg=json.loads(cfg_path.read_text());jobs={j['id'] for j in cfg['jobs']}
    if len(jobs)!=len(cfg['jobs']):raise ValueError('Duplicate configured grader request')
    paths=list((root/'output/judge_robustness_10/runs').glob('*.json'))
    rows=[json.loads(p.read_text()) for p in paths]
    by={r['id']:r for r in rows}
    if len(by)!=len(rows):raise ValueError('Duplicate grader result identity')
    if set(by)!=jobs:raise ValueError('Grader batch has missing or unexpected request records')
    if any(r.get('status') not in ('received','execution_error') for r in rows):
        raise ValueError('Grader batch still has running or unfinished requests')
    protected=[cfg_path,root/'output/judge_robustness_10/ledger.json',*paths]
    protected += sorted((root/'output/judge_robustness_10/first_attempts').glob('*.json'))
    return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in protected}


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module


def scan(data,name):
    if SECRET.search(data):raise ValueError('Credential-like content in '+name)
    if Path(name).suffix.lower() in ('.docx','.xlsx','.pptx'):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for item in z.infolist():
                if not item.is_dir() and SECRET.search(z.read(item)):
                    raise ValueError('Credential-like content in Office member '+name+'!'+item.filename)


def redact_account_ids(data,suffix):
    """Redact provider account identifiers only, retaining a source hash map."""
    if suffix!='.json':return data,False
    value=json.loads(data);changed=False
    def visit(x):
        nonlocal changed
        if isinstance(x,dict):
            out={}
            for k,v in x.items():
                if k in ('user_id','account_id'):
                    out[k]='[ACCOUNT_ID_REMOVED]';changed=True
                else:out[k]=visit(v)
            return out
        if isinstance(x,list):return [visit(v) for v in x]
        if isinstance(x,str):
            new,n=re.subn(r'("(?:user_id|account_id)"\s*:\s*")[^"]+(\")',r'\1[ACCOUNT_ID_REMOVED]\2',x)
            changed|=bool(n);return new
        return x
    clean=visit(value)
    return (json.dumps(clean,indent=2,ensure_ascii=False)+'\n').encode() if changed else data,changed


def collect_inputs(root):
    integration=load_module(root/'scripts/assignment_evidence.py','packaged_human_evidence')
    paths={root/p for p in (*integration.BASE_INPUTS,*FIXED_INPUTS)}
    paths.update(root/('output/'+p+'.json') for p in LEDGERS)
    for pattern in PATTERNS:paths.update(root.glob(pattern))
    # The frozen robustness configuration names the exact original and injected
    # packets. Include those inputs rather than trusting a cached result table.
    robustness=json.loads((root/'config/judge_robustness_10.json').read_text())
    for job in robustness['jobs']:
        packet=(root/job['packet']).resolve()
        if not packet.is_relative_to(root.resolve()):raise ValueError('External grader packet path')
        paths.add(packet)
    # Real human imports bind reviewed source bytes. Include only the source
    # records explicitly named by an import receipt, not the entire private tree.
    for receipt in (root/'reviews/assignment_final/exports').glob('*.receipt.json'):
        item=json.loads(receipt.read_text())
        for sources in item.get('case_source_hashes',{}).values():
            for rel in sources:
                path=(root/rel).resolve()
                if not path.is_relative_to(root.resolve()):raise ValueError('External human source path')
                paths.add(path)
    for path in paths:
        if path.is_dir():continue
        if not path.is_file():raise ValueError('Missing required evidence: '+str(path.relative_to(root)))
        if path.is_symlink() or path.name in FORBIDDEN_NAMES:raise ValueError('Forbidden evidence path')
    return {p for p in paths if p.is_file()}


def build_code(root,folder):
    folder.mkdir(parents=True,exist_ok=True)
    source_map=[]
    inputs=collect_inputs(root)
    code_paths={root/'scripts'/name for name in CODE_FILES}
    # Include locally imported implementation modules for source inspection,
    # even when live execution still requires the documented native runtime.
    pending=list(code_paths)
    while pending:
        source=pending.pop()
        if source.suffix!='.py':continue
        for node in ast.walk(ast.parse(source.read_text())):
            names=([node.module] if isinstance(node,ast.ImportFrom) and node.module else
                   [x.name for x in node.names] if isinstance(node,ast.Import) else [])
            for name in names:
                candidate=root/'scripts'/(name+'.py')
                if candidate.is_file() and candidate not in code_paths:
                    code_paths.add(candidate);pending.append(candidate)
    sources=inputs|code_paths|{root/'pytest.ini'}
    sources.update(root/'tests'/name for name in ('test_assignment_evidence.py','test_assignment_packaging.py','test_judge_robustness_analysis.py','test_measurement_report.py'))
    sources.update(root/'tests'/name for name in ('test_judge_agreement.py','test_judge_controls_11.py') if (root/'tests'/name).is_file())
    sources.update(root/'tests'/name for name in ('test_lossless_quotes_13.py','test_strengthening_13.py','test_inspection_pilot_13.py'))
    sources.add(root/'tests/test_judge_gap_14.py')
    for pattern in ('test_measurement*.py','test_judge_controls*.py'):
        sources.update((root/'tests').glob(pattern))
    sources.update(root/'output/assignment_final'/name for name in ('verification.json','test-results.txt','grader-update-test-results.txt','measurement-update-test-results.txt')
                   if (root/'output/assignment_final'/name).is_file())
    for path in sorted(sources):
        if not path.is_file():raise ValueError('Missing implementation: '+str(path.relative_to(root)))
        rel=path.relative_to(root);data=path.read_bytes();clean,redacted=redact_account_ids(data,path.suffix)
        scan(clean,rel.as_posix());target=folder/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(clean)
        source_map.append({'project_path':rel.as_posix(),'source_sha256':sha(data),'packaged_sha256':sha(clean),
            'transformation':'Provider account identifier redacted; substantive evidence unchanged.' if redacted else 'byte_identical'})
    shutil.copyfile(folder/'scripts/reproduce_assignment.py',folder/'reproduce_assignment.py')
    readme='''TURING TAKE-HOME: CODE AND OFFLINE REPRODUCTION

Quick start (Python 3.10 or later; standard library only):
  python3 reproduce_assignment.py

Run that command from this code directory, or invoke this file by its absolute
path from any directory. It makes zero network/API calls. The result is written
to reproduced-results.json. You may use --output /a/chosen/path.json.

WHAT IT RECOMPUTES
Counts from the original 60 saved solver runs and 10 fixed-model extension runs;
targeted field checks from the original scoring function and private rubric;
recorded primary/secondary judge coverage; raw grader-response validity; reported
API cost for the explicitly listed study stages; the completed judge-robustness
batch's raw-valid sensitivity, judge-family and injection comparisons; and the
integrated human review record. Full label frequencies, zero-cell confusion
tables and descriptive kappa are recomputed from the saved judgments. The new
lossless quote audit and 35-flag reconciliation are separate offline diagnostics;
the inspection pilot's evidence and execution gates are checked without calls.
Pilot controls and partial human answers never become original-study findings.
Original versus packaged source hashes are explained by SOURCE_MAP.json when
provider account identifiers are redacted; substantive audit records must match.
The new
controlled-document protocol is prepared but NOT RUN; its author expectations
are not human gold. This is not a live account balance or reconciled
invoice. Robustness checks do not establish human calibration or judge accuracy.
The original 144-attempt batch remains the primary grader comparison. Five
later recovery requests are a separate supplement, preserved with the original
error records and first-attempt ledger. Both sets of recorded charges are
included once in total cost; retries never turn an original failure into a
first-attempt success. No paid calls were made to produce this update.
Saved references are checked against those independent counts. Unknown charges,
uncertain labels and missing human judgments remain explicit.

WHAT IT DOES NOT DO
It does not rerun models, render Office files, verify domain expertise, invent
human labels, resolve provider invoices, or demonstrate a training effect.
The reproduction command needs no API key. The latest recorded full-suite test
results are in output/assignment_final/test-results.txt, with timestamped-purpose
logs alongside it. This command does not rerun the entire native runtime.

IMPLEMENTATION FOR INSPECTION
scripts/ contains the historical solver, scorer and grader, the native writer,
workspace tools, transport code, and the new human-review/report integration.
config/ and data/ retain the selected evaluation setup and scoring inputs.
Some archived live native tools depend on the author's bundled Node/Python
artifact and rendering runtimes and original machine paths. They are included
for code review, not advertised as a portable live-inference environment.
Do not run legacy live runner scripts as part of offline reproduction.

HUMAN REVIEW
reviews/assignment_final/README.txt explains importing real review exports.
Only saved imports with source-bound receipts are scored. Historical issue-only
and uncertain labels never become completed binary acceptance judgments.
See evidence.json and the saved review-completion record for the fixed review's
current completion status. Completing a qualitative review does not validate
the grader, demonstrate training gains, or imply external submission.

EVIDENCE ACCESS
This code bundle is evaluation-analysis material. It contains scoring rubrics,
identity mappings and automatic grades needed for audit. Do not provide those
analysis files to a solver or an independent reviewer before their labels are
saved. Use the separately prepared blinded review packets for human calibration.
Public GDPval-derived materials are included for private take-home assessment;
this package makes no commercial redistribution or training-rights claim.
data/judge_controls_11/private contains author expectations for auditing only.
The separately copied measurement-controls review folder omits those answers.

INTEGRITY
SOURCE_MAP.json records hashes of source and packaged bytes. Provider account
identifiers in recorded error strings are redacted; source hashes make
that transformation explicit. Model outputs, outcome fields and costs are not
changed. The outer MANIFEST.json verifies all packaged entry bytes.
'''
    for name in ('README.txt','START_HERE.txt'):(folder/name).write_text(readme)
    (folder/'requirements.txt').write_text('# Offline reproduction uses Python 3.10+ standard library only.\n# Optional PDF rebuilding: reportlab>=4,<5. Native live runtime is not bundled.\n')
    (folder/'SOURCE_MAP.json').write_text(json.dumps({'scope':'Curated code and evidence for private assessment; not a blinded reviewer packet.','files':source_map},indent=2)+'\n')
    return source_map


def verify_archive(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate archive names')
        if z.testzip() is not None:raise ValueError('Archive CRC failed')
        manifest=json.loads(z.read('MANIFEST.json'))
        expected={x['path'] for x in manifest['files']}|{'MANIFEST.json'}
        if set(names)!=expected:raise ValueError('Archive entry set differs from manifest')
        for entry in manifest['files']:
            p=Path(entry['path'])
            if p.is_absolute() or '..' in p.parts or p.name in FORBIDDEN_NAMES:raise ValueError('Unsafe archive path')
            data=z.read(entry['path']);scan(data,entry['path'])
            if len(data)!=entry['bytes'] or sha(data)!=entry['sha256']:raise ValueError('Archive entry hash mismatch')
    return manifest


def package(root=ROOT,verify_reproduction=True):
    root=Path(root).resolve();submission=root/'output/assignment_final/submission';code=submission/'code'
    (submission/'START_HERE.txt').write_text('''TURING TAKE-HOME — START HERE

Read one-page.pdf for the short finding and proposed dataset pilot.
index.html presents the same overview with links to the evidence.

For a deeper review:
  evidence.html — task selection, methods, findings and limitations
  pitches-and-defense.txt — distinct Anthropic and OpenAI pitches
  supporting/ — saved result summaries and diagnostic supplements
  code/START_HERE.txt — offline reproduction instructions

The archive includes audit inputs and code so the reported counts can be
checked. These folders are supporting material, not the two-minute overview.
''')
    robustness_snapshot=require_complete_robustness(root)
    required=('index.html','one-page.pdf','pitches-and-defense.txt','evidence.json')
    for name in required:
        if not (submission/name).is_file():raise ValueError('Submission content is not ready: '+name)
    if (submission/'evidence.json').read_bytes()!=(root/'output/assignment_final/evidence.json').read_bytes():
        raise ValueError('Submission evidence is stale; rebuild the report before packaging')
    record_path=root/'output/assignment_final/evaluation-record.json'
    if (submission/'supporting/evaluation-record.json').read_bytes()!=record_path.read_bytes():
        raise ValueError('Submission evaluation record is stale; rebuild the report before packaging')
    if code.exists():shutil.rmtree(code)
    source_map=build_code(root,code)
    entries=[]
    for p in sorted(submission.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(submission).as_posix()
        if p.name=='MANIFEST.json' or '__pycache__' in p.parts or p.suffix=='.pyc':continue
        if p.is_symlink() or p.name in FORBIDDEN_NAMES or p.suffix=='.zip':raise ValueError('Uncurated content: '+rel)
        data=p.read_bytes();scan(data,rel);entries.append({'path':rel,'bytes':len(data),'sha256':sha(data)})
    evidence=json.loads((submission/'evidence.json').read_text())
    review_complete=evidence.get('readiness',{}).get('human_review_complete') is True
    manifest={'schema':'assignment-submission-package-v1','scope':'Private take-home assessment handoff. Code/evaluation analysis is not a blinded human-review packet.',
        'entrypoint':'index.html','one_page':'one-page.pdf','offline_command':'python3 code/reproduce_assignment.py',
        'human_review_complete':review_complete,
        'human_requirement':('The fixed human review and evidence-backed finding documentation are complete; external submission and live presentation have not been performed.' if review_complete else 'Manual review remains pending unless real saved labels in evidence.json demonstrate completion.'),
        'network_calls_during_packaging':0,'file_count_excluding_manifest':len(entries),'files':entries}
    (submission/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    dest=root/'output/turing-assignment-submission.zip';temp=dest.with_suffix('.zip.building')
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for e in entries:z.write(submission/e['path'],e['path'])
            z.write(submission/'MANIFEST.json','MANIFEST.json')
        verify_archive(temp)
        reproduction=None
        if verify_reproduction:
            with tempfile.TemporaryDirectory(prefix='turing-offline-check-') as directory:
                target=Path(directory)/'extracted'
                with zipfile.ZipFile(temp) as z:z.extractall(target)
                # Disable site packages: the claimed offline path must work
                # without the author's installed third-party dependencies.
                run=subprocess.run([sys.executable,'-S',str(target/'code/reproduce_assignment.py')],cwd=directory,text=True,capture_output=True,timeout=90)
                if run.returncode:raise ValueError('Portable offline reproduction failed: '+run.stderr[-1800:])
                reproduction=json.loads((target/'code/reproduced-results.json').read_text())
                if not reproduction['all_consistency_checks_pass']:raise ValueError('Reproduced evidence differs')
        if require_complete_robustness(root)!=robustness_snapshot:
            raise ValueError('Grader records changed during packaging; rebuild from a stable completed snapshot')
        temp.replace(dest)
        digest=sha(dest.read_bytes());dest.with_suffix('.zip.sha256').write_text(digest+'  '+dest.name+'\n')
        result={'archive':str(dest),'bytes':dest.stat().st_size,'entries':len(entries)+1,'sha256':digest,
            'crc_and_hashes_verified':True,'portable_offline_reproduction_passed':verify_reproduction,
            'reproduction_site_packages_disabled':verify_reproduction,
            'new_api_calls':0,'account_identifier_redactions':sum(x['transformation']!='byte_identical' for x in source_map)}
        (root/'output/assignment_final/package-verification.json').write_text(json.dumps(result,indent=2)+'\n')
        if reproduction:(root/'output/assignment_final/reproduced-results.json').write_text(json.dumps(reproduction,indent=2)+'\n')
        print(json.dumps(result));return result
    finally:
        if temp.exists():temp.unlink()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args();package(args.root)
