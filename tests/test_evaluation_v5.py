import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from judge_aggregation_v5 import aggregate,ELIGIBLE
from evidence_grader_v2 import score_judgment
from validate_evaluation_v5 import inspect
class V5Tests(unittest.TestCase):
 def fixture(self):
  p={'source_documents':{'s':'Finance approval required'},'artifacts':[{'id':'a','units':[{'locator':'p1','text':'Finance approval required'},{'locator':'p2','text':'Wait for Finance'}]}], 'requirements':[{'id':'r','critical':True,'operative_sections':[{'artifact_id':'a','locator':'p1'},{'artifact_id':'a','locator':'p2'}]}]}
  ev=[{'source_id':'s','source_quote':'Finance approval required','artifact_id':'a','output_quote':x} for x in ['Finance approval required','Wait for Finance']]
  j={'requirements':[{'id':'r','stated':{'status':'pass','evidence':ev},'honored':{'status':'pass','evidence':ev}}],'operative_sections_inspected':[{'artifact_id':'a','locator':'p1','section':'rule','quote':'Finance approval required'},{'artifact_id':'a','locator':'p2','section':'action','quote':'Wait for Finance'}],'task_fulfillment':{'status':'pass'},'task_defect':{'status':'no','reason':'clear'}}
  return p,j
 def test_complete(self):
  p,j=self.fixture();self.assertTrue(score_judgment(p,j)['content_acceptable'])
 def test_missing_section(self):
  p,j=self.fixture();j['operative_sections_inspected'].pop();self.assertIsNone(score_judgment(p,j)['content_acceptable'])
 def test_forged_locator(self):
  p,j=self.fixture();j['operative_sections_inspected'][1]['locator']='p1';self.assertEqual(score_judgment(p,j)['status'],'invalid_grader_evidence')
 def test_duplicate(self):
  p,j=self.fixture();j['requirements']*=2;self.assertEqual(score_judgment(p,j)['status'],'invalid_grader_evidence')
 def test_unknown_excluded(self):
  rows=[{'run_id':'x','judge':j,'status':'received','assessment':{'status':s,'content_acceptable':v,'consequential_error':v}} for j,s,v in [('a',ELIGIBLE,False),('b','task_defect_or_uncertainty',None)]]
  d=aggregate(rows);self.assertEqual(d['comparisons']['consequential_error']['eligible_pairs'],0);self.assertEqual(d['per_judge']['b']['endpoints']['content_acceptable']['unknown'],1)
 def test_acceptance_disagreement(self):
  rows=[{'run_id':'x','judge':j,'status':'received','assessment':{'status':ELIGIBLE,'content_acceptable':v,'consequential_error':False}} for j,v in [('a',True),('b',False)]]
  d=aggregate(rows);self.assertEqual(len(d['comparisons']['content_acceptable']['disagreements']),1);self.assertEqual(d['comparisons']['consequential_error']['agree'],1)
 def test_missing_chunk_unknown(self):
  rows=[{'run_id':'x','judge':'a','status':'received','assessment':{'status':ELIGIBLE,'content_acceptable':True,'consequential_error':False}},{'run_id':'x','judge':'a','status':'execution_error'}]
  self.assertIsNone(aggregate(rows)['per_run']['x']['a']['content_acceptable'])
 def test_preparation_and_gate(self):
  d=inspect();self.assertTrue(d['checks_pass'],d);self.assertFalse(d['ready_for_judges']);self.assertEqual(len(d['pending_human_fields']),30)
if __name__=='__main__':unittest.main()
