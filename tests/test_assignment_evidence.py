import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('assignment_evidence',Path(__file__).parents[1]/'scripts/assignment_evidence.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
report_spec=importlib.util.spec_from_file_location('assignment_report',Path(__file__).parents[1]/'scripts/build_assignment_submission.py')
report=importlib.util.module_from_spec(report_spec);report_spec.loader.exec_module(report)

def mapping():
 return {'C-one':{'review_id':'C-one','run_id':'family__baseline__model__r1','family_id':'family','calibration_queue':True,'failure_queue':True,'historical_output_available':True},'N-draft':{'review_id':'N-draft','run_id':'draft','family_id':'family','calibration_queue':False,'failure_queue':False,'new_native_queue':True,'native_stage':'paired','native_output_status':'unsubmitted_draft'}}
def row(cid='C-one',**kw):
 return dict(review_id=cid,human_reviewed=True,content_acceptable='no',consequential_error='yes',evaluation_defect='no',category='approval_bypass',output_evidence='Page2:release now',source_and_consequence='Source:Finance approval missing; unauthorized release',review_minutes=None,**{})|kw
def document(rows=None,**kw):
 return {'schema':'turing-human-review-v1','reviewer_id':'human-a','qualification':None,'independent_of_author':None,'rows':rows if rows is not None else [row()]}|kw
def imported(digest='a',doc=None):
 doc=doc or document();return {'sha256':digest,'doc':doc,'rows':a.validate_export(doc,mapping())}
def observations(doc=None):return a.resolve_documents([imported(doc=doc)])[0]
def judge(valid=True):return {'C-one':{'status':'received','assessment':{'status':'automated_assessment_not_human_acceptance' if valid else 'invalid_grader_evidence','content_acceptable':True,'consequential_error':False}}}

class EvidenceTests(unittest.TestCase):
 def test_review_closure_requires_evidence_and_repair_not_only_case_count(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'config').mkdir()
   (root/'config/assignment_review_minimal_v1.json').write_text(json.dumps({'case_ids':['C-one'],'target_case_count':1}))
   pending=a.summarize_review_plan(root,observations(),mapping())
   self.assertTrue(pending['full_content_reviews_complete'])
   self.assertFalse(pending['human_review_complete'])
   self.assertEqual(pending['pending_finding_case_ids'],['C-one'])
   done=a.summarize_review_plan(root,observations(document([row(minimum_repair='Require Finance signoff before release')])),mapping())
   self.assertTrue(done['human_review_complete'])
   self.assertFalse(done['assignment_complete_inferred']);self.assertFalse(done['grader_validated'])
 def test_review_closure_does_not_resolve_disagreements_or_force_uncertain_labels(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'config').mkdir()
   (root/'config/assignment_review_minimal_v1.json').write_text(json.dumps({'case_ids':['C-one'],'target_case_count':1}))
   uncertain=observations(document([row(content_acceptable='uncertain',consequential_error='uncertain',category=None)]))
   self.assertTrue(a.summarize_review_plan(root,uncertain,mapping())['human_review_complete'])
   first=observations(document([row(minimum_repair='Require Finance signoff')]))
   other=copy.deepcopy(first);other[0]['row']['content_acceptable']='yes'
   x=a.summarize_review_plan(root,first+other,mapping())
   self.assertFalse(x['human_review_complete']);self.assertEqual(x['unresolved_disagreement_case_ids'],['C-one'])
 def test_human_tooling_category_retains_exact_label_and_conditional_scope(self):
  r=row(category='tooling_release_not_gated_on_bridge_supply',
        category_label='Tooling release not gated on bridge supply',
        category_definition='plastic tool scheduled to move while the bridge still needs it',
        category_authorship='Explicit user-provided category',
        evidence_scope_notes=['Single tooling set is a reviewer assumption, not an explicit source fact.'])
  x=a.summarize_humans(observations(document([r])),mapping(),{})['taxonomy']
  self.assertEqual(x['counts'],{'tooling_release_not_gated_on_bridge_supply':1})
  self.assertEqual(x['examples'][0]['category_label'],r['category_label'])
  self.assertEqual(x['examples'][0]['evidence_scope_notes'],r['evidence_scope_notes'])
  self.assertIsNone(x['examples'][0]['minimum_repair'])
 def test_case_comparison_retains_actual_labels_without_invalid_grade_fallback(self):
  rows=[row()]
  valid=a.case_level_comparisons(rows,mapping(),judge())[0]['endpoints']['consequential_error']
  self.assertEqual(valid['human_label'],'yes');self.assertEqual(valid['judge_label'],'no')
  self.assertTrue(valid['comparable'])
  invalid=a.case_level_comparisons(rows,mapping(),judge(False))[0]['endpoints']['consequential_error']
  self.assertIsNone(invalid['judge_label']);self.assertEqual(invalid['exclusions'],['invalid_judge_evidence'])
  missing=a.case_level_comparisons(rows,mapping(),{})[0]['endpoints']['consequential_error']
  self.assertIsNone(missing['judge_label']);self.assertEqual(missing['exclusions'],['missing_judge_response'])
 def test_reduced_plan_counts_only_selected_real_reviews_without_validity_claim(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'config').mkdir()
   plan={'case_ids':['C-one','N-draft'],'target_case_count':2,'headline_issue_case_ids':['C-one']}
   (root/'config/assignment_review_minimal_v1.json').write_text(json.dumps(plan))
   x=a.summarize_review_plan(root,observations(document([row(content_acceptable='uncertain',consequential_error='uncertain')])),mapping())
   self.assertEqual(x['completed_case_ids'],['C-one'])
   self.assertEqual(x['remaining_case_ids'],['N-draft'])
   self.assertEqual(x['remaining_core_endpoint_answers'],3)
   self.assertFalse(x['assignment_complete_inferred']);self.assertFalse(x['grader_validated'])
   self.assertIn('no disposition inferred',x['headline_issue_disposition'])
 def test_reduced_plan_rejects_duplicate_cases_and_missing_headline_members(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'config').mkdir();p=root/'config/assignment_review_minimal_v1.json'
   p.write_text(json.dumps({'case_ids':['C-one','C-one'],'target_case_count':2}))
   with self.assertRaisesRegex(ValueError,'duplicate'):a.summarize_review_plan(root,[],mapping())
   p.write_text(json.dumps({'case_ids':['C-one'],'target_case_count':1,'headline_issue_case_ids':['N-draft']}))
   with self.assertRaisesRegex(ValueError,'outside'):a.summarize_review_plan(root,[],mapping())
 def test_no_comparable_grade_pairs_are_unmeasured_in_report(self):
  self.assertEqual(report.comparison_fraction({'comparable':0,'changed':0}),'unmeasured (0 comparable)')
 def test_report_does_not_pool_bias_guidance_with_rewording(self):
  comparisons={v:{'comparable':2,'changed':0} for v in ('v1_reword','v2_reword','v3_reword')}
  comparisons['v4_bias_aware']={'comparable':2,'changed':2}
  e={'grader_robustness':{'completion':{'received':8,'planned':8},'raw':{'format_valid':8},'sensitivity':{'comparisons':comparisons},'injection':{'comparison':{'comparable':0,'changed':0}},'family':{'historical':{'comparable':6,'changed':2}}}}
  text=report.robustness_brief(e)
  self.assertIn('0/6 eligible rewording',text);self.assertIn('2/2 bias-aware',text)
  self.assertIn('unmeasured (0 comparable) selected injection',text)
  self.assertIn('disagreed on 2/6 eligible historical cases',text)
 def test_robustness_cost_added_once_and_unknown_not_free(self):
  prior={'reported_cumulative_usd':36.1950216,'unresolved_charge_records':33,'human_labor_usd':None}
  ledger=[{'status':'actual','actual_cost_usd':0.5},{'status':'provider_error_cost_unresolved','actual_cost_usd':None}]
  x=a.cost_with_robustness(prior,ledger,{'complete':True})
  self.assertAlmostEqual(x['reported_cumulative_usd'],36.6950216)
  self.assertEqual(x['unresolved_charge_records'],34)
  self.assertEqual(x['previous_snapshot_usd'],prior['reported_cumulative_usd'])
  self.assertIsNone(x['cost_per_accepted_deliverable'])
  self.assertEqual(prior['reported_cumulative_usd'],36.1950216)
 def test_robustness_cost_rejects_nonfinite_and_missing_actual(self):
  prior={'reported_cumulative_usd':0,'unresolved_charge_records':0}
  with self.assertRaises(ValueError):a.cost_with_robustness(prior,[{'status':'actual','actual_cost_usd':float('nan')}],{})
  x=a.cost_with_robustness(prior,[{'status':'actual','actual_cost_usd':None}],{'complete':False})
  self.assertEqual(x['unresolved_charge_records'],1)
  self.assertFalse(x['grader_robustness_complete'])
 def test_empty_is_unknown_not_zero_rate(self):
  x=a.summarize_humans([],mapping(),{})
  self.assertEqual(x['completed_count'],0);self.assertIsNone(x['review_minutes']['recorded_total'])
  self.assertIsNone(x['calibration']['metrics']['consequential_error']['error_sensitivity']['value'])
  self.assertIsNone(x['outcomes']['historical']['endpoints']['content_acceptable']['yes_among_resolved']['value'])
  self.assertEqual(x['calibration']['metrics']['consequential_error']['agreement_diagnostics']['cohen_kappa']['status'],'no_pairs')
 def test_uncertainty_preserved_and_not_binary(self):
  x=a.summarize_humans(observations(document([row(content_acceptable='uncertain',consequential_error='uncertain')])),mapping(),judge())
  self.assertEqual(x['completed_count'],1);self.assertEqual(x['calibration']['metrics']['content_acceptable']['comparable'],0)
  self.assertEqual(x['outcomes']['historical']['endpoints']['content_acceptable']['counts'],{'uncertain':1})
 def test_task_defects_excluded_not_relabelled(self):
  x=a.summarize_humans(observations(document([row(evaluation_defect='yes')])),mapping(),judge())
  self.assertEqual(x['outcomes']['historical']['eligible_valid_submissions'],0)
  self.assertEqual(x['calibration']['metrics']['consequential_error']['exclusions'],{'task_defect_or_uncertain_validity':1})
 def test_invalid_judge_is_not_false_negative_or_fallback(self):
  x=a.summarize_humans(observations(),mapping(),judge(False))['calibration']['metrics']['consequential_error']
  self.assertEqual(x['comparable'],0);self.assertEqual(x['exclusions']['invalid_judge_evidence'],1)
 def test_missed_errors_and_false_accepts_separate(self):
  x=a.summarize_humans(observations(),mapping(),judge())['calibration']['metrics']
  self.assertEqual(x['consequential_error']['missed_errors']['numerator'],1)
  self.assertEqual(x['content_acceptable']['false_accepts_among_judge_accepts']['numerator'],1)
 def test_identical_exports_deduplicated(self):
  obs,conflicts,_=a.resolve_documents([imported('a'),imported('b')])
  self.assertEqual(len(obs),1);self.assertEqual(conflicts,[])
 def test_changed_export_needs_explicit_supersession(self):
  changed=document([row(content_acceptable='yes')])
  obs,conflicts,_=a.resolve_documents([imported('a'),imported('b',changed)])
  self.assertFalse(obs);self.assertEqual(len(conflicts),1)
  changed['supersedes_export_sha256']='a'
  obs,conflicts,_=a.resolve_documents([imported('a'),imported('b',changed)])
  self.assertEqual(obs[0]['row']['content_acceptable'],'yes');self.assertFalse(conflicts)
 def test_other_reviewer_cannot_supersede(self):
  changed=document([row(content_acceptable='yes')],reviewer_id='human-b',supersedes_export_sha256='a')
  obs,_,errors=a.resolve_documents([imported('a'),imported('b',changed)])
  self.assertEqual(len(errors),1);self.assertEqual(obs[0]['reviewer_id'],'human-a')
 def test_cyclic_supersession_rejected(self):
  with self.assertRaisesRegex(ValueError,'Cyclic'):
   a.resolve_documents([imported('a',document(supersedes_export_sha256='b')),imported('b',document(supersedes_export_sha256='a'))])
 def test_two_reviewers_disagree_no_majority_or_consensus(self):
  other=document([row(consequential_error='no')],reviewer_id='human-b')
  obs,_,_=a.resolve_documents([imported('a'),imported('b',other)])
  x=a.summarize_humans(obs,mapping(),judge())
  self.assertEqual(x['completed_count'],1);self.assertEqual(x['review_observations'],2)
  self.assertEqual(len(x['reviewer_disagreements']),1);self.assertEqual(x['calibration']['metrics']['consequential_error']['comparable'],0)
  self.assertIsNone(x['reviewer_disagreements'][0]['adjudicated_label'])
 def test_draft_never_accepted_delivery(self):
  x=a.summarize_humans(observations(document([row('N-draft',content_acceptable='yes',consequential_error='no')])),mapping(),{})
  self.assertEqual(x['outcomes']['paired_extension']['eligible_valid_submissions'],0)
  self.assertEqual(x['outcomes']['paired_extension']['exclusions']['not_a_submitted_deliverable'],1)
 def test_taxonomy_needs_evidence_not_only_category(self):
  x=a.summarize_humans(observations(document([row(consequential_error='no',output_evidence='')])),mapping(),{})
  self.assertEqual(x['taxonomy']['manually_categorized_count'],0)
  self.assertEqual(x['taxonomy']['exclusions']['missing_taxonomy_evidence'],1)
 def test_reject_unsupported_consequential_label(self):
  with self.assertRaises(ValueError):a.validate_export(document([row(output_evidence='')]),mapping())
 def test_saved_timestamp_does_not_create_conflict(self):
  obs,conflicts,_=a.resolve_documents([imported('a',document([row(saved_at='first')])),imported('b',document([row(saved_at='second')]))])
  self.assertEqual(len(obs),1);self.assertFalse(conflicts)
 def test_metadata_change_is_not_silent_qualification_upgrade(self):
  obs,_,_=a.resolve_documents([imported('a'),imported('b',document(qualification='Purchasing manager',independent_of_author=True))])
  reviewer=a.summarize_humans(obs,mapping(),{})['reviewers'][0]
  self.assertIsNone(reviewer['qualification']);self.assertIsNone(reviewer['independent_of_author'])
  self.assertIn('qualification',reviewer['metadata_conflicts'])
 def test_historical_taxonomy_and_native_flags_separate(self):
  m=mapping();m['N-draft']['failure_queue']=True
  x=a.summarize_humans([],m,{})['taxonomy']
  self.assertEqual(x['planned_candidates'],1);self.assertEqual(x['native_flagged_candidates_separate'],1)
 def test_uncertain_error_is_not_confirmed_by_category(self):
  x=a.summarize_humans(observations(document([row(consequential_error='uncertain')])),mapping(),{})['taxonomy']
  self.assertEqual(x['manually_categorized_count'],1);self.assertEqual(x['human_confirmed_business_error_count'],0)
 def test_manual_severity_repair_and_secondary_notes_preserved(self):
  r=row(severity='material',minimum_repair='Require Finance signoff',secondary_notes='Tracker also affected')
  x=a.summarize_humans(observations(document([r])),mapping(),{})['taxonomy']['examples'][0]
  self.assertEqual(x['severity'],'material');self.assertEqual(x['minimum_repair'],'Require Finance signoff');self.assertEqual(x['secondary_issues'],'Tracker also affected')
 def test_import_snapshots_and_rejects_changed_sources(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   files={'output/submission_audit/private_review_key.json':list(mapping().values()),'output/native_workflow_01/calibration_private_key.json':[], 'output/paired_v1/runs/family__baseline__model__r1.json':{'status':'completed'},'data/paired_v1/solver/family__baseline.json':{'source':'unchanged'}}
   for rel,value in files.items():p=root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value))
   source=root/'download.json';source.write_text(json.dumps(document()))
   dest=a.import_review(source,root);self.assertEqual(a.sha(source),a.sha(dest))
   docs,errors,_=a.imported_docs(root,mapping());self.assertEqual(len(docs),1);self.assertFalse(errors)
   (root/'data/paired_v1/solver/family__baseline.json').write_text('{}')
   docs,errors,_=a.imported_docs(root,mapping());self.assertFalse(docs);self.assertIn('snapshot changed',errors[0]['reason'])
 def test_mutated_export_not_silently_loaded(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);folder=root/'reviews/assignment_final/exports';folder.mkdir(parents=True)
   p=folder/'a.json';p.write_text(json.dumps(document()))
   (folder/'a.receipt.json').write_text(json.dumps({'export_sha256':'different','reviewer_id':'human-a'}))
   docs,errors,_=a.imported_docs(root,mapping());self.assertFalse(docs);self.assertIn('bytes changed',errors[0]['reason'])

if __name__=='__main__':unittest.main()
