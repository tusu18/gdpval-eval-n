"""Create a complete private project handoff without API calls or cached runtimes."""
import hashlib,io,json,os,re,zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'output/Turing-Complete-Deliverable.zip'
PREFIX='Turing-Complete-Deliverable/'
SKIP_DIRS={'.git','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','node_modules','.venv','venv','.aws'}
SKIP_ROOTS={'tmp/python-deps','tmp/uv-cache'}
TEXT_EXTS={'.json','.jsonl','.txt','.md','.py','.mjs','.js','.html','.css','.yaml','.yml','.toml','.csv','.tsv','.xml','.rels','.ipynb','.sh'}
# Require a token boundary: encrypted provider reasoning can contain a random
# "sk-" substring inside a much longer opaque value.
SECRET=re.compile(rb'(?<![A-Za-z0-9_-])(?:sk-or-v1-[A-Za-z0-9]{32,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{48,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')

def digest(data):return hashlib.sha256(data).hexdigest()

def check_bytes(data,name,depth=0):
    """Inspect text and Office/archive members; print no matching secret content."""
    ext=Path(name).suffix.lower()
    if ext in TEXT_EXTS or ext in ('','.env','.pem','.key'):
        if SECRET.search(data):raise ValueError('Credential-like content detected in '+name)
    if ext in ('.zip','.docx','.xlsx','.pptx'):
        if depth>8:raise ValueError('Unexpected archive nesting in '+name)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if not info.is_dir():check_bytes(z.read(info),name+'!'+info.filename,depth+1)
    elif ext=='.pdf':
        # A binary pass catches uncompressed credentials; project PDFs contain
        # report/task content, and their structured source files are scanned too.
        if SECRET.search(data):raise ValueError('Credential-like content detected in '+name)

def main():
    excluded=[];sources=[]
    for directory,dirs,names in os.walk(ROOT,followlinks=False):
        base=Path(directory)
        for d in list(dirs):
            p=base/d;rel=p.relative_to(ROOT).as_posix()
            if p.is_symlink() or d in SKIP_DIRS or rel in SKIP_ROOTS:
                excluded.append({'path':rel,'reason':'Dependency/runtime cache, version-control metadata, or external symlink'});dirs.remove(d)
        for name in names:
            p=base/name;rel=p.relative_to(ROOT).as_posix()
            if p==DEST or name.startswith('Turing-Complete-Deliverable.zip.') or name in {'.DS_Store'} or name.endswith(('.pyc','.pyo')) or p.is_symlink():
                excluded.append({'path':rel,'reason':'Master archive itself, system metadata, bytecode, or symlink'});continue
            if name.startswith('.env') and name not in {'.env.example','.env.sample'} or name in {'credentials','credentials.json'} or p.suffix in {'.pem','.key'}:
                excluded.append({'path':rel,'reason':'Credential/configuration file excluded'});continue
            sources.append((p,'project/'+rel))
    inputs=[
        (Path('/Users/tusu18/Downloads/Field-Engineer-Take-Home-Project (1) (1).pdf'),'inputs/Field-Engineer-Take-Home-Project.pdf'),
        (Path('/Users/tusu18/.codex/attachments/926f2037-b1e8-4a97-b420-0e0117b66b72/Pasted text.txt'),'inputs/User-provided-project-feedback.txt'),
    ]
    input_status=[]
    for p,name in inputs:
        if p.is_file():sources.append((p,name));input_status.append({'archive_path':name,'status':'included'})
        else:input_status.append({'archive_path':name,'status':'not available at the supplied source path'})
    sources.append((ROOT/'output/pdf/turing-native-study-and-two-pitches.pdf','LATEST_REPORT_AND_PITCHES.pdf'))
    summary=json.loads((ROOT/'output/current_study_06/summary.json').read_text())
    verification=json.loads((ROOT/'output/current_study_06/verification.json').read_text())
    guide='''TURING - COMPLETE PROJECT DELIVERABLE
Packaged 4 November 2026 (America/New_York)

START HERE
1. Open LATEST_REPORT_AND_PITCHES.pdf for the current four-page report and the distinct Anthropic and OpenAI pitches.
2. Open project/output/submission_ready/index.html for the current local website.
3. Open project/reviews/calibration_ready_01/index.html for all 78 review cases. Start with the 20-case Calibration batch. Save and export human reviews before changing browsers or addresses.
4. Case 1's immutable sources and complete output are in project/reviews/purchasing_calibration/packets/2026-11-04-C-7424ebd2.pdf.
5. Interview preparation: project/output/current_study_06/interview-defense.txt.

WHAT IS INCLUDED
The complete project file tree: source code, tests, configurations, datasets, source/reference files, research notes, native DOCX/XLSX outputs, rendered PDFs/images, observable transcripts, run logs, cost ledgers, grading evidence, human-review records, current and historical reports, websites, and earlier packaged ZIPs. Supplied brief/feedback files are in inputs/ when available.

CURRENT EVIDENCE
All 17 previously unattempted jobs were executed: six submitted files. One additional engineering probe recovered one TLS-failed request and submitted its document. Earlier failures are preserved.
The fixed-model paired study has 10 finished attempts, five submissions and only one family with both submissions. Human acceptance and grader agreement remain unmeasured; there is no model ranking or demonstrated training gain.
Reported cumulative API cost: $36.1950216; 33 request-charge records remain unresolved. This is not a reconciled invoice.
134 automated tests passed; 15 task variants passed structural checks. These checks do not establish independent domain validity.

WHICH FILES ARE CURRENT
project/output/current_research_state.json identifies the current artifacts.
project/output/current_study_06/summary.json is the current result/cost summary.
project/output/current_study_06/evaluation_card.json records scope and limitations.
project/output/current_study_06/verification.json records the checks performed.
The project README and older reports/ZIPs are historical and can contain superseded counts, plans and budgets. Use the current files above for claims.

PACKAGE SCOPE
This is the full private working archive. It includes answer maps, automated judgments and unblinded engineering logs. For the curated submission-facing package, use project/output/turing-submission-ready.zip. Keep the private materials out of solver contexts and independent review packets.
No publication or external submission was performed. The archive does not grant additional reuse rights to source materials.

OPENING AND REPRODUCING
The reports and review website can be read without API access. Some browsers may require a local static server for embedded file previews; the supplied PDF packets remain directly readable.
Code and recorded evidence are included. Dependency caches and installed runtimes are excluded. Some native-file scripts use the original machine's bundled artifact runtime and absolute paths, so this is not a preconfigured portable runtime. The root requirements.txt belongs to the earlier preparation phase and is not a complete current environment lock.
Opening this archive does not start paid requests. Credentials are not included.

INTEGRITY
MANIFEST.json lists every included entry with byte count and SHA-256, excluding the manifest itself. EXCLUSIONS.json records intentional omissions. Archived log paths are preserved as recorded and may refer to the original workspace.
'''
    extras={'START_HERE.txt':guide.encode(),'CURRENT_STATUS.json':json.dumps({'summary':summary,'verification':verification},indent=2).encode(),
        'EXCLUSIONS.json':json.dumps({'excluded':excluded,'external_input_status':input_status},indent=2).encode()}
    entries=[];seen=set();temp=DEST.with_name(DEST.name+'.building')
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as z:
            for name,data in extras.items():
                check_bytes(data,name);z.writestr(PREFIX+name,data);seen.add(name);entries.append({'path':name,'bytes':len(data),'sha256':digest(data)})
            for p,name in sorted(sources,key=lambda x:x[1]):
                if name in seen:raise ValueError('Duplicate entry: '+name)
                data=p.read_bytes();check_bytes(data,name);z.writestr(PREFIX+name,data);seen.add(name);entries.append({'path':name,'bytes':len(data),'sha256':digest(data)})
            manifest={'schema':'complete-project-package-v1','packaged_at':datetime.now(ZoneInfo('America/New_York')).isoformat(),
                'scope':'Private complete working project plus supplied inputs; no new API calls','entries':entries,'file_count_excluding_manifest':len(entries),
                'uncompressed_bytes_excluding_manifest':sum(e['bytes'] for e in entries),'entrypoints':['START_HERE.txt','LATEST_REPORT_AND_PITCHES.pdf','project/output/submission_ready/index.html'],
                'credential_scan':'Recognizable key/private-key patterns checked in text, nested archives and Office XML; binary pass on PDFs. Not a general security certification.'}
            z.writestr(PREFIX+'MANIFEST.json',json.dumps(manifest,indent=2).encode())
        with zipfile.ZipFile(temp) as z:
            if z.testzip() is not None:raise ValueError('Archive CRC verification failed')
            if len(z.namelist())!=len(set(z.namelist())):raise ValueError('Duplicate archived paths')
            for entry in entries:
                data=z.read(PREFIX+entry['path'])
                if len(data)!=entry['bytes'] or digest(data)!=entry['sha256']:raise ValueError('Archive content verification failed: '+entry['path'])
        temp.replace(DEST)
        checksum=digest(DEST.read_bytes());DEST.with_suffix('.zip.sha256').write_text(checksum+'  '+DEST.name+'\n')
        print(json.dumps({'archive':str(DEST),'file_count':len(entries)+1,'bytes':DEST.stat().st_size,'sha256':checksum,'crc_and_all_entry_hashes_verified':True,'external_inputs':input_status,'new_api_calls':0}))
    finally:
        if temp.exists():temp.unlink()

if __name__=='__main__':main()
