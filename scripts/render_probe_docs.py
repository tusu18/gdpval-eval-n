"""Render experimental documents unchanged and check the requested 2-3 pages."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'output/repair_probe_01'
PY='/Users/tusu18/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
RENDER='/Users/tusu18/.codex/plugins/cache/openai-primary-runtime/documents/26.1017.22136/skills/documents/render_docx.py'
def one(path):
    rid=path.parent.name;dest=BASE/'artifact_qa/documents'/rid/path.stem
    fingerprint=hashlib.sha256(path.read_bytes()).hexdigest();marker=dest/'source.sha256'
    if not marker.exists() or marker.read_text()!=fingerprint:
        result=subprocess.run([PY,RENDER,str(path),'--output_dir',str(dest),'--emit_pdf','--dpi','90'],capture_output=True,text=True,timeout=180)
        if result.returncode:return {'run_id':rid,'filename':path.name,'status':'renderer_error','error':result.stderr[-1500:]}
        marker.write_text(fingerprint)
    pages=len(list(dest.glob('page-*.png')))
    return {'run_id':rid,'filename':path.name,'status':'rendered','pages':pages,'page_constraint_pass':2<=pages<=3,'native_sha256':fingerprint,'preview_dir':str(dest.relative_to(ROOT))}
if __name__=='__main__':
    files=list((BASE/'artifacts').rglob('*.docx'))
    with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,files))
    (BASE/'artifact_qa/page_checks.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({'documents':len(rows),'page_failures':sum(x.get('page_constraint_pass') is False for x in rows),'render_errors':sum(x['status']=='renderer_error' for x in rows)}))
