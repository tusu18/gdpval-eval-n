"""Finish offline checks and package the completed bounded comparison."""
import hashlib,json,re,zipfile
from pathlib import Path
from build_evidence_upgrade import validate
from summarize_native_study import summarize
from summarize_combined_native_study import main as combined_study
from prepare_focused_calibration import main as prepare_reviews
from prepare_native_grader_packets import main as prepare_grader
from build_native_study_brief import build as brief

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'output/native_workflow_01';DATA=ROOT/'data/evidence_upgrade_01'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')

def main():
 combined=combined_study();a=read(OUT/'engineering_audit.json');recovery=read(ROOT/'output/native_transport_02/engineering_audit.json')
 if not a['complete'] or not recovery['execution_finished']:raise SystemExit('Execution is still in progress; finalization deferred.')
 maps=read(DATA/'grader/evidence_maps.json');rubrics={r['id']:r for r in read(DATA/'grader/rubrics.json')}
 checks=[{'instance_id':m['instance_id'],'errors':validate(read(DATA/'solver'/(m['instance_id']+'.json')),m,rubrics[m['family_id']])} for m in maps]
 manifest=read(DATA/'manifest.json');release=[]
 if sha(DATA/'grader/evidence_maps.json')!=manifest['private_map_sha256']:release.append('private_map_changed')
 for f in manifest['files']:
  if sha(ROOT/f['path'])!=f['sha256'] or sha(ROOT/f['parent_path'])!=f['parent_sha256']:release.append(f['path'])
 tests=(OUT/'test-results.txt').read_text();match=re.search(r'Ran (\d+) tests',tests)
 if not match or not re.search(r'^OK$',tests,re.M):raise ValueError('Successful test log required.')
 smoke=read(OUT/'engineering_smoke/results.json')
 if any(x['errors'] for x in checks) or release or not a['frozen_inputs_unchanged'] or not recovery['frozen_inputs_unchanged'] or not a['protected_historical_records_unchanged']:raise ValueError('Evidence-integrity or task check failed.')
 if not all(r['authored_native_hashes_verified'] for r in a['runs']+recovery['runs']):raise ValueError('An authored native artifact no longer matches its recorded hash.')
 prepare_reviews();prepare_grader();brief()
 review=ROOT/'reviews/calibration_ready_01'
 public=json.loads((review/'cases.js').read_text().removeprefix('window.CASES = ').removesuffix(';\n'))
 linked=[]
 for case in public['cases']:
  for rel in [case['packet'],case['transcript']]+[f['path'] for f in case['files']]:
   target=(review/rel).resolve()
   if not target.is_relative_to(review.resolve()) or not target.is_file():raise ValueError('Missing or external reviewer link: '+rel)
   linked.append(rel)
 (review/'START_HERE.txt').write_text('HUMAN REVIEW WORKSPACE\n\nOpen index.html, or use the local review page at http://127.0.0.1:8767 while its preview server is running.\n\nStart with the Calibration batch: 20 frozen historical cases. The six additional diagnostics, initial native attempts and infrastructure-recovery attempts are separate cohorts. Do not combine them into an accuracy estimate.\n\nRead each full source-and-output PDF. Open the native files where needed. Record the three judgments, source/output evidence and actual review minutes. Uncertain is valid. Save and export your reviews as JSON; a reviewer export is the input for the scoring utility. Nothing is sent to an external service. Browser storage is local to the browser/profile/address, so export a backup.\n\nYour earlier issue-only and uncertain judgments remain in their original records. This interface does not invent or prefill human answers. Model names and automated grades are withheld; this is not a claim of perfect blinding.\n\nNo submitted output is available for some new attempts. Those cases include the source and observable trace, with an explicit notice. Do not infer a consequential business error solely from a missing submission.\n')
 findings=[];pattern=re.compile(r'sk-or-v1-[A-Za-z0-9]{32,}')
 for base in [OUT,ROOT/'output/native_transport_02',review,ROOT/'scripts',ROOT/'config']:
  for p in base.rglob('*'):
   if p.is_file() and not p.is_symlink() and p.suffix in ('.json','.js','.py','.mjs','.html','.txt') and pattern.search(p.read_text(errors='replace')):findings.append(str(p.relative_to(ROOT)))
 if findings:raise ValueError('Credential-shaped material found; package not created.')
 verification={'status':'offline_checks_pass','automated_tests':int(match.group(1)),
  'test_log':'output/native_workflow_01/test-results.txt','local_native_smoke_status':smoke['status'],
  'local_constructed_smoke_checks':4,'model_attempts':combined['total_finished_attempts'],'task_checks':checks,'release_integrity_errors':release,
  'protected_historical_records':len(read(ROOT/'output/evidence_upgrade_01/prior_evidence_hashes.json')),
  'frozen_inputs_unchanged':True,'protected_historical_records_unchanged':True,'credential_scan_findings':0,
  'human_full_output_reviews_created':0,'independent_task_review_complete':False,
  'reviewer_links_verified':len(linked),
  'report_visual_qa':'pending final rendered-page inspection; see visual_qa.json',
  'source_and_formula_limits':a['limits']}
 write(OUT/'verification.json',verification)
 state={'date':'2026-11-04','current_implementation':'config/native_workflow_01.json',
  'current_brief':'output/pdf/turing-native-study-and-two-pitches.pdf','current_audit':'output/native_workflow_01/engineering_audit.json',
  'verification':'output/native_workflow_01/verification.json','review_workspace':'reviews/calibration_ready_01/index.html',
  'phase':'native_execution_finished_human_review_pending','pitch_audiences':['OpenAI','Anthropic'],
  'combined_results':'output/native_workflow_01/combined_study.json','cost':combined['cost'],'model_selection_ready':False,'training_ready':False,
  'recovery_unattempted':combined['recovery']['unattempted_count'],'api_execution_block':'OpenRouter in-flight credit rejection persisted after sequential recovery.' if combined['recovery']['account_or_rate_stop'] else None,
  'supersedes':'Earlier briefs are historical for native-workflow readiness and the $25 cap. User authorized no fixed cap. Initial 20 attempts are preserved; recovery selected 14 infrastructure-failed slots, sequentially.',
  'next_action':'Complete the 20-case historical human calibration; review new native outputs separately. Adjudicate task defects and collect fresh, permissioned families before ranking models or testing training.'}
 write(ROOT/'output/current_research_state.json',state)
 with (review/'START_HERE.txt').open('a') as f:f.write('\nNew native cases distinguish completed submissions, unsubmitted diagnostic drafts and no written output. Draft labels stay separate and cannot turn an incomplete attempt into a completed delivery.\n')
 reviewfiles=sorted({review/rel for rel in linked}|{review/name for name in ('index.html','cases.js','manifest.json','START_HERE.txt')})
 with zipfile.ZipFile(ROOT/'output/turing-human-review-kit.zip','w',zipfile.ZIP_DEFLATED) as z:
  for p in sorted(reviewfiles):z.write(p,str(p.relative_to(review)))
 # Coordinator manifest is intentionally outside the masked reviewer folder.
 paths=[ROOT/'config/native_workflow_01.json',ROOT/'config/native_transport_02.json',ROOT/'output/current_research_state.json',ROOT/'output/pdf/turing-native-study-and-two-pitches.pdf']
 paths += [ROOT/p for p in read(ROOT/'config/native_workflow_01.json')['input_hashes']]
 paths += [p for p in DATA.rglob('*.json')]+[p for p in (ROOT/'data/grader_challenges_02').rglob('*.json')]
 paths += list((OUT/'runs').glob('*.json'))+list((OUT/'grader_packets').glob('*.json'))
 paths += [OUT/name for name in ('ledger.json','engineering_audit.json','verification.json','calibration_private_key.json','test-results.txt')]
 paths += [OUT/'combined_study.json',ROOT/'output/research_next_step/literature_review_2026-11-03.json']
 paths += [ROOT/'output/native_transport_02'/name for name in ('ledger.json','engineering_audit.json','run_summary.json')]
 paths += list((ROOT/'output/native_transport_02/runs').glob('*.json'))
 paths += list((ROOT/'scripts').glob('*.py'))+list((ROOT/'scripts').glob('*.mjs'))+list((ROOT/'scripts').glob('*.html'))+list((ROOT/'tests').glob('*.py'))
 for r in a['runs']+recovery['runs']:
  folder=(ROOT/r['raw_record']).parent.parent/'workspaces'/r['run_id']
  paths += [p for p in folder.rglob('*') if p.is_file()]
 paths += [p for p in (OUT/'engineering_smoke').rglob('*') if p.is_file()]
 paths=sorted(set(paths)); write(OUT/'package_manifest.json',{
  'scope':'Private coordinator evidence. Contains answer maps and model identities; keep out of solver and masked human-review contexts. Historical full campaigns remain in the workspace. This is not a standalone reproduction of every prior run.',
  'files':{str(p.relative_to(ROOT)):sha(p) for p in paths}})
 with zipfile.ZipFile(ROOT/'output/turing-native-study-coordinator-kit.zip','w',zipfile.ZIP_DEFLATED) as z:
  for p in paths+[OUT/'package_manifest.json']:z.write(p,str(p.relative_to(ROOT)))
 print(json.dumps({'human_review_files':len(reviewfiles),'coordinator_files':len(paths)+1,'complete':True}))

if __name__=='__main__':main()
