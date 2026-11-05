"""Portable evidence checks: missing pairs, invalid grades and archive tampering."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from reproduce_assignment import recompute,source_hashes_explained
from package_assignment_submission import scan,redact_account_ids,verify_archive,require_complete_robustness


def save(root,path,data):
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(data));return target


def fixture(root):
    (root/'scripts').mkdir()
    shutil.copyfile(ROOT/'scripts/score_paired_pilot.py',root/'scripts/score_paired_pilot.py')
    shutil.copyfile(ROOT/'scripts/reproduce_assignment.py',root/'reproduce_assignment.py')
    save(root,'data/paired_v1/grader/rubrics.json',[{'id':'f','truth':{'cost':100}}])
    save(root,'data/paired_v1/solver/f__baseline.json',{'occupation':'Buyer'})
    for variant,status in [('baseline','completed'),('conflict','invalid_json')]:
        r={'run_id':'f__'+variant,'family_id':'f','variant':variant,'model':'solver','trial':1,
           'status':status,'actual_cost_usd':0.1,'elapsed_seconds':2,'tool_events':[],
           'final':{'facts':{'cost':100},'artifacts':[]} if status=='completed' else {}}
        save(root,'output/paired_v1/runs/'+variant+'.json',r)
        save(root,'output/paired_native_08/runs/'+variant+'.json',{'family_id':'f','condition':variant,
             'status':'submitted' if variant=='baseline' else 'execution_error'})
    save(root,'output/paired_v1/judgments_v3/p.json',{'run_id':'f__baseline','kind':'primary',
         'status':'completed','judgment':{'critical_error':False}})
    save(root,'output/paired_v1/summary.json',{'saved_runs':2,'review':{'valid_primary':1,'valid_secondary':0}})
    save(root,'output/current_study_06/summary.json',{'paired_finished_attempts':2,'paired_submitted_attempts':1,
         'pairs_with_both_submitted':0,'cost':{'reported_cumulative_usd':0.2,'unresolved_charge_records':1}})
    for group in ('paired_v1','repair_probe_01','native_workflow_01','native_transport_02','native_completion_03',
                  'native_completion_07','paired_native_08','native_backoff_probe_09','grader_checks_05'):
        save(root,'output/'+group+'/ledger.json',[{'actual_cost_usd':0.2}] if group=='paired_v1' else [])
    save(root,'output/paired_v1/judge_ledger.json',[])
    save(root,'output/grader_checks_05/runs/h.json',{'cohort':'historical_calibration','status':'received',
         'assessment':{'status':'invalid_grader_evidence'}})
    save(root,'output/grader_checks_05/runs/c.json',{'cohort':'constructed','status':'received',
         'assessment':{'status':'automated_assessment_not_human_acceptance'}})


class PortableReproductionTests(unittest.TestCase):
    def test_source_hash_difference_requires_explicit_bound_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            self.assertFalse(source_hashes_explained(root,{'run.json':'old'},{'run.json':'new'}))
            save(root,'SOURCE_MAP.json',{'files':[{'project_path':'run.json','source_sha256':'old',
                'packaged_sha256':'new','transformation':'Provider account identifier redacted; substantive evidence unchanged.'}]})
            self.assertTrue(source_hashes_explained(root,{'run.json':'old'},{'run.json':'new'}))
            self.assertFalse(source_hashes_explained(root,{'run.json':'old'},{'run.json':'unexpected'}))
            self.assertFalse(source_hashes_explained(root,{'run.json':'old','missing.json':'x'},{'run.json':'new'}))

    def test_missing_output_never_becomes_completed_pair_or_human_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture(root);result=recompute(root)
            self.assertEqual(result['extension']['complete_pairs'],0)
            self.assertEqual(result['historical']['structured_decision_passes'],1)
            self.assertEqual(result['grader_cohorts']['historical_calibration']['raw_evidence_valid'],0)
            self.assertIsNone(result['human'])
            self.assertTrue(result['all_consistency_checks_pass'])
            self.assertFalse(result['cost_scope']['grader_robustness_included'])
            self.assertFalse(result['cost_scope']['additional_stages_ingested'])

    def test_completed_robustness_cost_is_added_once_and_recomputed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture(root)
            save(root,'config/judge_robustness_10.json',{'jobs':[]})
            save(root,'output/judge_robustness_10/ledger.json',[
                {'actual_cost_usd':0.3,'status':'actual'},
                {'actual_cost_usd':None,'status':'provider_error_cost_unresolved'}])
            (root/'scripts/analyze_judge_robustness_10.py').write_text(
                'def build(root):\n    return {"recomputed_from_records": True}\n')
            result=recompute(root)
            self.assertAlmostEqual(result['reported_api_cost_usd'],0.5)
            self.assertEqual(result['unresolved_charge_records_as_recorded'],2)
            self.assertTrue(result['grader_robustness']['recomputed_from_records'])
            self.assertTrue(result['cost_scope']['grader_robustness_included'])
            self.assertTrue(result['all_consistency_checks_pass'])

    def test_reference_tampering_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture(root)
            path=root/'output/current_study_06/summary.json';doc=json.loads(path.read_text())
            doc['paired_submitted_attempts']=2;path.write_text(json.dumps(doc))
            result=recompute(root)
            self.assertFalse(result['all_consistency_checks_pass'])
            self.assertFalse(result['consistency_checks']['paired_submitted_count'])

    def test_stale_task_trace_is_not_a_verified_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture(root)
            save(root,'output/assignment_final/evaluation-record.json',{'attempts':30})
            (root/'scripts/build_evaluation_record.py').write_text(
                'def build(root):\n    return {"attempts": 60}\n')
            result=recompute(root)
            self.assertFalse(result['all_consistency_checks_pass'])
            self.assertFalse(result['consistency_checks']['task_and_attempt_record_matches_frozen_inputs'])

    def test_prepared_controls_are_inspected_without_execution_or_fake_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fixture(root)
            save(root,'config/judge_controls_11.proposed.json',{'execution_enabled':False})
            (root/'scripts/build_judge_controls_11.py').write_text(
                'def inspect(root):\n    return {"status":"prepared_not_run","executed_requests":0,"human_validated_cases":0,"reported_api_cost_usd":None}\n')
            result=recompute(root)
            self.assertTrue(result['consistency_checks']['proposed_controls_invariants_pass'])
            self.assertEqual(result['proposed_judge_controls']['executed_requests'],0)
            self.assertIsNone(result['proposed_judge_controls']['reported_api_cost_usd'])
            self.assertEqual(result['network_calls'],0)

    def test_runs_from_unrelated_working_directory_without_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'unpacked code with spaces';root.mkdir();fixture(root)
            run=subprocess.run([sys.executable,'-S',str(root/'reproduce_assignment.py')],cwd=directory,
                               capture_output=True,text=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stderr)
            report=json.loads((root/'reproduced-results.json').read_text())
            self.assertEqual(report['network_calls'],0)
            self.assertTrue(report['all_consistency_checks_pass'])


class PackageIntegrityTests(unittest.TestCase):
    def test_final_package_refuses_missing_running_or_duplicate_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            save(root,'config/judge_robustness_10.json',{'jobs':[{'id':'a'},{'id':'b'}]})
            save(root,'output/judge_robustness_10/ledger.json',[])
            save(root,'output/judge_robustness_10/runs/a.json',{'id':'a','status':'received'})
            with self.assertRaises(ValueError):require_complete_robustness(root)
            save(root,'output/judge_robustness_10/runs/b.json',{'id':'b','status':'running'})
            with self.assertRaises(ValueError):require_complete_robustness(root)
            save(root,'output/judge_robustness_10/runs/b.json',{'id':'b','status':'execution_error'})
            snapshot=require_complete_robustness(root)
            self.assertEqual(len(snapshot),4)
            save(root,'output/judge_robustness_10/runs/duplicate.json',{'id':'b','status':'received'})
            with self.assertRaises(ValueError):require_complete_robustness(root)

    def test_embedded_encrypted_substring_is_not_a_standalone_key(self):
        fragment=b'sk-'+b'A'*55
        scan(b'opaquePrefix'+fragment+b'opaqueSuffix','opaque.json')
        with self.assertRaises(ValueError):scan(b'"'+fragment+b'"','key.json')

    def test_account_redaction_preserves_cost_and_status(self):
        original={'status':'execution_error','actual_cost_usd':0.25,
                  'error':'Provider error {"user_id":"example-account"}',
                  'nested':{'account_id':'account-example'}}
        clean,changed=redact_account_ids(json.dumps(original).encode(),'.json')
        result=json.loads(clean)
        self.assertTrue(changed)
        self.assertEqual(result['actual_cost_usd'],0.25)
        self.assertEqual(result['status'],'execution_error')
        self.assertNotIn('example-account',clean.decode())
        self.assertEqual(result['nested']['account_id'],'[ACCOUNT_ID_REMOVED]')

    def test_archive_tampering_and_unmanifested_entries_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'bundle.zip';data=b'original'
            manifest={'files':[{'path':'index.html','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('index.html',b'tampered');z.writestr('MANIFEST.json',json.dumps(manifest))
            with self.assertRaises(ValueError):verify_archive(path)
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('index.html',data);z.writestr('MANIFEST.json',json.dumps(manifest));z.writestr('unlisted.txt','extra')
            with self.assertRaises(ValueError):verify_archive(path)


if __name__=='__main__':unittest.main()
