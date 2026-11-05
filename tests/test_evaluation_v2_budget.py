import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from run_evaluation_v2 import Client,BudgetStop,write

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.key=self.root/'key';self.key.write_text('sk-or-test-placeholder-not-a-real-key');self.key.chmod(0o600)
        self.client=Client(self.key,self.root/'run')
        self.body={'model':'openai/gpt-6.1-sol','messages':[{'role':'user','content':'test'}],'max_tokens':16000}
    def tearDown(self):self.tmp.cleanup()
    def test_reserve_unknown_charge(self):
        write(self.client.root/'calls/old/reservation.json',{'reserved_usd':1.25,'actual_cost_usd':None,'scope':'solver_primary'})
        x=self.client.totals();self.assertEqual(x['known_cost_usd'],0);self.assertEqual(x['committed_usd'],1.25);self.assertEqual(x['unresolved_requests'],1)
    def test_stop_before_transport(self):
        self.client.cfg['authorized_available_budget_usd']=.001
        with patch('run_evaluation_v2.subprocess.run') as call:
            with self.assertRaises(BudgetStop):self.client.call(self.body)
            call.assert_not_called()
    def test_solver_limit_preserves_grading(self):
        self.client.cfg['solver_ceiling_usd']=.001
        with patch('run_evaluation_v2.subprocess.run') as call:
            with self.assertRaises(BudgetStop):self.client.call(self.body,scope='solver_primary')
            call.assert_not_called()
    def test_reserve_includes_image_not_base64(self):
        b=json.loads(json.dumps(self.body));b['messages'][0]['content']=[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+'A'*100000}}]
        self.assertGreater(self.client.reservation(b),self.client.reservation(self.body))
    def test_ambiguous_failure_not_retried(self):
        with patch('run_evaluation_v2.subprocess.run',side_effect=TimeoutError('network timeout')) as call:
            with self.assertRaises(RuntimeError):self.client.call(self.body)
            self.assertEqual(call.call_count,1)
        self.assertEqual(self.client.totals()['unresolved_requests'],1)
    def test_actual_cost_settles_reserve(self):
        response={'status':200,'body':{'id':'fixture','usage':{'cost':.02}}}
        with patch('run_evaluation_v2.subprocess.run') as call:
            call.return_value.returncode=0;call.return_value.stdout=json.dumps(response)
            result,meta=self.client.call(self.body)
        self.assertEqual(self.client.totals()['known_cost_usd'],.02)
        self.assertEqual(self.client.totals()['unresolved_reserved_usd'],0)

if __name__=='__main__':unittest.main()
