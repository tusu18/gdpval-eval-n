import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from score_focused_reviews import score

class FocusedReviews(unittest.TestCase):
    def setUp(self):
        self.mapping = {
            'C-a': {'family_id':'f1','calibration_queue':True,'primary_judge':{'critical_error':False,'content_acceptable':True}},
            'C-b': {'family_id':'f1','calibration_queue':False},
            'N-a': {'family_id':'f2','calibration_queue':False,'new_native_queue':True,'native_output_status':'submitted'},
            'N-b': {'family_id':'f3','calibration_queue':False,'new_native_queue':True,'native_output_status':'submitted'},
        }
    def row(self, rid, **kw):
        return dict(review_id=rid,human_reviewed=True,content_acceptable='uncertain',consequential_error='uncertain',evaluation_defect='no',**kw)
    def doc(self, rows):
        return {'schema':'turing-human-review-v1','reviewer_id':'synthetic-test-only','rows':rows}
    def test_empty_is_not_acceptance(self):
        r=score(self.doc([]),self.mapping)
        self.assertEqual(r['human_completed'],0)
        self.assertIsNone(r['cohorts']['native_development']['outcomes']['content_acceptable']['yes_among_resolved_valid_cases']['value'])
    def test_uncertain_and_defects_not_resolved(self):
        a=self.row('N-a'); b=self.row('N-b');b.update(evaluation_defect='yes',content_acceptable='yes')
        r=score(self.doc([a,b]),self.mapping)['cohorts']['native_development']
        self.assertEqual(r['completed'],2)
        self.assertEqual(r['outcomes']['content_acceptable']['yes_among_resolved_valid_cases']['denominator'],0)
    def test_new_outputs_do_not_inherit_historical_judge(self):
        a=self.row('C-a');a.update(content_acceptable='yes',consequential_error='no')
        b=self.row('N-a');b.update(content_acceptable='yes',consequential_error='no')
        r=score(self.doc([a,b]),self.mapping)
        self.assertEqual(r['historical_judge_calibration']['metrics']['content_acceptable']['comparable'],1)
        self.assertIsNone(r['native_judge_agreement'])
        self.assertEqual(r['cohorts']['native_development']['completed'],1)
    def test_native_critical_requires_source_and_output(self):
        a=self.row('N-a');a['consequential_error']='yes'
        with self.assertRaises(ValueError):score(self.doc([a]),self.mapping)
    def test_drafts_do_not_become_human_reviews(self):
        a=self.row('N-a');a['human_reviewed']=False
        self.assertEqual(score(self.doc([a]),self.mapping)['human_completed'],0)
    def test_recovery_stays_out_of_initial_cohort(self):
        self.mapping['N-b']['native_stage']='recovery'
        r=score(self.doc([self.row('N-a'),self.row('N-b')]),self.mapping)
        self.assertEqual(r['cohorts']['native_development']['completed'],1)
        self.assertEqual(r['cohorts']['native_recovery']['completed'],1)
    def test_new_phases_do_not_pool_into_earlier_cohorts(self):
        self.mapping['N-a']['native_stage']='paired';self.mapping['N-b']['native_stage']='completion'
        r=score(self.doc([self.row('N-a'),self.row('N-b')]),self.mapping)
        self.assertEqual(r['cohorts']['native_development']['completed'],0)
        self.assertEqual(r['cohorts']['paired_development']['completed'],1)
        self.assertEqual(r['cohorts']['native_completion']['completed'],1)
    def test_usable_draft_cannot_be_promoted_to_completed_delivery(self):
        self.mapping['N-a']['native_output_status']='unsubmitted_draft'
        a=self.row('N-a');a.update(content_acceptable='yes',consequential_error='no')
        r=score(self.doc([a]),self.mapping)
        self.assertEqual(r['cohorts']['native_development']['completed'],0)
        self.assertEqual(r['cohorts']['native_drafts_initial_diagnostic']['completed'],1)
        self.assertIsNone(r['model_recommendation'])

if __name__ == '__main__': unittest.main()
