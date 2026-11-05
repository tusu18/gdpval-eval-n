from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from judge_agreement import agreement_diagnostics
from assignment_evidence import historical_judge_diagnostics


class AgreementDiagnosticsTests(unittest.TestCase):
    def test_empty_is_unknown_with_all_zero_cells(self):
        result=agreement_diagnostics([])
        self.assertEqual(len(result['full_matrix']),4)
        self.assertEqual(sum(cell['count'] for cell in result['full_matrix']),0)
        self.assertEqual(result['cohen_kappa']['status'],'no_pairs')
        self.assertIsNone(result['cohen_kappa']['value'])
        self.assertIsNone(result['observed_agreement']['value'])
        self.assertIsNone(result['positive_agreement']['value'])
        self.assertEqual(result['label_frequencies'],{'left':{'yes':0,'no':0},'right':{'yes':0,'no':0}})

    def test_shared_negatives_do_not_become_positive_agreement(self):
        pairs=[('no','no')]*10+[('yes','no'),('no','yes')]
        result=agreement_diagnostics(pairs)
        self.assertEqual(result['observed_agreement']['numerator'],10)
        self.assertEqual(result['observed_agreement']['denominator'],12)
        self.assertEqual(result['positive_agreement']['value'],0)
        self.assertAlmostEqual(result['negative_agreement']['value'],10/11)
        self.assertAlmostEqual(result['cohen_kappa']['value'],-1/11)
        self.assertIn('very_small_sample',result['cohen_kappa']['warnings'])
        self.assertEqual(result['full_matrix'][0],{'left':'yes','right':'yes','count':0})

    def test_perfect_constant_raters_have_undefined_kappa(self):
        result=agreement_diagnostics([('yes','yes')]*12)
        self.assertEqual(result['observed_agreement']['value'],1)
        self.assertIsNone(result['cohen_kappa']['value'])
        self.assertEqual(result['cohen_kappa']['status'],'degenerate_marginals')
        self.assertIsNone(result['negative_agreement']['value'])

    def test_constant_one_rater_suppresses_uninformative_kappa(self):
        result=agreement_diagnostics([('yes','yes')]*4+[('yes','no')]*2)
        self.assertEqual(result['cohen_kappa']['status'],'suppressed_single_label_margin')
        self.assertIsNone(result['cohen_kappa']['value'])
        self.assertEqual(result['label_frequencies']['left'],{'yes':6,'no':0})
        self.assertEqual(result['label_frequencies']['right'],{'yes':4,'no':2})

    def test_balanced_perfect_agreement_kappa_one(self):
        result=agreement_diagnostics([('yes','yes')]*15+[('no','no')]*15)
        self.assertEqual(result['cohen_kappa']['value'],1)
        self.assertEqual(result['cohen_kappa']['warnings'],[])
        self.assertEqual(result['positive_agreement']['value'],1)

    def test_balanced_opposites_kappa_negative_one(self):
        result=agreement_diagnostics([('yes','no')]*10+[('no','yes')]*10)
        self.assertEqual(result['cohen_kappa']['value'],-1)
        self.assertEqual(result['positive_agreement']['value'],0)
        self.assertEqual(result['negative_agreement']['value'],0)

    def test_undeclared_uncertainty_and_none_never_coerced(self):
        for pairs in [[('yes',None)],[('yes','uncertain')],[(True,False)]]:
            with self.assertRaises(ValueError):agreement_diagnostics(pairs)

    def test_uncertainty_can_be_preserved_as_explicit_third_label(self):
        result=agreement_diagnostics([('pass','uncertain'),('uncertain','uncertain')],('pass','fail','uncertain'),None)
        self.assertEqual(len(result['full_matrix']),9)
        self.assertEqual(result['label_frequencies']['right']['uncertain'],2)
        self.assertEqual(result['observed_agreement']['numerator'],1)
        self.assertNotIn('positive_agreement',result)

    def test_positive_and_negative_agreement_follow_declared_label(self):
        result=agreement_diagnostics([('fail','fail'),('pass','fail')],('fail','pass'),'fail')
        self.assertEqual(result['positive_agreement']['value'],2/3)
        self.assertEqual(result['negative_agreement']['value'],0)

    def test_historical_defects_do_not_disappear_into_quality_agreement(self):
        records=[]
        for run,family in [('a','change_control'),('b','normal')]:
            for kind,label in [('primary',True),('secondary',False)]:
                records.append({'run_id':run,'kind':kind,'status':'completed','judge_model':kind,
                    'judgment':{'content_acceptable':label,'critical_error':label,'evaluation_defect':False}})
        result=historical_judge_diagnostics(records,[{'run_id':'a','family_id':'change_control'},{'run_id':'b','family_id':'normal'}])
        for field in ('content_acceptable','critical_error'):
            endpoint=result['endpoints'][field]
            self.assertEqual(endpoint['comparable'],2)
            self.assertEqual(endpoint['task_validity_filtered']['comparable'],1)
            self.assertEqual(endpoint['known_or_judge_flagged_task_defect_case_ids'],['a'])
        self.assertEqual(result['new_human_labels'],0)

    def test_historical_missing_invalid_and_task_unknown_are_separate(self):
        records=[{'run_id':'only_secondary','kind':'secondary','status':'completed','judgment':{}}]
        for kind in ('primary','secondary'):
            records.append({'run_id':'uncertain_label','kind':kind,'status':'completed',
                'judgment':{'critical_error':'uncertain','content_acceptable':True,'evaluation_defect':None}})
        result=historical_judge_diagnostics(records,[])['endpoints']
        self.assertEqual(result['critical_error']['comparable'],0)
        self.assertEqual(result['critical_error']['exclusions'],{'missing_primary_record':1,'non_binary_label':1})
        self.assertEqual(result['content_acceptable']['comparable'],1)
        self.assertEqual(result['content_acceptable']['task_validity_filtered']['comparable'],0)

    def test_historical_duplicate_identity_fails_closed(self):
        record={'run_id':'a','kind':'primary','status':'completed','judgment':{}}
        with self.assertRaises(ValueError):historical_judge_diagnostics([record,record],[])


if __name__=='__main__':unittest.main()
