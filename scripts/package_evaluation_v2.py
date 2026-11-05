"""Prepare portable public evidence and a separate blind-review package.

Default is staging only. --finalize additionally makes new version-specific ZIPs
after checking no paid dispatch is in progress. No API calls, no old ZIP edits.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime,timezone
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import unquote,urlparse
import uuid
import zipfile

import report_evaluation_v2 as report

ROOT=Path(__file__).resolve().parents[1]
TEXT_EXT={'.json','.jsonl','.ndjson','.html','.txt','.md','.py','.mjs','.js','.csv','.log','.yaml','.yml','.toml'}
NATIVE_EXT={'.docx','.xlsx','.pptx','.pdf','.png','.jpg','.jpeg','.webp','.svg'}
SECRET_PATTERNS=[r'sk-or-v1-[A-Za-z0-9_-]{16,}',r'(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{24,}',r'gh[pousr]_[A-Za-z0-9]{25,}',r'AKIA[A-Z0-9]{16}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'(?i)Authorization\s*[:=]\s*["\x27]?Bearer\s+[A-Za-z0-9_.-]{16,}']
PRIVATE_KEYS={'authorization','api_key','apikey','x-api-key','access_token','refresh_token','cookie','set-cookie','user_id','reviewer','reviewer_name','reviewer_identity','reviewer_experience'}
OMITTED_REASONING={'reasoning_details','encrypted_content','chain_of_thought'}

def digest_bytes(value):return hashlib.sha256(value).hexdigest()
def skip_path(path,base):
    rel=path.relative_to(base);parts=rel.parts;name=path.name.lower()
    if any(x in ('node_modules','__pycache__','.git','package-staging','packages') for x in parts):return True
    if '.private.' in name or 'private-key' in name or 'private_key' in name or name.startswith('.env') or name.endswith(('.lock','.tmp','.pyc')):return True
    if any(x in name for x in ('credential','secret-key','api-key','api_key','key-file')):return True
    return False

class Sanitizer:
    def __init__(self,root):self.root=Path(root).resolve();self.counts={};self.patterns=[re.compile(p) for p in SECRET_PATTERNS]
    def count(self,key):self.counts[key]=self.counts.get(key,0)+1
    def string(self,value):
        if value.startswith('data:image/') and ';base64,' in value:
            self.count('image_payload_omitted');return '[LOCAL IMAGE PAYLOAD OMITTED; SHA256 '+digest_bytes(value.encode())+'; characters '+str(len(value))+']'
        result=value.replace(str(self.root),'[PROJECT_ROOT]')
        result=result.replace(str(Path.home()),'[LOCAL_HOME]')
        if result!=value:self.count('local_path_rewritten')
        for pattern in self.patterns:
            result,n=pattern.subn('[REDACTED CREDENTIAL]',result)
            if n:self.count('credential_pattern_redacted')
        return result
    def value(self,value):
        if isinstance(value,list):
            result=[]
            for item in value:
                if isinstance(item,dict) and item.get('type')=='reasoning':self.count('private_reasoning_omitted');continue
                result.append(self.value(item))
            return result
        if isinstance(value,dict):
            result={}
            for key,item in value.items():
                public_key=self.string(key)
                if key.lower() in PRIVATE_KEYS:
                    self.count('private_field_redacted');result[public_key]=None;continue
                if key in OMITTED_REASONING or (key=='reasoning' and isinstance(item,str)):
                    self.count('private_reasoning_omitted');continue
                if key=='body' and isinstance(item,str):
                    try:result[public_key]=json.dumps(self.value(json.loads(item)),ensure_ascii=False);continue
                    except (ValueError,TypeError):pass
                result[public_key]=self.value(item)
            return result
        if isinstance(value,str):return self.string(value)
        return value
    def file_bytes(self,path):
        raw=path.read_bytes()
        if path.suffix.lower() not in TEXT_EXT:return raw,False
        text=raw.decode('utf-8',errors='replace')
        try:
            if path.suffix=='.json':text=json.dumps(self.value(json.loads(text)),indent=2,ensure_ascii=False)+'\n'
            elif path.suffix in ('.jsonl','.ndjson'):text='\n'.join(json.dumps(self.value(json.loads(line)),ensure_ascii=False) for line in text.splitlines() if line.strip())+'\n'
            else:raise ValueError('ordinary text')
        except ValueError:
            if path.suffix=='.log':
                text='\n'.join(line if len(line)<=1800 else '[LONG ENGINE DIAGNOSTIC LINE OMITTED; SHA256 '+digest_bytes(line.encode())+'; characters '+str(len(line))+']' for line in text.splitlines())
            text=self.string(text)
        data=text.encode();return data,data!=raw

def selected_files(root):
    files=set()
    for base in (root/'data/evaluation_v2',root/'docs/evaluation_v2',root/'output/evaluation_v2',root/'reviews/evaluation_v2'):
        if base.exists():files.update(p for p in base.rglob('*') if p.is_file() and not skip_path(p,base) and p.suffix.lower() in TEXT_EXT|NATIVE_EXT)
    for directory,pattern in (('config','evaluation_v2*.json'),('scripts','*evaluation_v2*'),('tests','*evaluation_v2*')):
        files.update(p for p in (root/directory).glob(pattern) if p.is_file() and p.suffix.lower() in TEXT_EXT and not skip_path(p,root))
    for relative in ('research/reference_manifest.json','data/gdpval/manifest.json','data/gdpval/task_selection.csv'):
        if (root/relative).is_file():files.add(root/relative)
    tasks=report.lines(root/'data/evaluation_v2/effective-inputs.jsonl') or report.lines(root/'data/evaluation_v2/tasks.jsonl')
    for task in tasks:
        for ref in task.get('references',[]):
            value=ref.get('path') or ref.get('local_path')
            if value:
                path=report.rooted(root,value)
                if path.is_file():files.add(path)
    return sorted(files)

class LinkParser(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ('href','src') and value:self.links.append(value)

def validate_package(folder):
    folder=Path(folder).resolve();broken=[];leaks=[];private=[];archived_web=[];patterns=[re.compile(x) for x in SECRET_PATTERNS]
    for path in folder.rglob('*'):
        if not path.is_file():continue
        rel=str(path.relative_to(folder))
        if skip_path(path,folder):private.append(rel)
        parts=[]
        if path.suffix.lower() in TEXT_EXT:parts=[path.read_text(errors='replace')]
        elif path.suffix.lower() in ('.docx','.xlsx','.pptx'):
            with zipfile.ZipFile(path) as z:parts=[z.read(n).decode('utf-8',errors='replace') for n in z.namelist() if n.endswith(('.xml','.rels'))]
        for text in parts:
            if any(p.search(text) for p in patterns):leaks.append(rel+':credential_pattern')
            if path.suffix.lower() in TEXT_EXT and re.search(r'/Users/[A-Za-z0-9._-]+/',text):leaks.append(rel+':local_user_path')
        if path.suffix=='.html':
            if 'external_sources' in path.parts:
                archived_web.append(rel);continue
            parser=LinkParser();parser.feed(parts[0])
            for value in parser.links:
                parsed=urlparse(value)
                if parsed.scheme or parsed.netloc or value.startswith('#'):continue
                target=(path.parent/unquote(parsed.path)).resolve()
                if not target.is_relative_to(folder) or not target.exists():broken.append({'file':rel,'link':value})
    return {'portable_local_links_valid':not broken,'broken_links':broken,'archived_web_snapshots_excluded_from_app_link_check':archived_web,'archived_web_note':'Cached source HTML retains original website links and external assets. It is evidence, not a bundled website; offline text/PDF extracts are supplied separately.','credential_and_local_identity_scan_pass':not leaks,'scan_findings':sorted(set(leaks)),'private_file_exclusion_pass':not private,'private_files':private}

def blank_private_fields(payload):
    payload=copy.deepcopy(payload)
    for case in payload.get('cases',[]):
        # Review packages start blank; they never export prior reviewer identity
        # or transfer historical labels into a new prospective review.
        case['review']={key:None for key in case.get('review',{})}
    return payload

def primary_blind_payload(root):
    payload=blank_private_fields(report.read(root/'reviews/evaluation_v2/human-reviews.json',{'cases':[]}))
    private=report.read(root/'output/evaluation_v2/review-private-key.json',{'case_map':{}})
    primary_model=report.read(root/'config/evaluation_v2_run.json',{}).get('primary_model')
    selected=set(report.read(root/'config/evaluation_v2_grader.json',{}).get('human_validation',{}).get('selected_task_ids',[]))
    ids={m['case_id'] for m in private['case_map'].values() if m.get('model')==primary_model and m.get('task_id') in selected}
    payload['cases']=[c for c in payload['cases'] if c['case_id'] in ids]
    payload['selection']='Nine prespecified primary-study task slots, three per occupation. Failed or unavailable primary deliverables remain in their original slots and are not replaced by recoveries.'
    return payload

def stage_blind(root,folder,include_recovery=False):
    folder.mkdir(parents=True,exist_ok=True);payload=primary_blind_payload(root)
    for case in payload['cases']:
        for group in ('sources','artifacts','renders'):
            for item in case.get(group,[]):
                source=report.rooted(root,item['path']);dest=folder/'cases'/case['case_id']/source.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);item['path']=str(dest)
    sanitizer=Sanitizer(root);portable=copy.deepcopy(payload)
    for case in portable['cases']:
        for group in ('sources','artifacts','renders'):
            for item in case.get(group,[]):item['path']=str(Path(item['path']).relative_to(folder))
    report.write(folder/'human-reviews.json',portable)
    html=report.review_html(payload,folder).replace(str(folder),'[REVIEW_PACKAGE_ROOT]')
    (folder/'index.html').write_text(sanitizer.string(html))
    extras=[]
    if include_recovery:
        r=report.read(root/'output/evaluation_v2/report.json',{})
        private_path=root/'output/evaluation_v2/review-private-key.json';private=report.read(private_path,{'case_map':{},'salt':uuid.uuid4().hex});recovery_map=private.setdefault('optional_recovery_map',{})
        tasks={t['task_id']:t for t in report.lines(root/'data/evaluation_v2/effective-inputs.jsonl')}
        for run in r.get('recovery_runs',[]):
            if run.get('status')!='submitted':continue
            task=tasks.get(run['task_id'],{});cid=recovery_map.setdefault(run['run_id'],'X-'+hashlib.sha256((private['salt']+'|optional|'+run['run_id']).encode()).hexdigest()[:10])
            case={'case_id':cid,'task_id':run['task_id'],'occupation':run.get('occupation'),'prompt':task.get('prompt',''),'status':'ready_for_review','review_scope':'optional recovery diagnostic, excluded from the primary sample','sources':[],'artifacts':[],'renders':[],'review':{k:None for k in payload['cases'][0]['review']} if payload['cases'] else {}}
            if run['task_id']=='58ac1cc5-5754-4580-8c9c-8c67e1a9d619':case['review_prompt']='Accept this form as usable without correction, or require fields/comments relayout?'
            for i,ref in enumerate(task.get('references',[]),1):
                source=report.rooted(root,ref.get('path') or ref['local_path']);dest=folder/'recovery-extra/cases'/cid/f'source-{i:02d}{source.suffix}';dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);case['sources'].append({'name':ref.get('name',source.name),'path':str(dest),'sha256':report.sha(dest)})
            for i,a in enumerate(run.get('submission',[]),1):
                source=report.rooted(root,a['path']);dest=folder/'recovery-extra/cases'/cid/f'deliverable-{i:02d}{source.suffix}';dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest);case['artifacts'].append({'name':f'Deliverable {i:02d}','kind':a.get('kind',source.suffix[1:]),'path':str(dest),'sha256':report.sha(dest)})
                for j,v in enumerate(a.get('previews',[]),1):
                    src=report.rooted(root,v['path']);dest=folder/'recovery-extra/cases'/cid/f'deliverable-{i:02d}-view-{j:03d}.png';shutil.copyfile(src,dest);case['renders'].append({'name':f'Deliverable {i:02d}, view {j:03d}','path':str(dest),'sha256':report.sha(dest)})
            extras.append(case)
        report.write(private_path,private)
        if extras:
            extra_payload={**payload,'cases':sorted(extras,key=lambda x:(not bool(x.get('review_prompt')),x['case_id'])),'selection':'Optional recovery examples only. A targeted form-usability question is prioritized after technical inspection; these are post-hoc diagnostics. Extra cases do not replace failed primary slots and must not enter primary acceptance denominators.'}
            extra_dir=folder/'recovery-extra';rendered=report.review_html(extra_payload,extra_dir).replace(str(folder),'[REVIEW_PACKAGE_ROOT]');(extra_dir/'index.html').write_text(sanitizer.string(rendered))
            portable_extra=copy.deepcopy(extra_payload)
            for case in portable_extra['cases']:
                for group in ('sources','artifacts','renders'):
                    for item in case.get(group,[]):item['path']=str(Path(item['path']).relative_to(extra_dir))
            report.write(extra_dir/'human-reviews.json',sanitizer.value(portable_extra))
            main=(folder/'index.html').read_text().replace('</main>','<p><a href="recovery-extra/index.html">Optional recovery diagnostic examples, separate from the primary sample</a></p></main>');(folder/'index.html').write_text(main)
    (folder/'README.txt').write_text('Open index.html in a browser. All prospective human labels are blank. Download answers from the form to save them. The nine primary slots are fixed; no failed slot is replaced. Optional recovery-extra is a separate diagnostic set. Do not consult the public audit report or judge records until labels are saved. No model identity, judge verdict, private mapping, API trace or historical label file is included. Native file contents can still suggest identity, so blinding is partial.\n')
    return {'primary_slots':len(payload['cases']),'primary_ready':sum(c['status']=='ready_for_review' for c in payload['cases']),'optional_recovery_cases':len(extras)}

def stage(root=ROOT,include_recovery=False,finalize=False):
    root=Path(root).resolve();out=root/'output/evaluation_v2';report.build(root)
    if finalize:
        pending=[c for c in report.collect_calls(out) if c.get('status')=='reserved_before_dispatch']
        if pending:raise ValueError('Final ZIP deferred: paid requests are still reserved/in progress. Stage safely now and finalize after reconciliation.')
    stage_root=out/'package-staging';public=stage_root/'public';blind=stage_root/'blind-review'
    # This only replaces this script's disposable v2 staging directories.
    for directory in (public,blind):
        if directory.exists():shutil.rmtree(directory)
        directory.mkdir(parents=True)
    sanitizer=Sanitizer(root);files=[]
    for source in selected_files(root):
        relative=source.relative_to(root);dest=public/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        data,changed=sanitizer.file_bytes(source);dest.write_bytes(data)
        files.append({'path':str(relative),'original_sha256':report.sha(source),'packaged_sha256':digest_bytes(data),'bytes':len(data),'transformed_for_publication':changed})
    (public/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>GDPval evaluation v2 evidence</title><h1>Original GDPval evaluation v2</h1><p><a href="output/evaluation_v2/report.html">Open the evidence report</a></p><p>This is an audit package containing model identities and grader results. Use the separate blind-review package before reading these results.</p>')
    (public/'README.txt').write_text('Original GDPval evaluation v2 compact review and audit archive\n\nOpen index.html or output/evaluation_v2/report.html. The complete original 15-task roster is separate from smoke, recovery, supplemental models, repeats and judge diagnostics. New human acceptance remains unknown until prospective review. Frozen invalid judgments remain invalid.\n\nPrivacy and trace policy\nCredentials, private reviewer identities, private answer/identity maps, encrypted reasoning and private reasoning text are excluded. Observable API requests/responses, physical-call reservations, costs, tool events, artifacts and configuration are included after sanitation. Inline image payloads are replaced with their hashes; native files and rendered views remain separately available. Long engine dump lines are replaced with hashes. Local home paths are replaced by placeholders. Source/package hashes and transformation flags are recorded in package-manifest.json. Sanitized traces are not byte-for-byte request replay files, and this archive does not claim complete replayability. Raw source/harness files and full original request records remain in the local project workspace; the public archive records their original hashes and every transformed copy. No private raw-trace archive is generated. Native deliverables and provided binary sources retain their original bytes.\n\nReproduction\nUse data/evaluation_v2/effective-inputs.jsonl, source attachments and pinned manifests. The original dataset revision and prompt/source hashes are retained. The solver/grader require the stated bundled artifact runtime, Node/Python and a separately configured API credential; no credential or account session is packaged. Replace local path placeholders or use manifest-relative paths for a new environment. Do not run paid scripts merely to view this report. Authorizations are spending limits, not wallet balances.\n\nThe earlier assignment ZIP was not changed. This is a separate version.\n')
    blind_summary=stage_blind(root,blind,include_recovery)
    manifest={'schema':'evaluation-v2-public-package-v1','built_at':datetime.now(timezone.utc).isoformat(),'final_zip_requested':finalize,'files':files,'sanitization_counts':sanitizer.counts,'blind_review':blind_summary,'original_assignment_untouched':True,'new_human_labels':0,'exact_request_replay_included':False,'raw_records_preserved_in_local_workspace':True,'raw_trace_archive_generated':False}
    report.write(public/'package-manifest.json',manifest)
    checks={'public':validate_package(public),'blind_review':validate_package(blind)}
    # Blind package must not include audit-only model/judge files or metadata.
    blind_json='\n'.join(p.read_text(errors='replace') for p in blind.rglob('*.json'))
    leaked_terms=[term for term in ('solver_model','judge_model','served_provider','diagnostic_matrix_cell','historical_human_consequential_error','review-private-key') if term in blind_json]
    checks['blind_metadata_exclusion']={'pass':not leaked_terms,'findings':leaked_terms}
    report.write(stage_root/'validation.json',checks)
    if any(not c['portable_local_links_valid'] or not c['credential_and_local_identity_scan_pass'] or not c['private_file_exclusion_pass'] for c in (checks['public'],checks['blind_review'])) or leaked_terms:raise ValueError('Package validation failed; inspect package-staging/validation.json. No ZIP created.')
    paths={}
    if finalize:
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');destination=out/'packages';destination.mkdir(exist_ok=True)
        for label,directory in (('evidence',public),('blind-review',blind)):
            target=destination/f'gdpval-evaluation-v2-{label}-{stamp}.zip'
            with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
                for path in sorted(directory.rglob('*')):
                    if path.is_file():archive.write(path,path.relative_to(directory))
            paths[label]=str(target)
    return {'staged_public':str(public),'staged_blind_review':str(blind),'public_file_count':len(files),'public_bytes':sum(f['bytes'] for f in files),'blind_summary':blind_summary,'validation':'passed','zip_paths':paths,'finalized':finalize}

def self_test():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td).resolve();s=Sanitizer(root);fake='sk-or-v1-'+'a'*40
        x=s.value({'Authorization':'Bearer '+fake,'body':json.dumps({'user_id':'private-human','output':[{'type':'reasoning','content':'private analysis'},{'type':'message','content':'safe'}]}),'image':'data:image/png;base64,'+'a'*40,'path':str(root/'case.json')})
        assert fake not in json.dumps(x) and 'private-human' not in json.dumps(x) and 'private analysis' not in json.dumps(x)
        assert 'SHA256' in x['image'] and '[PROJECT_ROOT]' in x['path']
        p=root/'package';p.mkdir();(p/'index.html').write_text('<a href="data/source%20file.txt">source</a>');(p/'data').mkdir();(p/'data/source file.txt').write_text('content')
        assert validate_package(p)['portable_local_links_valid']
        (p/'index.html').write_text('<a href="../missing.txt">bad</a>');assert not validate_package(p)['portable_local_links_valid']
        (p/'secret.txt').write_text(fake);assert not validate_package(p)['credential_and_local_identity_scan_pass']
        return {'status':'passed','checks':['credential/account/private-reasoning redaction','inline-media hashing','local path rewriting','portable percent-encoded links','escaping/missing links rejected','secret scan fails closed']}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',default=str(ROOT));parser.add_argument('--include-recovery',action='store_true');parser.add_argument('--finalize',action='store_true');parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    print(json.dumps(self_test() if args.self_test else stage(Path(args.root),args.include_recovery,args.finalize),indent=2))
