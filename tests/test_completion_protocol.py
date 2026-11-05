import importlib.util,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from run_completion_and_pairs import infrastructure_error

class CompletionProtocolTests(unittest.TestCase):
    def test_budget_failure_is_not_infrastructure_retry(self):
        self.assertFalse(infrastructure_error({'status':'turn_limit'}))
        self.assertFalse(infrastructure_error({'status':'submitted'}))
        self.assertTrue(infrastructure_error({'status':'execution_error','error':'OpenRouter HTTP 402'}))

    def test_completion_preserves_original_runs_and_excludes_successes(self):
        cfg=json.loads((ROOT/'config/native_completion_03.json').read_text())
        self.assertEqual(len(cfg['jobs']),12)
        for j in cfg['jobs']:
            self.assertNotEqual(j['run_id'],j['parent_run_id'])
            p=ROOT/'output/native_transport_02/runs'/(j['parent_run_id']+'.json')
            if p.exists():self.assertTrue(infrastructure_error(json.loads(p.read_text())))

    def test_each_paired_family_has_same_model_and_contract(self):
        cfg=json.loads((ROOT/'config/paired_native_04.json').read_text())
        maps={m['instance_id']:m for m in json.loads((ROOT/'data/evidence_upgrade_01/grader/evidence_maps.json').read_text())}
        self.assertEqual({j['model'] for j in cfg['jobs']},{'anthropic/claude-opus-5.5'})
        families={j['family_id'] for j in cfg['jobs']};self.assertEqual(len(families),5)
        for family in families:
            jobs=[j for j in cfg['jobs'] if j['family_id']==family]
            self.assertEqual({j['condition'] for j in jobs},{'baseline','conflict'})
            self.assertEqual(maps[jobs[0]['instance_id']]['deliverable_contract'],maps[jobs[1]['instance_id']]['deliverable_contract'])

    def test_transport_verifies_tls_and_disallows_redirect(self):
        text=(ROOT/'scripts/openrouter_transport_v3.mjs').read_text()
        self.assertIn("redirect: 'error'",text)
        self.assertNotIn('rejectUnauthorized',text)
        self.assertNotIn('NODE_TLS_REJECT_UNAUTHORIZED',text)

if __name__=='__main__':unittest.main()
