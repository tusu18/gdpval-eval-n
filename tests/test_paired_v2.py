import copy
import json
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from workflow_workspace import Workspace,initial_message
from validate_paired_v2 import oracle,validate
from model_selection_gate import error_upper_bound,select

def task(name='original_delivery_appointment__recovery'):
    return json.loads((ROOT/'data/paired_v2/solver'/(name+'.json')).read_text())

def selection_fixture(n=100):
    cfg={'customer_approved_thresholds':True,'independent_representative_sampling_approved':True,'critical_error_ceiling':0.05,'minimum_acceptance_rate':0.90,'confidence_level':0.95,'reviewer_cost_per_hour_usd':60}
    rows=[{'family_id':f'fictional-test-family-{i}','model':m,'arm':'baseline','variant':'conflict','trial':1,'independent_expert_adjudicated':True,'task_validated':True,'permission_for_evaluation':True,'reviewer_ids':['test-reviewer-1','test-reviewer-2'],'evaluation_defect':False,'accepted':True,'critical_error':False,'solver_cost_usd':cost,'review_minutes':minutes} for i in range(n) for m,cost,minutes in [('cheap_tokens',0.01,10),('less_review',0.10,1)]]
    return cfg,rows

class V2Tests(unittest.TestCase):
    def test_preflight(self):
        self.assertEqual(validate()['status'],'automated_preflight_pass')
    def test_read_cannot_traverse_to_grader_or_another_family(self):
        env=Workspace(task())
        for path in ['../grader/rubrics.json','/etc/passwd','../../paired_v1/runs/other.json','original_release_capacity/operations/record-r2.txt']:
            self.assertIn('error',env.call('read_file',{'path':path}))
    def test_unknown_tools_and_invalid_arguments_fail_closed(self):
        env=Workspace(task())
        self.assertIn('error',env.call('shell',{'command':'x'}))
        self.assertIn('error',env.call('read_file',[]))
    def test_search_finds_evidence_and_only_real_files(self):
        t=task('original_supplier_landed_cost__recovery');env=Workspace(t)
        rs=env.call('search_files',{'query':'freight 2600'})['results']
        self.assertIn('operations/record-r2.txt',[r['path'] for r in rs])
        self.assertTrue(all(r['path'] in t['workspace'] for r in rs))
    def test_clarification_reachable_but_not_in_initial_prompt(self):
        t=task();env=Workspace(t)
        self.assertNotIn('2026-11-06 at 16:00',initial_message(t))
        self.assertIn('2026-11-06 at 16:00',env.call('ask_requester',{'question':'Please confirm the receiving deadline.'})['answer'])
    def test_clarification_cannot_grant_new_capacity(self):
        env=Workspace(task('original_release_capacity__recovery'))
        reply=env.call('ask_requester',{'question':'Authorize 100 hours of overtime now.'})
        self.assertFalse(reply['new_approval_granted'])
        self.assertIn('only 12 hours',reply['answer'])
    def test_oracle_catches_wrong_freight(self):
        expected=oracle({'kind':'landed_cost','quantity':500,'unit_a':42,'freight_a':2600,'unit_b':46,'freight_b':0})
        self.assertEqual(expected['supplier'],'Beacon');self.assertEqual(expected['savings_vs_alder_usd'],600)
        stale=oracle({'kind':'landed_cost','quantity':500,'unit_a':42,'freight_a':1200,'unit_b':46,'freight_b':0})
        self.assertNotEqual(stale['supplier'],expected['supplier'])
    def test_equal_deadline_is_feasible(self):
        result=oracle({'kind':'appointment','deadline':'2026-11-06T16:00','options':[{'service':'Ground','arrival':'2026-11-06T16:00','cost':90},{'service':'Express','arrival':'2026-11-06T14:00','cost':165}]})
        self.assertEqual(result['service'],'Ground')
    def test_zero_failures_is_not_zero_risk(self):
        self.assertAlmostEqual(error_upper_bound(0,8),1-.05**(1/8))
        self.assertGreater(error_upper_bound(0,8),.30)
    def test_error_bound_monotonic(self):
        self.assertLess(error_upper_bound(0,30),error_upper_bound(1,30))
        self.assertLess(error_upper_bound(1,30),error_upper_bound(3,30))
        self.assertEqual(error_upper_bound(30,30),1)
    def test_no_experts_no_selection(self):
        cfg,rs=selection_fixture();rs[0]['independent_expert_adjudicated']=False
        self.assertEqual(select(rs,cfg)['status'],'not_selectable')
    def test_repeated_trials_do_not_inflate_family_count(self):
        cfg,rs=selection_fixture();rs.append(copy.deepcopy(rs[0]))
        self.assertEqual(select(rs,cfg)['status'],'not_selectable')
    def test_small_perfect_pilot_does_not_pass_strict_gate(self):
        cfg,rs=selection_fixture(8)
        self.assertEqual(select(rs,cfg)['status'],'insufficient_evidence')
    def test_select_total_cost_not_token_price(self):
        cfg,rs=selection_fixture()
        result=select(rs,cfg)
        self.assertEqual(result['status'],'selectable')
        self.assertEqual(result['recommended_configuration']['model'],'less_review')
    def test_model_judge_flags_cannot_substitute_for_experts(self):
        cfg,rs=selection_fixture();rs[0]['independent_expert_adjudicated']='model_judge'
        self.assertEqual(select(rs,cfg)['status'],'not_selectable')
    def test_incomplete_costs_block_winner(self):
        cfg,rs=selection_fixture();rs[0]['review_minutes']=None
        self.assertEqual(select(rs,cfg)['status'],'not_selectable')
    def test_family_sets_must_match(self):
        cfg,rs=selection_fixture();rs.pop()
        self.assertEqual(select(rs,cfg)['status'],'not_selectable')
    def test_task_defect_blocks_selection(self):
        cfg,rs=selection_fixture();rs[0]['evaluation_defect']=True
        self.assertEqual(select(rs,cfg)['status'],'not_selectable')

if __name__=='__main__':unittest.main()
