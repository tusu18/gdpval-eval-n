"""Retained controlled input edits on a disposable original-output copy.

This is artifact behavior testing, not a new GDPval task or a solver rerun.
Native writer is reused. No original source or submitted artifact is changed.
"""
import json
import os
import subprocess
from pathlib import Path
from evaluation_v3_workspace import Workspace
from evaluation_v2_workspace import sha, write, SOFFICE, RUNTIME
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
TID='4520f882-715a-482d-8e87-1cb3cbdfe975'

def main():
    source=ROOT/'output/evaluation_v3/judge-packets'/TID/'artifacts/A1.xlsx'
    original_sha=sha(source)
    out=ROOT/'output/evaluation_v3/independent-checks/payroll-behavior';out.mkdir(parents=True,exist_ok=True)
    task={'task_id':'artifact-behavior-probe','references':[{'name':'Original payroll.xlsx','path':str(source),'sha256':original_sha}]}
    ws=Workspace(task,out/'native-workspace')
    cases=[('baseline',0,0),('conflict_unapproved',1,0),('conflict_approved',1,1)]
    paths=[]
    for name,quartet,approved in cases:
        reply=ws.call('write_workbook',{'filename':name+'.xlsx','content':{'template_source':'Original payroll.xlsx','sheets':[{'name':'Roster','updates':[{'cell':'G3','value':quartet}]},{'name':'Work','updates':[{'cell':'I3','value':approved}]}]}})
        if reply.get('error'):raise RuntimeError(reply['error'])
        paths.append(Path(ws.files[name+'.xlsx']['path']))
    recalc=out/'recalculated';recalc.mkdir(exist_ok=True)
    profile=(out/'soffice-profile').resolve().as_uri()
    env=os.environ.copy();env['PATH']=str(RUNTIME/'bin/override')+os.pathsep+str(RUNTIME/'bin/fallback')+os.pathsep+env.get('PATH','')
    command=[str(SOFFICE),f'-env:UserInstallation={profile}','--headless','--convert-to','xlsx','--outdir',str(recalc),*[str(p) for p in paths]]
    process=subprocess.run(command,capture_output=True,text=True,env=env,timeout=240)
    (out/'recalculation.log').write_text(process.stdout+'\n'+process.stderr)
    if process.returncode:raise RuntimeError('Native recalculation failed')
    results=[]
    for (name,quartet,approved),before in zip(cases,paths):
        path=recalc/(name+'.xlsx')
        wb=load_workbook(path,data_only=True)
        results.append({'case':name,'input_changes':{'Roster!G3':quartet,'Work!I3':approved},'unchanged_eligibility':{'Rates!B20':wb['Rates']['B20'].value},'role_status':wb['Roster']['O3'].value,'quartet_premium_usd':wb['Earnings']['J3'].value,'person_gross_usd':wb['Earnings']['M3'].value,'payroll_total_usd':wb['Payroll']['M12'].value,'before_recalculation_sha256':sha(before),'recalculated_path':str(path),'recalculated_sha256':sha(path)})
    baseline,conflict,approved=results
    result={'task_id':TID,'probe_type':'controlled edits to original submitted artifact; not new task or solver output','engine':'Bundled LibreOffice headless XLSX recalculation after artifact-tool copy/edit','original_sha256':original_sha,'original_unchanged':sha(source)==original_sha,'cases':results,'approval_only_status_change':[conflict['role_status'],approved['role_status']],'approval_only_gross_delta_usd':round(approved['person_gross_usd']-conflict['person_gross_usd'],2),'quartet_input_gross_delta_usd':round(conflict['person_gross_usd']-baseline['person_gross_usd'],2),'interpretation':'The contradictory quartet flag creates the additional calculated amount even without approval. Approval removes the role-conflict warning without changing that amount. Other workbook review flags remain. No money was paid and no error in the original saved sample payment is claimed. Expert validation remains pending.'}
    assert result['original_unchanged']
    assert conflict['unchanged_eligibility']==approved['unchanged_eligibility']=={'Rates!B20':0}
    assert conflict['role_status']=='CONFLICT: role inputs' and approved['role_status']=='OK - roles approved'
    assert result['approval_only_gross_delta_usd']==0
    write(out/'result.json',result)
    print(json.dumps(result))

if __name__=='__main__':main()
