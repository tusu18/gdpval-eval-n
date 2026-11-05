import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_human_reviews import compare,reviewer_metrics,interval

class ReviewComparisonTests(unittest.TestCase):
    def setUp(self):
        self.mapping={str(i):{'family_id':f'family-{i%2}','calibration_queue':True,'failure_queue':True,
                           'primary_judge':{'critical_error':False,'content_acceptable':True}} for i in range(4)}
        self.a={'schema':'turing-human-review-v1','reviewer_id':'synthetic-A','rows':[
            {'review_id':str(i),'human_reviewed':True,'evaluation_defect':'no','content_acceptable':'yes',
             'consequential_error':'no','category':'no_issue','review_minutes':None} for i in range(4)]}
        self.b=copy.deepcopy(self.a);self.b['reviewer_id']='synthetic-B'
    def test_shared_negatives_do_not_validate_sensitivity(self):
        r=reviewer_metrics(self.a,self.mapping)['metrics']['consequential_error']
        self.assertEqual(r['agreement']['numerator'],4)
        self.assertIsNone(r['error_sensitivity']['value'])
        self.assertIsNone(r['agreement_uncertainty']['interval_95'])
    def test_false_accept_denominator_is_judge_accepts(self):
        self.a['rows'][0]['content_acceptable']='no'
        r=reviewer_metrics(self.a,self.mapping)['metrics']['content_acceptable']
        self.assertEqual(r['false_accepts_among_judge_accepts'],{'numerator':1,'denominator':4,'value':.25})
    def test_missed_material_error_has_positive_case_denominator(self):
        self.a['rows'][0].update(consequential_error='yes', content_acceptable='no',
            output_evidence='Synthetic test output: release now.',
            source_and_consequence='Synthetic test policy: approval missing; release violates the gate.')
        r=reviewer_metrics(self.a,self.mapping)['metrics']['consequential_error']
        self.assertEqual(r['error_sensitivity'],{'numerator':0,'denominator':1,'value':0})
        self.assertEqual(r['missed_error_fraction'],{'numerator':1,'denominator':1,'value':1})
    def test_unreviewed_rows_do_not_enter_overlap(self):
        self.b['rows'][1]['human_reviewed']=False
        r=compare(self.a,self.b,self.mapping)
        self.assertEqual(r['shared_completed_attempts'],3);self.assertEqual(r['only_first_reviewed'],['1'])
    def test_uncertainty_is_retained_in_reviewer_disagreement(self):
        self.b['rows'][0]['evaluation_defect']='uncertain'
        r=compare(self.a,self.b,self.mapping)
        self.assertEqual(r['inter_rater']['evaluation_defect']['agreement']['denominator'],4)
        self.assertIsNone(r['disagreements_requiring_adjudication'][0]['adjudicated_label'])
        self.assertEqual(r['reviewers'][1]['metrics']['consequential_error']['comparable'],3)
    def test_taxonomy_disagreement_is_not_silently_reconciled(self):
        self.b['rows'][0]['category']='unsupported_continuity'
        r=compare(self.a,self.b,self.mapping)
        self.assertEqual(r['inter_rater']['category']['agreement']['numerator'],3)
        self.assertEqual(len(r['disagreements_requiring_adjudication']),1)
    def test_same_reviewer_id_is_rejected(self):
        with self.assertRaises(ValueError):compare(self.a,self.a,self.mapping)
    def test_single_family_has_no_bootstrap_interval(self):
        self.assertIsNone(interval([('one',True),('one',False)])['interval_95'])
    def test_no_reviewed_rows_produce_no_agreement(self):
        for r in self.a['rows']:r['human_reviewed']=False
        r=compare(self.a,self.b,self.mapping)
        self.assertEqual(r['shared_completed_attempts'],0)
        self.assertIsNone(r['inter_rater']['category']['agreement']['value'])

if __name__=='__main__':unittest.main()
