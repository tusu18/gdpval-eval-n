"""Meaningful local preflight: saved OOXML features, formula updates, source/trace guards.
No solver calls, APIs, labels or professional-task answers.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile
import openpyxl
from evaluation_v4_workspace import Workspace, ROOT, sha, xlsx_audit, write

def main():
    root=ROOT/'output/evaluation_v4/preflight'/('native-capabilities'+('-'+sys.argv[1] if len(sys.argv)>1 else ''))
    if root.exists():raise SystemExit('Preflight exists; retain history and use an explicit new fixture directory for rerun.')
    root.mkdir(parents=True)
    source=root/'source.txt';source.write_text('Synthetic fixture source; not a GDPval answer.\n')
    task={'task_id':'native-capabilities','prompt':'Infrastructure fixture only','references':[{'name':'source.txt','path':str(source),'sha256':sha(source)}]}
    builder=root/'fixture.mjs';shutil.copyfile(ROOT/'scripts/evaluation_v4_native_smoke.mjs',builder)
    os.environ['OPENROUTER_API_KEY']='TEST_SENTINEL_NOT_A_REAL_CREDENTIAL'
    workspace=Workspace(task,root)
    result=workspace.call('run_builder',{'script':str(builder),'artifacts':['features.xlsx','image-document.docx'],'timeout_seconds':300})
    write(root/'smoke-result.json',result)
    if 'error' in result or any('error' in a for a in result.get('artifacts',[])):
        print(json.dumps(result,indent=2));raise SystemExit(1)
    native=workspace._current('features.xlsx')['path'];audit=xlsx_audit(native)
    counts=audit['native_feature_counts']
    for k in ('pivot_tables','pivot_caches','pivot_records','charts','auto_filters','validation_rules','print_areas'):assert counts[k]>=1,(k,counts)
    wb=openpyxl.load_workbook(native,data_only=False)
    assert len(wb['Summary']._pivots)==1
    pivot=wb['Summary']._pivots[0]
    assert pivot.cache.cacheSource.worksheetSource.ref=='A1:C5'
    assert len(pivot.cache.records.r)==4
    assert wb['Summary']['B2'].value==40 and wb['Summary']['B3'].value==60 and wb['Summary']['B4'].value==100
    assert len(wb['ByStatus']._pivots[0].rowFields)==2
    assert wb['ByStatus']['C2'].value==40 and wb['ByStatus']['C3'].value==20 and wb['ByStatus']['C4'].value==40 and wb['ByStatus']['C5'].value==100
    assert wb['Data']['F2'].value=='=E2*2'
    assert wb['Data'].page_setup.orientation=='landscape'
    wb.close()
    cached=openpyxl.load_workbook(native,data_only=True)
    assert cached['Data']['F2'].value==18;cached.close()
    docx=workspace._current('image-document.docx')['path']
    with zipfile.ZipFile(docx) as z:assert any(n.startswith('word/media/') for n in z.namelist())
    assert 'error' in workspace.call('import_artifact',{'path':str(source),'filename':'forbidden.txt'})
    assert 'error' in workspace.call('run_builder',{'script':str(ROOT/'scripts/evaluation_v4_native_smoke.mjs')})
    assert sha(source)==task['references'][0]['sha256']
    # Same task reopens with strict source and output hashes.
    workspace=Workspace(task,root)
    for event in workspace.events:assert all(k in event for k in ('request_sha256','started_at','ended_at','reply_sha256'))
    summary={'saved_native_features':counts,'dependent_formula_update':'7→14, then9→18 verified, cached18 saved',
        'pivot_cache_and_aggregates':'4 source records; East40,West60,Total100; native pivot object loads',
        'docx_embedded_image':True,'credential_environment_absent':True,'source_unchanged':True,
        'unlogged_artifact_and_outside_builder_rejected':True,'images_require_manual_display':True,
        'all_registered_revisions':{n:r['sha256'] for n,r in workspace.files.items()}}
    write(root/'test-summary.json',summary);print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
