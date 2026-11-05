"""Build author-hidden copies for a source/native-file judge; no inference."""
import argparse
import json
import shutil
from pathlib import Path
from evaluation_v2_workspace import extract_native, sha, write

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/evaluation_v3'

def copied(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and sha(target)!=sha(source):
        raise ValueError('Judge input changed after packet creation')
    if not target.exists():shutil.copyfile(source,target)
    return target

def main():
    p=argparse.ArgumentParser();p.add_argument('--task',required=True);a=p.parse_args()
    tasks=[json.loads(x) for x in (ROOT/'data/evaluation_v3/tasks.jsonl').read_text().split('\n') if x.strip()]
    matches=[t for t in tasks if t['task_id'].startswith(a.task)]
    if len(matches)!=1:raise ValueError('Ambiguous task')
    task=matches[0];tid=task['task_id'];folder=OUT/'judge-packets'/tid
    rubric_path=ROOT/'data/evaluation_v3/project-rubrics.json';rubric=json.loads(rubric_path.read_text())
    rt=next(t for t in rubric['tasks'] if t['task_id']==tid)
    submission=OUT/'solver'/tid/'submission_manifest.json'
    if not submission.exists():raise ValueError('No submission')
    artifacts=json.loads(submission.read_text())
    preflight=json.loads((OUT/'preflight'/tid/'state.json').read_text())
    sources=[];outputs=[]
    for index,ref in enumerate(task['references'],1):
        source=ROOT/ref['local_path'];id=f'S{index}';target=copied(source,folder/'sources'/f'{id}{source.suffix}')
        extraction=extract_native(target,id);write(folder/'sources'/f'{id}.json',extraction)
        views=[]
        for n,view in enumerate(preflight['source_views'].get(ref['name'],[]),1):
            dest=copied(Path(view['path']),folder/'sources'/f'{id}-view-{n}.png')
            views.append({'id':f'{id}-V{n}','path':str(dest),'label':view['label']})
        sources.append({'id':id,'original_name':ref['name'],'path':str(target),'sha256':sha(target),'extraction':str(folder/'sources'/f'{id}.json'),'views':views})
    for index,artifact in enumerate(artifacts,1):
        source=Path(artifact['path']);id=f'A{index}';target=copied(source,folder/'artifacts'/f'{id}{source.suffix}')
        extraction=extract_native(target,id);write(folder/'artifacts'/f'{id}.json',extraction)
        views=[]
        for n,view in enumerate(artifact['previews'],1):
            dest=copied(Path(view['path']),folder/'artifacts'/f'{id}-view-{n}.png')
            views.append({'id':f'{id}-V{n}','path':str(dest),'label':view['label']})
        outputs.append({'id':id,'submitted_filename':artifact['filename'],'path':str(target),'sha256':sha(target),'extraction':str(folder/'artifacts'/f'{id}.json'),'views':views})
    packet={'task_id':tid,'original_prompt':task['prompt'],'task_today':'2026-11-04','rubric_sha256':sha(rubric_path),
      'rubric':rt,'global_rules':rubric['global_rules'],'severity_scale':rubric['severity_scale'],
      'aggregation':rubric['aggregation'],'judgment_record_contract':rubric['judgment_record_contract'],
      'sources':sources,'artifacts':outputs,'model_author_identity_provided':False,'prior_grades_or_human_labels_provided':False}
    write(folder/'packet.json',packet)
    print(json.dumps({'task_id':tid,'packet':str(folder/'packet.json'),'artifacts':len(outputs),'artifact_views':sum(len(x['views']) for x in outputs)}))

if __name__=='__main__':main()
