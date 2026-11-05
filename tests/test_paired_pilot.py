import sys, unittest, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from score_paired_pilot import matches,score,paired_summary
from run_paired_pilot import extract_json

class PairedTests(unittest.TestCase):
    def test_bool_not_number(self):
        self.assertFalse(matches(True,1));self.assertFalse(matches(1,True));self.assertFalse(matches(float('nan'),1))
    def test_mutated_business_values_fail(self):
        for wrong,right in [(150000,110000),(84,21),(50000,5000),(110,150)]:self.assertFalse(matches(wrong,right))
    def test_missing_approver_fails(self):self.assertFalse(matches(['purchase'],['finance','program','purchase']))
    def test_missing_is_not_explicit_wrong(self):
        r={'status':'completed','final':{'facts':{}},'tool_events':[]}
        s=score(r,{'truth':{'x':1}});self.assertTrue(s['missing_decision']);self.assertFalse(s['explicit_wrong']);self.assertFalse(s['decision_pass'])
    def test_registry_not_read_does_not_imply_read(self):
        r={'status':'completed','final':{'facts':{'x':1}},'tool_events':[{'name':'read_record','arguments':{'filename':'../grader/rubrics.json'},'reply':{'error':'file_not_in_workspace'}}]}
        self.assertFalse(score(r,{'truth':{'x':1}})['read_registry'])
    def test_bootstrap_clusters_families(self):
        rows=[{'family_id':f,'trial':t,'model':'m','variant':v,'decision_pass':v=='baseline' or f=='b','eligible_for_decision_scoring':True} for f in ['a','b'] for t in [1,2] for v in ['baseline','conflict']]
        x=paired_summary(rows,'m','conflict');self.assertEqual(x['paired_families'],2);self.assertEqual(x['paired_runs'],4);self.assertEqual(x['family_mean_difference'],-.5)
    def test_original_fact_absent_in_missing_prompt_or_reference(self):
        specs=json.loads((ROOT/'data/paired_v1/grader/rubrics.json').read_text())
        for s in specs:
            r=json.loads((ROOT/'data/paired_v1/solver'/f"{s['id']}__recovery.json").read_text())
            body=r['prompt'] if s['where']=='prompt' else r['attachments'][s['where']]
            self.assertNotIn(s['old'],body);self.assertIn(s['record'],r['workspace']['record-17.txt'])
    def test_solver_has_no_gold_or_grader(self):
        for p in (ROOT/'data/paired_v1/solver').glob('*.json'):
            r=json.loads(p.read_text());self.assertNotIn('truth',r);self.assertNotIn('rubric',r);self.assertEqual(set(r['workspace']),{'registry.txt','record-17.txt','record-22.txt'})
    def test_json_rejects_nonobject(self):
        with self.assertRaises(ValueError):extract_json('[1]')
if __name__=='__main__':unittest.main()
