import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from score_current_calibration import score
class CurrentCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.mapping={'C-1':{'family_id':'f','calibration_queue':True,'primary_judge':{'content_acceptable':True,'critical_error':False}}}
        self.doc={'schema':'turing-human-review-v1','reviewer_id':'synthetic-test-only','rows':[{'review_id':'C-1','human_reviewed':True,'content_acceptable':'no','consequential_error':'yes','evaluation_defect':'no','output_evidence':'Synthetic test evidence','source_and_consequence':'Synthetic test source and consequence'}]}
    def test_missing_new_judge_is_not_backfilled(self):
        r=score(self.doc,self.mapping,{})['results']['metrics']['consequential_error']
        self.assertEqual(r['comparable'],0)
        self.assertEqual(r['exclusions']['missing_judge_label'],1)
        self.assertIsNotNone(self.mapping['C-1']['primary_judge'])
    def test_invalid_evidence_does_not_count_as_detection(self):
        j={'C-1':{'status':'received','assessment':{'status':'invalid_grader_evidence','consequential_error':True}}}
        self.assertEqual(score(self.doc,self.mapping,j)['results']['metrics']['consequential_error']['comparable'],0)
    def test_missed_error_count_uses_actual_human_label(self):
        j={'C-1':{'status':'received','assessment':{'status':'automated_assessment_not_human_acceptance','consequential_error':False,'content_acceptable':True}}}
        r=score(self.doc,self.mapping,j)['results']['metrics']
        self.assertEqual(r['consequential_error']['matrix']['human_yes_judge_no'],1)
        self.assertEqual(r['content_acceptable']['false_accepts_among_judge_accepts']['numerator'],1)
if __name__=='__main__':unittest.main()
