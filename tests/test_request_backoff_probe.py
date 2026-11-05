import json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_request_backoff_probe as probe

class RequestBackoffProbe(unittest.TestCase):
    def test_same_payload_after_provider_directed_wait(self):
        error='OpenRouter HTTP 402: {"reason":"in_flight_budget_exhausted"}'
        replies=[SimpleNamespace(returncode=1,stderr=error,stdout=''),SimpleNamespace(returncode=0,stderr='',stdout='{"id":"simulated-only"}')]
        with tempfile.TemporaryDirectory() as tmp,patch.object(probe,'CURRENT_OUT',Path(tmp)),patch.object(probe.subprocess,'run',side_effect=replies) as dispatch,patch.object(probe,'pause') as pause:
            key='synthetic-test-key-not-an-api-credential'
            result=probe.api(key,'chat/completions',{'model':'synthetic-model','messages':[]})
            self.assertEqual(result['id'],'simulated-only');pause.assert_called_once_with(120)
            self.assertEqual(dispatch.call_args_list[0].kwargs['input'],dispatch.call_args_list[1].kwargs['input'])
            raw=(Path(tmp)/'transport_events.jsonl').read_text();self.assertNotIn(key,raw)
            events=[json.loads(x) for x in raw.splitlines()]
            self.assertEqual(sum(e['extra_unresolved_charge_record'] for e in events),1)
            self.assertEqual(events[0]['request_sha256'],events[1]['request_sha256'])
    def test_retries_are_bounded(self):
        error='OpenRouter HTTP 429: {"limit_source":"openrouter_admission_control","Retry-After":"10"}'
        with tempfile.TemporaryDirectory() as tmp,patch.object(probe,'CURRENT_OUT',Path(tmp)),patch.object(probe.subprocess,'run',return_value=SimpleNamespace(returncode=1,stderr=error,stdout='')) as dispatch,patch.object(probe,'pause') as pause:
            with self.assertRaises(RuntimeError):probe.api('synthetic-key','chat/completions',{'model':'synthetic-model'})
            self.assertEqual(dispatch.call_count,3);self.assertEqual(pause.call_count,2)
    def test_auth_credit_and_certificate_failures_are_not_bypassed(self):
        for message in ('OpenRouter HTTP 401','OpenRouter HTTP 403','OpenRouter HTTP 402: insufficient balance','CERT_HAS_EXPIRED','UNABLE_TO_VERIFY_LEAF_SIGNATURE'):
            self.assertIsNone(probe.retry_delay(message,0))
        self.assertEqual(probe.retry_delay('ERR_SSL_SSL/TLS_ALERT_BAD_RECORD_MAC',0),2)
        self.assertIsNone(probe.retry_delay('ERR_SSL_SSL/TLS_ALERT_BAD_RECORD_MAC',1))
        self.assertEqual(probe.retry_delay('OpenRouter HTTP 402: {"reason":"in_flight_budget_exhausted","Retry-After":"180"}',0),180)
        self.assertIsNone(probe.retry_delay('OpenRouter HTTP 402: {"reason":"in_flight_budget_exhausted","Retry-After":"600"}',0))

if __name__=='__main__':unittest.main()
