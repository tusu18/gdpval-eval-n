"""Fail-closed gates and bounded inspection; never imports model credentials."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import inspection_pilot_13 as p


def fixture(root):
    case={'case_id':'R-test','packet':'data/packet.json','artifact':'data/workbook.xlsx'}
    packet={'source_documents':{'request':'Finance approval is required.'},
            'criteria':[{'id':'authority','critical':True,'requirement':'Preserve Finance approval.'}],
            'artifacts':[{'id':'workbook.xlsx','units':[{'locator':'sheet1:A1','text':'Finance approval is required.'}]}],
            'expected_target_check_pass':True,'human_validation':'author_expected_only'}
    p.write(root/case['packet'],packet);(root/case['artifact']).write_bytes(b'test-only-artifact')
    img='output/strengthening_13/image.png';p.write(root/img,{'test_image':True})
    rec='output/strengthening_13/recalc.json'
    p.write(root/rec,{'sheets':[{'name':'Shipment Manifest','range':'A1:I6',
        'values':[[0]*9 for _ in range(6)],'formulas':[['']*9 for _ in range(6)]}]})
    config={'cases':[case],'model':'local-test','max_tokens':100,'reasoning_effort':'medium','provider':{},
            'system_prompt':p.SYSTEM,'inspection':[{'case_id':'R-test','render_engine':'test','scope':'test',
                'recalculation':rec,'images':[{'path':img,'label':'test'}]}],
            'input_hashes':{r:p.sha(root/r) for r in (case['packet'],case['artifact'])},
            'human_review_path':str(p.REVIEW),'max_tool_calls_per_response':8,
            'max_request_bytes':1000000,'max_total_requests':24,'execution_enabled':False,
            'jobs':[{'id':'R-test__C_agentic','case_id':'R-test','arm':'C_agentic','max_model_requests':4}]}
    p.write(root/p.CFG,config)
    return config


def response(content=None, calls=None):
    return {'choices':[{'message':{'content':content,'tool_calls':calls or []}}]}


def tool_response(name,args):
    return response(calls=[{'id':'t','type':'function','function':{'name':name,'arguments':json.dumps(args)}}])


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.config=fixture(self.root)
    def tearDown(self):self.temp.cleanup()

    def test_A_excludes_images_and_B_C_start_identically_without_labels(self):
        a=p.materialize(self.config,'R-test','A_text',self.root,False)
        b=p.materialize(self.config,'R-test','B_fixed_inspection',self.root,False)
        c=p.materialize(self.config,'R-test','C_agentic',self.root,False)
        self.assertEqual(b['messages'],c['messages']);self.assertNotIn('tools',a);self.assertIn('tools',c)
        self.assertEqual(len(a['messages'][1]['content']),1)
        self.assertNotIn('expected_target_check_pass',json.dumps(c))
        self.assertNotIn('author_expected_only',json.dumps(c))

    def test_allowlist_denies_paths_and_malformed_ranges(self):
        inspector=p.Inspector(self.config,'R-test',self.root)
        for name,args in [('open_evidence',{'id':'../../private/author_key.json'}),
                          ('read_cells',{'sheet':'Shipment Manifest','range':123}),
                          ('read_cells',{'sheet':'Shipment Manifest','range':'J1:K2'}),
                          ('write_file',{})]:
            with self.assertRaises(ValueError):inspector.call(name,args)

    def test_four_request_limit_with_no_retry_or_extra_tool_dispatch(self):
        seen=[]
        def fake(payload):seen.append(payload);return tool_response('open_evidence',{'id':'request'})
        result=p.run_session(self.config,self.config['jobs'][0],fake,self.root,True)
        self.assertEqual(len(seen),4);self.assertEqual(result['status'],'unexpected_tool_call')
        self.assertNotIn('tools',seen[-1]);self.assertEqual(len(result['tool_events']),3)
        self.assertEqual(result['model_requests'],0)

    def test_malformed_tool_args_record_error_then_can_finish(self):
        seen=[]
        def fake(payload):
            seen.append(payload)
            return tool_response('read_cells',{'sheet':'Shipment Manifest','range':123}) if len(seen)==1 else response('{}')
        result=p.run_session(self.config,self.config['jobs'][0],fake,self.root,True)
        self.assertEqual(result['status'],'received');self.assertIn('error',result['tool_events'][0]['result'])

    def test_transport_failure_is_one_attempt_and_unknown_charge(self):
        def fake(payload):raise TimeoutError('test failure')
        with patch.object(p,'validate_live',return_value=None):
            result=p.run_session(self.config,self.config['jobs'][0],fake,self.root)
        self.assertEqual(result['model_requests'],1);self.assertEqual(result['unresolved_charge_records'],1)
        records=list((self.root/p.OUT/'inspection-requests').glob('*.json'))
        self.assertEqual(len(records),1);self.assertEqual(p.read(records[0])['status'],'transport_error')

    def test_interruption_is_journaled_and_resume_refuses_replay(self):
        def interrupted(payload):raise KeyboardInterrupt()
        with patch.object(p,'validate_live',return_value=None):
            with self.assertRaises(KeyboardInterrupt):p.run_session(self.config,self.config['jobs'][0],interrupted,self.root)
            with self.assertRaisesRegex(ValueError,'reconciliation'):p.run_live(self.root)
        records=list((self.root/p.OUT/'inspection-requests').glob('*.json'))
        self.assertEqual(len(records),1);self.assertEqual(p.read(records[0])['status'],'started')

    def test_campaign_request_bound_stops_before_transport(self):
        folder=self.root/p.OUT/'inspection-requests'
        for i in range(24):p.write(folder/f'{i}.json',{'status':'started'})
        with patch.object(p,'validate_live',return_value=None):
            result=p.run_session(self.config,self.config['jobs'][0],lambda _:self.fail('Should not dispatch'),self.root)
        self.assertEqual(result['status'],'campaign_request_limit');self.assertEqual(result['model_requests'],0)

    def test_valid_judgment_has_eligibility_without_inferred_human_or_native_acceptance(self):
        packet=p.sanitized_packet(p.read(self.root/'data/packet.json'))
        judgment={'criteria':[{'id':'authority','status':'pass','rationale':'test',
            'evidence_kind':'quoted','evidence':[{'source_id':'request','source_quote':'Finance approval',
                'artifact_id':'workbook.xlsx','output_quote':'Finance approval'}]}],
            'task_defect':{'status':'no','reason':'test'},
            'inspection_checks':{'visual':'unknown','recalculation':'unknown','reason':'Only text supplied.'}}
        result=p.validate_judgment(packet,judgment)
        self.assertEqual(result['raw']['status'],'automated_assessment_not_human_acceptance')
        self.assertNotIn('package_acceptable',result['raw']);self.assertNotIn('human_accepted',result['raw'])
        self.assertTrue(result['raw_comparison_eligible'])
        judgment['inspection_checks']['visual']='pass'
        unsupported=p.validate_judgment(packet,judgment)
        self.assertFalse(unsupported['raw_comparison_eligible'])
        self.assertIn('visual_claim_without_render_evidence',unsupported['inspection_metadata_errors'])
        judgment.pop('inspection_checks')
        missing=p.validate_judgment(packet,judgment)
        self.assertIn('missing_inspection_checks',missing['inspection_metadata_errors'])

    def _reviews(self):
        row={'case_id':'R-test','task_adequate':'yes','target_check':'pass',
             'whole_output_acceptance':'accept','consequential_error':'no'}
        p.write(self.root/p.REVIEW,{'reviewer':'actual_user','case_reviews':[row]})
        for index,key in enumerate(p.ENDPOINTS):
            p.write(self.root/p.REVIEW.parent/'responses'/f'{index}.json',{
                'case_id':'R-test','reviewer':'actual_user','endpoint':key,'normalized_label':row[key],
                'received_at':'2026-11-04T01:00:00Z','answer_verbatim':'Actual answer',
                'source_hashes':self.config['input_hashes']})
        return row

    def test_no_human_labels_and_outstanding_followup_block_execution(self):
        self.assertFalse(p.human_gate(self.root,self.config)['ready'])
        row=self._reviews();self.assertTrue(p.human_gate(self.root,self.config)['ready'])
        row['outstanding_followup']=True
        p.write(self.root/p.REVIEW,{'reviewer':'actual_user','case_reviews':[row]})
        self.assertFalse(p.human_gate(self.root,self.config)['ready'])

    def test_latest_explicit_response_supersedes_stale_label(self):
        self._reviews()
        p.write(self.root/p.REVIEW.parent/'responses'/'new.json',{'case_id':'R-test','reviewer':'actual_user',
            'endpoint':'target_check','normalized_label':'fail','received_at':'2026-11-04T02:00:00Z',
            'answer_verbatim':'Revised to fail','source_hashes':self.config['input_hashes']})
        self.assertFalse(p.human_gate(self.root,self.config)['ready'])

    def test_whitespace_quote_cannot_qualify_as_raw_pilot_evidence(self):
        packet=p.sanitized_packet(p.read(self.root/'data/packet.json'))
        judgment={'criteria':[{'id':'authority','status':'pass','rationale':'test',
            'evidence_kind':'quoted','evidence':[{'source_id':'request','source_quote':'Finance approval',
                'artifact_id':'workbook.xlsx','output_quote':' '}]}],
            'task_defect':{'status':'no','reason':'test'},
            'inspection_checks':{'visual':'unknown','recalculation':'unknown','reason':'Only text.'}}
        result=p.validate_judgment(packet,judgment)
        self.assertFalse(result['raw_comparison_eligible'])
        self.assertIn('authority:empty_output_quote',result['raw']['errors'])


if __name__=='__main__':unittest.main()
