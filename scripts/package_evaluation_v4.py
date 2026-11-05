"""Bundle the forty-task evidence, retaining earlier cohort archives' contents."""
import hashlib
import json
import re
import zipfile
import posixpath
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/evaluation_v4'
SECRET = re.compile(rb'\bsk-(?:or-v1-)?[A-Za-z0-9_-]{32,}\b')

def digest(b): return hashlib.sha256(b).hexdigest()

class Links(HTMLParser):
    def __init__(self): super().__init__(); self.items=[]
    def handle_starttag(self, tag, attrs):
        for key,value in attrs:
            if key in ('href','src') and value: self.items.append(value)

def check_report_links(files):
    path='output/evaluation_v4/report.html'
    parser=Links();parser.feed(files[path].decode())
    missing=[];checked=0
    for link in parser.items:
        u=urlsplit(link)
        if u.scheme or u.netloc or not u.path: continue
        target=posixpath.normpath(posixpath.join(posixpath.dirname(path),unquote(u.path)))
        checked+=1
        if target not in files:
            local=ROOT/target
            if local.is_file() and local.resolve().is_relative_to(ROOT) and not local.is_symlink():
                files[target]=local.read_bytes()
            else: missing.append(target)
    if missing: raise RuntimeError('Missing report links: '+str(missing))
    return checked

def main():
    files = {}
    prior = [ROOT/'output/evaluation_v2/packages/gdpval-evaluation-v2-evidence-20261105T021640Z.zip',
             ROOT/'output/evaluation_v3/packages/gdpval-five-task-extension-v3.zip']
    provenance = []
    for index, path in enumerate(prior, 2):
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            provenance.append({'path':str(path.relative_to(ROOT)), 'sha256':digest(path.read_bytes())})
            for name in z.namelist():
                if name.endswith('/'): continue
                if name in ('README.txt','PACKAGE-MANIFEST.json'):
                    name2 = f'prior-package-notes/v{index}-{name}'
                else: name2 = name
                body = z.read(name)
                if name2 in files and files[name2] != body:
                    # Preserve the earlier full record and retain later conflicts separately.
                    files[f'prior-package-notes/conflicts/v{index}/{name2}'] = body
                    continue
                files[name2] = body
    roots = [ROOT/'data/evaluation_v4', ROOT/'docs/evaluation_v4', OUT]
    for folder in roots:
        for path in folder.rglob('*'):
            relative = path.relative_to(ROOT)
            if any(x in relative.parts for x in ('packages','node_modules','runtime-home','runtime-tmp','__pycache__')): continue
            if path.is_symlink() or not path.is_file(): continue
            if path == OUT/'package.json': continue
            if path.name.endswith(('.tmp','.lock')): continue
            files[str(relative)] = path.read_bytes()
    paths = list((ROOT/'scripts').glob('*evaluation_v4*')) + list((ROOT/'config').glob('evaluation_v4*'))
    for path in paths:
        if path.is_file(): files[str(path.relative_to(ROOT))] = path.read_bytes()
    files['README.txt'] = ('''Forty original GDPval tasks: evidence package\n\nStart with output/evaluation_v4/delivery/index.html (two-minute brief), then pitches.html and evidence.html in that folder. The full trace inventory is output/evaluation_v4/report.html. Read the separate cohort counts and limitations before interpreting results. All five public tasks in eight purposively selected occupations are retained. Earlier API and in-app results are not a matched comparison with the new native-builder/research cohort.\n\nThe package preserves original native sources, outputs, available tool/build/assessment traces, methods and hashes. It does not contain model private reasoning or a complete provider conversation transcript. In-app serving snapshots, tokens and dollar costs are unavailable. Historical human labels are not fresh labels for these outputs.\n\nExisting API confirmed charges and unresolved-charge reservations are separate; the $30 ceiling remains. New v4 OpenRouter inference cost is zero. App usage is not represented as free.\n\nSome original JSON trace paths are absolute host paths retained for provenance. Resolve paths after the original workspace prefix against this archive root. The HTML report uses relative links. Bundled runtime dependencies and inference access are not included. Never treat a schema-valid or source-quoted judge verdict as expert acceptance.\n\nEarlier package notes are preserved under prior-package-notes. No public task or rubric was replaced after seeing a new outcome.\n''').encode()
    links_checked=check_report_links(files)
    for name, body in files.items():
        if SECRET.search(body): raise RuntimeError('Credential-like content detected in '+name)
    manifest = {'created_at':datetime.now(timezone.utc).isoformat(), 'prior_archives':provenance,
                'files':{name:{'sha256':digest(body),'bytes':len(body)} for name,body in sorted(files.items())},
                'credentials_pattern_check':'passed', 'report_local_links_checked':links_checked,
                'not_a_self_contained_inference_environment':True}
    files['PACKAGE-MANIFEST.json'] = (json.dumps(manifest,indent=2)+'\n').encode()
    dest = OUT/'packages/gdpval-forty-task-evaluation-v4.zip';dest.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,body in sorted(files.items()): z.writestr(name,body)
    with zipfile.ZipFile(dest) as z: assert z.testzip() is None
    summary = {'path':str(dest),'bytes':dest.stat().st_size,'sha256':digest(dest.read_bytes()),'entries':len(files),'crc_check':'passed'}
    (OUT/'package.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))

if __name__ == '__main__': main()
