import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from score_human_submission_reviews import validated_rows,score

class HumanReviewTests(unittest.TestCase):
    def doc(self,row):return {'schema':'turing-human-review-v1','reviewer_id':'synthetic-test-reviewer','rows':[row]}
    def row(self):return {'review_id':'test','human_reviewed':True,'content_acceptable':'no','consequential_error':'uncertain','evaluation_defect':'no','review_minutes':None}
    def test_unreviewed_draft_never_becomes_human_label(self):
        r=self.row();r['human_reviewed']=False;self.assertEqual(validated_rows(self.doc(r),{'test'}),[])
    def test_unknown_id_rejected(self):
        with self.assertRaises(ValueError):validated_rows(self.doc(self.row()),set())
    def test_unsupported_positive_rejected(self):
        r=self.row();r['consequential_error']='yes'
        with self.assertRaises(ValueError):validated_rows(self.doc(r),{'test'})
    def test_defect_and_unknown_are_not_counted_as_agreement(self):
        r=self.row();r['evaluation_defect']='yes'
        m={'test':{'calibration_queue':True,'failure_queue':False,'family_id':'fictional','primary_judge':{'critical_error':False,'content_acceptable':False}}}
        s=score(self.doc(r),m);self.assertEqual(s['critical_agreement']['reviewed_comparable'],0);self.assertEqual(s['content_agreement']['reviewed_comparable'],0)
    def test_no_review_time_is_not_fabricated(self):
        r=self.row();m={'test':{'calibration_queue':True,'failure_queue':False,'family_id':'fictional','primary_judge':{'critical_error':False,'content_acceptable':False}}}
        s=score(self.doc(r),m);self.assertEqual(s['missing_review_times'],1);self.assertEqual(s['critical_agreement']['reviewed_comparable'],0)

if __name__=='__main__':unittest.main()
