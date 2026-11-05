import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_judge_robustness_10 import assess_record, comparison, fixture_counts, normalized_copy, ledger_summary, separate_first_attempts, AUTO
from evidence_grader import score_judgment


def packet():
    return {'source_documents': {'policy': 'All approvals are required.'},
            'criteria': [{'id': 'authority', 'critical': True}],
            'artifacts': [{'id': 'memo', 'units': [{'text': 'Hold until all approvals.'}, {'text':'No release occurred.'}]}],
            'engineering_checks': {'native_count_and_types_pass': True}}


def judgment(status='pass'):
    return {'criteria': [{'id':'authority', 'status':status, 'rationale':'Evidence-based explanation.',
                         'evidence_kind':'quoted', 'evidence':[{'source_id':'policy', 'source_quote':'All approvals are required.',
                         'artifact_id':'memo', 'output_quote':'Hold until all approvals.'}],
                         'inspected_artifact_ids':['memo'], 'consequence':'Authority could be bypassed.',
                         'minimum_correction':'Preserve the hold.', 'counterevidence':'No other evidence.'}],
            'task_defect': {'status':'no', 'reason':'Sources are usable.'}}


def record(status='pass'):
    p=packet();j=judgment(status)
    return {'status':'received','judgment':j,'assessment':score_judgment(p,j)}


class RobustnessAuditTests(unittest.TestCase):
    def test_invalid_quote_not_a_pass_or_comparison(self):
        r=record();r['judgment']['criteria'][0]['evidence'][0]['output_quote']='Invented phrase'
        r['assessment']=score_judgment(packet(),r['judgment'])
        a=assess_record(r,packet())
        self.assertFalse(a['eligible']);self.assertIsNone(a['label'])
        result=comparison([('case',a,assess_record(record('fail'),packet()))])
        self.assertEqual(result['comparable'],0);self.assertEqual(result['changed'],0)

    def test_empty_criteria_cannot_be_pass_even_with_cached_pass(self):
        r=record();r['judgment']['criteria']=[]
        a=assess_record(r,packet())
        self.assertFalse(a['eligible']);self.assertIsNone(a['label'])

    def test_missing_baseline_is_not_a_flip(self):
        result=comparison([('case',assess_record(None,{}),assess_record(record('fail'),packet()))])
        self.assertEqual(result['changed'],0);self.assertEqual(result['excluded_pairs'],1)
        self.assertEqual(result['exclusion_reasons']['baseline:missing_response'],1)

    def test_uncertain_not_merged_into_pass(self):
        result=comparison([('case',assess_record(record('uncertain'),packet()),assess_record(record(),packet()))])
        self.assertEqual(result['comparable'],1);self.assertEqual(result['changed'],1)
        self.assertEqual(result['binary_comparable'],0);self.assertEqual(result['uncertain_comparisons'],1)
        self.assertEqual(result['matrix'][0]['baseline'],'uncertain')

    def test_task_defect_excluded_from_quality(self):
        r=record();r['judgment']['task_defect']['status']='yes';r['assessment']=score_judgment(packet(),r['judgment'])
        a=assess_record(r,packet())
        self.assertTrue(a['format_valid']);self.assertFalse(a['eligible']);self.assertIsNone(a['label'])

    def test_cached_validation_mismatch_excluded(self):
        r=record();r['assessment']['status']='invalid_grader_evidence'
        a=assess_record(r,packet())
        self.assertFalse(a['eligible']);self.assertTrue(a['stored_status_mismatch'])

    def test_cached_content_label_is_not_trusted(self):
        r=record('fail');r['assessment']['content_acceptable']=True
        a=assess_record(r,packet())
        self.assertEqual(a['label'],'fail')

    def test_network_error_is_not_business_error(self):
        a=assess_record({'status':'execution_error'},packet())
        self.assertFalse(a['received']);self.assertFalse(a['eligible']);self.assertIsNone(a['label'])

    def test_multiline_normalization_records_loss_and_preserves_original(self):
        j=judgment();q='word/document.xml:paragraph:1\tHold until all approvals.\nword/document.xml:paragraph:2\tNo release occurred.'
        j['criteria'][0]['evidence'][0]['output_quote']=q
        normal,changes=normalized_copy(packet(),j)
        self.assertEqual(j['criteria'][0]['evidence'][0]['output_quote'],q)
        self.assertEqual(normal['criteria'][0]['evidence'][0]['output_quote'],'Hold until all approvals.')
        self.assertEqual(changes[0]['discarded_nonempty_segments'],1)
        self.assertEqual(score_judgment(packet(),j)['status'],'invalid_grader_evidence')
        self.assertEqual(score_judgment(packet(),normal)['status'],AUTO)

    def test_normalization_cannot_salvage_invented_second_segment(self):
        j=judgment();q='word/document.xml:paragraph:1\tHold until all approvals.\nInvented second sentence.'
        j['criteria'][0]['evidence'][0]['output_quote']=q
        normal,changes=normalized_copy(packet(),j)
        self.assertEqual(changes,[]);self.assertEqual(normal['criteria'][0]['evidence'][0]['output_quote'],q)

    def test_constructed_denominator_excludes_invalid_not_as_miss(self):
        keys=[{'id':'a','member':'mutated','expected_content_acceptable':False,'expected_consequential_error':True},
              {'id':'b','member':'mutated','expected_content_acceptable':False,'expected_consequential_error':True}]
        values={'a':assess_record(record('fail'),packet()),'b':assess_record(None,{})}
        result=fixture_counts(keys,values)
        self.assertEqual(result['critical_error_checks'],{'planned':2,'binary_comparable':1,'detected':1,'missed':0,'unknown_invalid_or_unreceived':1})

    def test_valid_pair_change_has_actual_denominator(self):
        result=comparison([('a',assess_record(record(),packet()),assess_record(record('fail'),packet())),
                           ('b',assess_record(record(),packet()),assess_record(record(),packet()))])
        self.assertEqual((result['comparable'],result['changed'],result['agree']),(2,1,1))
        self.assertEqual(result['binary_changed'],1)
        self.assertEqual(len(result['agreement_diagnostics']['full_matrix']),9)
        self.assertEqual(result['binary_agreement_diagnostics']['label_frequencies']['left'],{'fail':0,'pass':2})
        self.assertIsNone(result['binary_agreement_diagnostics']['cohen_kappa']['value'])

    def test_bad_costs_are_unresolved_not_zero_known_charges(self):
        rows=[{'status':'actual','actual_cost_usd':v} for v in (0,0.5,None,True,float('nan'),-1)]
        result=ledger_summary(rows)
        self.assertEqual(result['reported_api_cost_usd'],0.5)
        self.assertEqual(result['unresolved_charge_records'],4)
        self.assertEqual(result['missing_or_invalid_amount_records'],4)


class FirstAttemptSeparationTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.root=Path(self.directory.name)
        identity={'id':'retry','study':'family','variant':'v0','model':'judge','packet':'packet.json','base_id':'base'}
        self.original={**identity,'status':'execution_error','started_at':'a','finished_at':'b','error':'socket error'}
        self.current={**identity,'status':'received','started_at':'c','finished_at':'d',
            'previous_attempts':[{k:self.original[k] for k in ('started_at','finished_at','status','error')}]}
        self.records={'retry':self.current,'other':{'id':'other','status':'received'}}
        self.first=[{'id':'retry','status':'provider_error_cost_unresolved','actual_cost_usd':None},
                    {'id':'other','status':'actual','actual_cost_usd':1.0}]
        self.ledger=self.first+[{'id':'retry','status':'actual','actual_cost_usd':0.2}]
        self.original_path='output/judge_robustness_10/first_attempts/retry.json'
        self.current_path='output/judge_robustness_10/runs/retry.json'
        self.ledger_path='output/judge_robustness_10/first_attempts/ledger.json'
        self.manifest_path='output/judge_robustness_10/first_attempts/manifest.json'
        def save(path,data):
            dest=self.root/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(data)+'\n')
            return hashlib.sha256(dest.read_bytes()).hexdigest()
        self.save=save
        self.manifest={'schema':'first-attempt-archive-snapshot-v1','source_archive':'output/history/prior.zip','source_archive_sha256':'0'*64,
            'records':[{'id':'retry','path':self.original_path,'sha256':save(self.original_path,self.original),
                        'recovery_record':self.current_path,'recovery_sha256':save(self.current_path,self.current),'original_status':'execution_error'}],
            'ledger':{'path':self.ledger_path,'sha256':save(self.ledger_path,self.first),'records':2}}
        save(self.manifest_path,self.manifest)

    def tearDown(self):self.directory.cleanup()

    def run_split(self):return separate_first_attempts(self.root,self.records,self.ledger,{'retry','other'})

    def test_original_error_remains_primary_and_costs_include_both_attempts(self):
        primary,first,extra,ids,provenance=self.run_split()
        self.assertEqual(primary['retry']['status'],'execution_error')
        self.assertEqual(self.records['retry']['status'],'received')
        self.assertEqual(ids,['retry']);self.assertEqual(len(first),2);self.assertEqual(len(extra),1)
        self.assertEqual(ledger_summary(first)['unresolved_charge_records'],1)
        self.assertAlmostEqual(ledger_summary(self.ledger)['reported_api_cost_usd'],1.2)
        self.assertEqual(provenance['mode'],'archived_first_attempts')

    def test_changed_original_snapshot_fails_closed(self):
        self.save(self.original_path,{**self.original,'error':'changed'})
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.run_split()

    def test_changed_recovery_snapshot_fails_closed(self):
        self.save(self.current_path,{**self.current,'status':'execution_error'})
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.run_split()

    def test_changed_first_ledger_prefix_fails_closed(self):
        self.ledger=copy.deepcopy(self.ledger);self.ledger[0]['actual_cost_usd']=0
        with self.assertRaisesRegex(ValueError,'ledger changed'):self.run_split()

    def test_extra_or_unexpected_retry_fails_closed(self):
        self.ledger.append({'id':'other','status':'actual','actual_cost_usd':0.2})
        with self.assertRaisesRegex(ValueError,'identities'):self.run_split()

    def test_recovery_predecessor_must_match_preserved_error(self):
        self.current['previous_attempts'][0]['error']='different error'
        self.manifest['records'][0]['recovery_sha256']=self.save(self.current_path,self.current)
        self.save(self.manifest_path,self.manifest)
        with self.assertRaisesRegex(ValueError,'predecessor metadata'):self.run_split()

    def test_manifest_required_when_recovery_is_present(self):
        (self.root/self.manifest_path).unlink()
        with self.assertRaisesRegex(ValueError,'require a validated'):self.run_split()

    def test_locally_present_original_archive_hash_is_checked(self):
        dest=self.root/'output/history/prior.zip';dest.parent.mkdir(parents=True);dest.write_bytes(b'wrong archive')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.run_split()


if __name__=='__main__':unittest.main()
