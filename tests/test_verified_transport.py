import json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_verified_transport_study as transport
class VerifiedTransportTests(unittest.TestCase):
    def test_identical_network_retry_records_extra_uncertain_charge(self):
        with tempfile.TemporaryDirectory() as d:
            transport.CURRENT_OUT=Path(d)
            responses=[SimpleNamespace(returncode=1,stderr='EPIPE; write EPIPE',stdout=''),SimpleNamespace(returncode=0,stderr='',stdout='{"id":"synthetic"}')]
            with patch.object(transport.subprocess,'run',side_effect=responses) as call,patch.object(transport.time,'sleep'):
                self.assertEqual(transport.api('x'*40,'chat/completions',{'model':'synthetic','messages':[]})['id'],'synthetic')
                self.assertEqual(call.call_args_list[0].kwargs['input'],call.call_args_list[1].kwargs['input'])
            events=[json.loads(x) for x in (Path(d)/'transport_events.jsonl').read_text().splitlines()]
            self.assertEqual(sum(e['extra_unresolved_charge_record'] for e in events),1)
            self.assertNotIn('x'*40,(Path(d)/'transport_events.jsonl').read_text())
    def test_credit_rejection_is_never_retried(self):
        with tempfile.TemporaryDirectory() as d:
            transport.CURRENT_OUT=Path(d)
            with patch.object(transport.subprocess,'run',return_value=SimpleNamespace(returncode=1,stderr='OpenRouter HTTP 402',stdout='')) as call:
                with self.assertRaises(RuntimeError):transport.api('x'*40,'chat/completions',{'model':'synthetic'})
                self.assertEqual(call.call_count,1)
    def test_pair_amendment_predates_all_outcomes(self):
        root=Path(__file__).resolve().parents[1]
        self.assertFalse(list((root/'output/paired_native_04/runs').glob('*.json')))
        cfg=json.loads((root/'config/paired_native_08.json').read_text())
        self.assertEqual(len(cfg['jobs']),10)
        self.assertEqual({j['model'] for j in cfg['jobs']},{'anthropic/claude-opus-5.5'})
if __name__=='__main__':unittest.main()
