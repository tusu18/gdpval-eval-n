import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_judge_gap_14 import aggregate


class JudgeGapTests(unittest.TestCase):
    def test_grouping_uses_generator_and_excludes_missing_judgments(self):
        runs={'a':{'model':'generator_a'},'b':{'model':'generator_b'},'missing':{'model':'generator_b'}}
        records=[{'run_id':'a','judge_model':'generator_a','judgment':{'content_acceptable':True,'critical_error':False}},
                 {'run_id':'b','judge_model':'generator_a','judgment':{'content_acceptable':False,'critical_error':True}}]
        counts=aggregate(records,runs)
        self.assertEqual(counts['generator_a'],{'judged':1,'accepted':1,'rejected':0,'critical_error':0})
        self.assertEqual(counts['generator_b'],{'judged':1,'accepted':0,'rejected':1,'critical_error':1})

    def test_unknown_verdict_cannot_become_a_negative_or_silent_denominator(self):
        for value in (None,'false','uncertain'):
            with self.assertRaises(ValueError):
                aggregate([{'run_id':'r','judgment':{'content_acceptable':value,'critical_error':False}}],{'r':{'model':'m'}})


if __name__=='__main__':unittest.main()
