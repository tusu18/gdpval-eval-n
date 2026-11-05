"""Package extension evidence without credentials, caches, or prior gold data."""
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/evaluation_v3'

class Links(HTMLParser):
    def __init__(self):super().__init__();self.paths=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            for key,value in attrs:
                if key=='href' and value and not re.match(r'^[a-z]+:|#',value):self.paths.append(value)

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    report=json.loads((OUT/'report.json').read_text())
    assert report['new_native_submitted_tasks']==5 and report['new_native_files']==8 and report['new_tasks_with_assessment']==5
    staging=OUT/'package-staging'
    if staging.exists():shutil.rmtree(staging)
    staging.mkdir()
    paths=[]
    for base in ('data/evaluation_v3','docs/evaluation_v3','output/evaluation_v3'):
        for p in (ROOT/base).rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(ROOT)
            if any(part in ('package-staging','packages','__pycache__','soffice-profile','lo-profile') for part in rel.parts):continue
            if p.name.startswith('process-') or p.suffix in ('.pyc','.tmp','.lock'):continue
            paths.append(p)
    paths+=list((ROOT/'config').glob('evaluation_v3*.json'))
    paths+=list((ROOT/'scripts').glob('*evaluation_v3*.py'))
    paths += [ROOT/'scripts'/n for n in ('evaluation_v2_workspace.py','evaluation_v2_engine.mjs','evaluation_v2_compat_workspace.py','run_evaluation_v2.py')]
    paths.append(ROOT/'output/evaluation_v2/report.json')
    records=[]
    secret_patterns=[rb'sk-or-v1-[a-zA-Z0-9]{32,}',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
    for p in sorted(set(paths)):
        payload=p.read_bytes()
        if any(re.search(pattern,payload) for pattern in secret_patterns):raise ValueError('Credential pattern detected; refusing package')
        dest=staging/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(payload)
        records.append({'path':str(p.relative_to(ROOT)),'original_sha256':sha(p)})
    packaged_report=staging/'output/evaluation_v3/report.html'
    packaged_report.write_text(packaged_report.read_text().replace('../evaluation_v2/report.html','../evaluation_v2/report.json').replace('Earlier report</a>','Earlier data record</a>'))
    (staging/'README.txt').write_text('''FIVE ORIGINAL GDPval TASKS — SEPARATE V3 EXTENSION

Open output/evaluation_v3/report.html for results and evidence, or output/evaluation_v3/human-review.html to record your review before consulting assessments.

Five additional original tasks across three additional occupations were executed using separate in-app agents requesting GPT-6.1 Sol. Eight native deliverables were submitted. Separate in-app agents requesting GPT-6 Astra assessed them with 43 frozen project criteria. Four tasks received provisional rubric passes; the payroll workbook has a reproduced approval/eligibility conflict and an unresolved sound-check question. No fresh human acceptance labels exist.

These are original public GDPval tasks, not a new synthetic training dataset. Controlled payroll input edits are behavior tests of an existing output, not additional original tasks or solver reruns. Original submitted files remain unchanged.

V3 is separate from the earlier 15-task OpenRouter cohort. Different host/tool/context/resource settings prevent pooling success rates or inferring an occupation/model ranking. Both requested in-app models are OpenAI-family models; this extension is not cross-family grader validation. Exact served snapshots, seeds, temperature, token usage and app inference dollar cost were not exposed. No new OpenRouter requests were made; previous known charges and unknown-charge reservations remain unchanged under $30.

This is a review evidence archive, not a self-contained inference environment. Native tools require the Codex bundled runtime/libraries. Some JSON trace paths retain their original absolute locations; corresponding files are included under the same project-relative directories. The model's full internal conversation/reasoning is not included. Native tool actions, inputs, revisions, image-display receipts, assessments and original source/output hashes are retained. Local source and native artifact files can be opened directly. The earlier evaluation is summarized by its report.json; its full evidence remains in its separate v2 archive.

Human-review entries stay in the browser until exported. A downloaded review file is not automatically submitted to the study. Record prior exposure to the analysis and your professional experience. Rubric passes, verified quotations and successful file generation do not establish expert acceptance or judge accuracy.
''')
    for name in ('report.html','human-review.html'):
        p=staging/'output/evaluation_v3'/name;parser=Links();parser.feed(p.read_text())
        missing=[v for v in parser.paths if not (p.parent/unquote(v)).resolve().exists()]
        if missing:raise ValueError('Broken packaged links: '+str(missing))
    for record in records:record['packaged_sha256']=sha(staging/record['path'])
    (staging/'PACKAGE-MANIFEST.json').write_text(json.dumps({'files':records,'file_count':len(records),'report_link_amendment':'Packaged report links to included v2 JSON summary instead of external full v2 HTML evidence. Original report and its hash retained in record.','privacy_scan':'No credential patterns found; no gold dataset columns or reference answers included.'},indent=2)+'\n')
    folder=OUT/'packages';folder.mkdir(exist_ok=True);archive=folder/'gdpval-five-task-extension-v3.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(staging.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(staging))
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('ZIP CRC failure')
        entries=len(z.namelist())
    result={'path':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),'entries':entries,'crc_pass':True,'html_links_pass':True,'credential_scan_pass':True}
    (folder/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
