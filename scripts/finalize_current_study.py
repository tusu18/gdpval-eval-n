"""Package current evidence without turning automatic judgments into human labels."""
import argparse,hashlib,json,re,shutil,subprocess,sys,zipfile
from pathlib import Path
from run_completion_and_pairs import read,write,sha,utc
from summarize_current_study import main as summarize
from prepare_focused_calibration import main as prepare_reviews
from prepare_native_grader_packets import main as prepare_packets
from build_focused_submission import build as build_report
from build_submission_site import build as build_site
from build_interview_defense import build as build_defense
from build_current_evaluation_card import build as build_card
from analyze_current_transport import build as analyze_transport
from build_evidence_upgrade import validate
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/current_study_06'

def seal():
    # The coordinator archive is private. Public submission has no answer maps,
    # automatic labels for review cases, account metadata, or five-model table.
    old=read(ROOT/'output/archive/before-limit-increase/output/native_workflow_01/package_manifest.json')
    paths={ROOT/p for p in old['files'] if (ROOT/p).exists()}
    for directory in ('config','scripts','tests'):
        paths.update(p for p in (ROOT/directory).iterdir() if p.is_file() and p.suffix in ('.json','.py','.mjs','.html'))
    for stage in ('native_completion_03','native_completion_07','paired_native_08','native_backoff_probe_09','grader_checks_05','current_study_06'):
        paths.update(p for p in (ROOT/'output'/stage).rglob('*') if p.is_file() and p.name not in ('account_limit_snapshot.json','model_catalog.json','preview.pdf') and p.suffix not in ('.png',) )
        # Native rendering evidence is preserved as well as submitted bytes.
        if stage.startswith(('native','paired')):paths.update((ROOT/'output'/stage).rglob('*.png'))
    paths.update([ROOT/'output/pdf/turing-native-study-and-two-pitches.pdf',ROOT/'output/current_research_state.json'])
    paths.update(p for p in (ROOT/'reviews/purchasing_calibration').rglob('*') if p.is_file())
    paths.update((OUT/'case-1').glob('*.png'))
    paths.discard(OUT/'package_manifest.json')
    write(OUT/'package_manifest.json',{'scope':'Private coordinator evidence; answer maps, unblinded model logs and automatic grades. Keep out of human-review and solver contexts. Historical failed runs are preserved.','files':{str(p.relative_to(ROOT)):sha(p) for p in sorted(paths)}})
    with zipfile.ZipFile(ROOT/'output/turing-native-study-coordinator-kit.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(paths|{OUT/'package_manifest.json'}):z.write(p,str(p.relative_to(ROOT)))
    with zipfile.ZipFile(ROOT/'output/turing-submission-ready.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted((ROOT/'output/submission_ready').rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(ROOT/'output/submission_ready')))
    for name in ('turing-native-study-coordinator-kit.zip','turing-human-review-kit.zip','turing-submission-ready.zip'):
        with zipfile.ZipFile(ROOT/'output'/name) as z:
            if z.testzip() is not None or len(z.namelist())!=len(set(z.namelist())):raise ValueError('Bad archive: '+name)
    print(json.dumps({'archives_verified':3,'coordinator_files':len(paths)+1}))

def main(allow_incomplete=False):
    c=summarize()
    if not c['paired_execution_complete'] and not allow_incomplete:raise ValueError('Paired study not finished.')
    completion=c['engineering_recovery']['native_completion_07']
    if not completion['complete'] and not allow_incomplete:raise ValueError('Infrastructure continuation not finished.')
    probe=c['engineering_recovery'].get('native_backoff_probe_09')
    if probe and not probe['complete']:raise ValueError('The separate engineering probe remains unfinished.')
    if c['grader'].get('attempted')!=56:raise ValueError('Approved grader batch not finished.')
    analyze_transport()
    if not c['frozen_inputs_unchanged'] or not c['protected_historical_records_unchanged']:raise ValueError('Frozen evidence changed.')
    cfg=read(ROOT/'config/grader_checks_05.json')
    for rel,digest in cfg['input_hashes'].items():
        if sha(ROOT/rel)!=digest:raise ValueError('Grader input changed: '+rel)
    maps=read(ROOT/'data/evidence_upgrade_01/grader/evidence_maps.json');rubrics={r['id']:r for r in read(ROOT/'data/evidence_upgrade_01/grader/rubrics.json')}
    checks=[{'instance_id':m['instance_id'],'errors':validate(read(ROOT/'data/evidence_upgrade_01/solver'/(m['instance_id']+'.json')),m,rubrics[m['family_id']])} for m in maps]
    if any(x['errors'] for x in checks):raise ValueError('Task validation failed.')
    tested=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,text=True,capture_output=True)
    log=tested.stdout+tested.stderr;(OUT/'test-results.txt').write_text(log)
    if tested.returncode:raise ValueError('Tests failed; inspect test-results.txt.')
    count=int(re.search(r'Ran (\d+) tests',log).group(1))
    prepare_reviews();prepare_packets();build_report(allow_incomplete=allow_incomplete);build_defense()
    review=ROOT/'reviews/calibration_ready_01';public=json.loads((review/'cases.js').read_text().removeprefix('window.CASES = ').removesuffix(';\n'))
    linked=set()
    for case in public['cases']:
        for rel in [case['packet'],case['transcript']]+[f['path'] for f in case['files']]:
            p=(review/rel).resolve()
            if not p.is_relative_to(review.resolve()) or not p.is_file():raise ValueError('Broken review link: '+rel)
            linked.add(p)
    (review/'START_HERE.txt').write_text('Start with the 20-case Calibration batch. Read full sources and outputs. Record usable / consequential error / evaluation defect separately, with source and output evidence and actual review minutes. Uncertain is valid. Do not copy automatic grades.\n\nThe matched development batch fixes one model across baseline/conflict pairs; it is not held out. Earlier native and infrastructure-recovery batches are separate diagnostics. Unsubmitted drafts do not become completed deliveries.\n\nSave and export your JSON reviews. Local browser storage depends on browser/profile/address; export backups. Existing issue-only and uncertain answers remain separate. No human labels are prefilled.\n')
    linked.update(review/n for n in ('index.html','cases.js','manifest.json','START_HERE.txt'))
    with zipfile.ZipFile(ROOT/'output/turing-human-review-kit.zip','w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(linked):z.write(p,str(p.relative_to(review)))
    build_site()
    bundle=ROOT/'output/submission_ready';shutil.copyfile(ROOT/'output/turing-human-review-kit.zip',bundle/'human-review-kit.zip')
    shutil.copyfile(OUT/'interview-defense.txt',bundle/'interview-defense.txt')
    # Copy only linked review assets; no private key or unlabeled helper file.
    if (bundle/'review').exists():shutil.rmtree(bundle/'review')
    for p in linked:
        target=bundle/'review'/p.relative_to(review);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    patterns=re.compile(rb'sk-or-v1-[A-Za-z0-9]{32,}')
    for directory in ('scripts','config','output/current_study_06','output/grader_checks_05','output/native_completion_03','output/native_completion_07','output/paired_native_08','output/native_backoff_probe_09','output/submission_ready'):
        for p in (ROOT/directory).rglob('*'):
            if p.is_file() and not p.is_symlink() and p.suffix in ('.json','.jsonl','.txt','.py','.mjs','.html','.js') and patterns.search(p.read_bytes()):raise ValueError('Credential pattern: '+str(p))
    verification={'updated_at':utc(),'status':'offline_checks_pass','execution_complete':c['paired_execution_complete'] and completion['complete'],
        'release_scope':'Incomplete evidence snapshot; remaining native attempts are still pending.' if not (c['paired_execution_complete'] and completion['complete']) else 'Execution complete; human review pending.',
        'unattempted_paired':c['paired_planned_attempts']-c['paired_finished_attempts'],'unattempted_engineering_recovery':completion['planned_attempts']-completion['finished_attempts'],
        'automated_tests':count,'task_variants_checked':len(checks),'task_checks':checks,
        'native_smoke_checks':4,'native_smoke_scope':'Existing four constructed checks on unchanged native tools.','historical_records_unchanged':438,
        'frozen_inputs_unchanged':True,'review_cases':len(public['cases']),'review_links_verified':len(linked),
        'human_labels_created':0,'model_ranking':None,'human_calibrated_grader':False,'report_visual_qa':'pending final rendered-page inspection'}
    write(OUT/'verification.json',verification)
    build_card()
    write(ROOT/'output/current_research_state.json',{'updated_at':utc(),'phase':'paired_execution_complete_human_review_pending' if c['paired_execution_complete'] and completion['complete'] else 'credit_limit_interrupted_human_review_pending','current_brief':'output/pdf/turing-native-study-and-two-pitches.pdf',
        'current_summary':'output/current_study_06/summary.json','current_site':'output/submission_ready/index.html','paired_protocol':'config/paired_native_08.json',
        'review_workspace':'reviews/calibration_ready_01/index.html','cost':c['cost'],'model_selection_ready':False,'training_ready':False,
        'unattempted_paired':verification['unattempted_paired'],'unattempted_engineering_recovery':verification['unattempted_engineering_recovery'],
        'next_action':('Resume unattempted native runs once account funding and key allowance permit. ' if not verification['execution_complete'] else '')+'Complete human calibration, review matched outputs separately, and adjudicate task defects. Fresh permissioned families are required for held-out claims.'})
    seal();print(json.dumps(verification))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--allow-incomplete',action='store_true');main(parser.parse_args().allow_incomplete)
