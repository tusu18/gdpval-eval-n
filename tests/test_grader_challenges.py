from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_grader_challenges import build

class GraderChallengeTests(unittest.TestCase):
    def test_same_facts_can_hide_changed_actions(self):
        cases,keys=build()
        for i in range(0,len(cases),2):
            a,b=cases[i:i+2]
            self.assertEqual(a['submission']['facts'],b['submission']['facts'])
            self.assertEqual(a['workspace'],b['workspace'])
            self.assertNotEqual(a['submission']['deliverable_text'],b['submission']['deliverable_text'])
            self.assertNotEqual(keys[i]['expected_content_acceptable'],keys[i+1]['expected_content_acceptable'])
    def test_unnecessary_hold_is_not_automatically_honesty_error(self):
        _,keys=build();k=next(k for k in keys if k['id']=='unnecessary_hold__mutated')
        self.assertFalse(k['expected_consequential_error']);self.assertTrue(k['expected_unnecessary_hold'])
        self.assertFalse(k['expected_content_acceptable'])
    def test_no_human_gold_is_invented(self):
        _,keys=build();self.assertFalse(any(k['human_validated'] for k in keys))

if __name__=='__main__':unittest.main()
