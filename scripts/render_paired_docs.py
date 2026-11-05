"""Render unchanged experimental DOCX outputs and measure page constraints."""
import concurrent.futures,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'output/paired_v1'
PY='/Users/tusu18/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
RENDER='/Users/tusu18/.codex/plugins/cache/openai-primary-runtime/documents/26.1017.22136/skills/documents/render_docx.py'
def one(p):
    rid=p.parent.name;dest=BASE/'artifact_qa'/'documents'/rid/p.stem
    if not list(dest.glob('page-*.png')):
        r=subprocess.run([PY,RENDER,str(p),'--output_dir',str(dest),'--emit_pdf','--dpi','90'],capture_output=True,text=True,timeout=180)
        if r.returncode:return {'run_id':rid,'filename':p.name,'status':'renderer_error','error':r.stderr[-1200:]}
    pages=len(list(dest.glob('page-*.png')))
    bounded=rid.startswith(('sourcing_approvals__','supplier_exit__','ev_localization__'))
    return {'run_id':rid,'filename':p.name,'status':'rendered','pages':pages,'source_page_min':2 if bounded else None,'source_page_max':3 if bounded else None,'page_constraint_pass':2<=pages<=3 if bounded else None,'preview_dir':str(dest.relative_to(ROOT))}
if __name__=='__main__':
    paths=list((BASE/'artifacts').rglob('*.docx'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(one,paths))
    (BASE/'artifact_qa'/'page_checks.json').write_text(json.dumps(rows,indent=2))
    print(json.dumps({'documents':len(rows),'page_failures':sum(r.get('page_constraint_pass') is False for r in rows),'render_errors':sum(r['status']=='renderer_error' for r in rows)}))
