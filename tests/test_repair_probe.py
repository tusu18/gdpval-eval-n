import copy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import run_repair_probe as probe

class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.legacy=self.base/'legacy.json';probe.write(self.legacy,[{'charged_or_reserved':4.391054}])
        self.body={'max_tokens':9000,'messages':[{'role':'user','content':'hello'}]}
    def tearDown(self):self.tmp.cleanup()
    def budget(self,**kwargs):return probe.CampaignBudget(self.base/'probe',legacy_paths=[self.legacy],**kwargs)
    def test_campaign_cap_includes_existing_study(self):
        probe.write(self.legacy,[{'charged_or_reserved':24.99}]);b=self.budget()
        with self.assertRaises(probe.BudgetStop):b.reserve('x',self.body)
        self.assertEqual(len(b.rows),0)
    def test_stage_cap_is_enforced(self):
        b=self.budget(stage=.1)
        with self.assertRaises(probe.BudgetStop):b.reserve('x',self.body)
    def test_reservation_refunds_to_reported_cost(self):
        b=self.budget();i=b.reserve('x',self.body);b.settle(i,{'usage':{'cost':.005}})
        self.assertEqual(b.exposure(),Decimal('.005'))
    def test_timeout_keeps_full_reservation(self):
        b=self.budget();i=b.reserve('x',self.body);before=b.exposure();b.settle(i,error=TimeoutError())
        self.assertEqual(before,b.exposure());self.assertEqual(b.rows[i]['status'],'unresolved_charge_reserved')
    def test_only_proven_predispatch_rejection_releases_charge(self):
        b=self.budget();i=b.reserve('x',self.body);b.settle(i,error=probe.APIError('rejected',pre_dispatch=True))
        self.assertEqual(b.exposure(),0)
        j=b.reserve('y',self.body);b.settle(j,error=probe.APIError('unknown HTTP 402'))
        self.assertGreater(b.exposure(),0)
    def test_unknown_or_nonfinite_cost_stays_reserved(self):
        for value in [None,float('nan'),-1,True,'0.1']:
            b=self.budget();i=b.reserve('x',self.body);old=b.rows[i]['reservation_usd'];b.settle(i,{'usage':{'cost':value}})
            self.assertEqual(b.rows[i]['charged_or_reserved'],old)
    def test_concurrent_reservations_cannot_overspend(self):
        b=self.budget(stage=.30)
        def reserve(n):
            try:return b.reserve(str(n),self.body)
            except probe.BudgetStop:return None
        with ThreadPoolExecutor(max_workers=8) as p:list(p.map(reserve,range(20)))
        self.assertLessEqual(b.exposure(),Decimal('.30'))
        self.assertGreater(len(b.rows),0)
    def test_legacy_cost_is_reread_before_dispatch(self):
        b=self.budget();b.reserve('x',self.body);probe.write(self.legacy,[{'charged_or_reserved':24.99}])
        with self.assertRaises(probe.BudgetStop):b.reserve('y',self.body)
    def test_request_limits_apply_before_reservation(self):
        b=self.budget()
        for body in [{'max_tokens':9001},{'max_tokens':True},{'max_tokens':9000,'content':'x'*130000}]:
            with self.assertRaises(probe.BudgetStop):b.reserve('x',body)
        self.assertEqual(b.rows,[])
    def test_catalog_cannot_silently_raise_prices(self):
        catalog={'data':[{'id':'m','pricing':{'prompt':'0.000003','completion':'0.00001'},'supported_parameters':['tools']}]}
        with self.assertRaises(RuntimeError):probe.validate_catalog(catalog,['m'])
    def test_all_sixteen_cells_preserve_pairing(self):
        cfg=probe.read(ROOT/'config/repair_probe_01.json')
        self.assertEqual(len(cfg['jobs']),16)
        cells={}
        for j in cfg['jobs']:cells.setdefault((j['family_id'],j['model'],j['trial']),set()).add(j['arm'])
        self.assertEqual(len(cells),8);self.assertTrue(all(x=={'baseline','evidence_check'} for x in cells.values()))
    def test_raw_bad_output_preserved_without_retry(self):
        cfg=probe.read(ROOT/'config/repair_probe_01.json');job=cfg['jobs'][0];b=self.budget();calls=[]
        def fake(path,key,body):
            calls.append(body)
            return {'usage':{'cost':.001},'choices':[{'finish_reason':'length','message':{'content':'{"unfinished":'}}]}
        with patch.object(probe,'BASE',self.base/'probe'):
            r=probe.run_one(job,'fake-test-credential',b,cfg,transport=fake)
            self.assertEqual(r['status'],'protocol_or_output_error');self.assertEqual(r['finish_reason'],'length');self.assertEqual(len(r['calls']),1)
            probe.run_one(job,'fake-test-credential',b,cfg,transport=fake)
        self.assertEqual(len(calls),1)
    def test_tool_attempt_cannot_read_grader(self):
        cfg=probe.read(ROOT/'config/repair_probe_01.json');job=cfg['jobs'][0];b=self.budget();calls=[]
        def fake(path,key,body):
            calls.append(body)
            if len(calls)==1:
                return {'usage':{'cost':.001},'choices':[{'finish_reason':'tool_calls','message':{'content':None,'tool_calls':[{'id':'t1','type':'function','function':{'name':'read_file','arguments':'{"path":"../grader/rubrics.json"}'}}]}}]}
            return {'usage':{'cost':.001},'choices':[{'finish_reason':'stop','message':{'content':'{"facts":{},"artifacts":[]}'}}]}
        with patch.object(probe,'BASE',self.base/'probe'):r=probe.run_one(job,'fake-test-credential',b,cfg,transport=fake)
        self.assertIn('error',r['tool_events'][0]['reply'])
        self.assertNotIn('rubric',calls[1]['messages'][-1]['content'])

if __name__=='__main__':unittest.main()
