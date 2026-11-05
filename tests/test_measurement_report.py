"""Report safeguards for sparse agreement and unrun controls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('measurement_report',ROOT/'scripts/build_assignment_submission.py')
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


def diagnostic(status='suppressed_single_label_margin'):
    return {'label_order':['yes','no'],
        'full_matrix':[{'left':a,'right':b,'count':4 if (a,b)==('yes','yes') else 2 if (a,b)==('yes','no') else 0}
                       for a in ('yes','no') for b in ('yes','no')],
        'label_frequencies':{'left':{'yes':6,'no':0},'right':{'yes':4,'no':2}},
        'observed_agreement':{'numerator':4,'denominator':6,'value':4/6},
        'cohen_kappa':{'value':None,'status':status,'warnings':['very_small_sample']}}


class MeasurementReportTests(unittest.TestCase):
    def test_constant_margin_is_withheld_not_reported_as_accuracy_or_undefined(self):
        result=report.agreement_html('Example',diagnostic())
        self.assertIn('Cohen\'s kappa: Not reported',result)
        self.assertIn('suppressed single label margin',result)
        self.assertIn('yes 6, no 0',result)
        self.assertIn('yes 4, no 2',result)
        self.assertEqual(result.count('<td>0</td>'),2)
        self.assertIn('not accuracy',result)

    def test_undefined_and_unmeasured_are_distinct(self):
        result=report.agreement_html('Example',diagnostic('degenerate_marginals'))
        self.assertIn('Cohen\'s kappa: Undefined',result)
        self.assertEqual(report.ratio_text({'numerator':0,'denominator':0,'value':None}),'Unmeasured')
        self.assertEqual(report.ratio_text({'numerator':0,'denominator':4,'value':0}),'0/4')

    def test_diagnostic_labels_are_escaped(self):
        result=report.agreement_html('<script>x</script>',diagnostic())
        self.assertNotIn('<script>',result)
        self.assertIn('&lt;script&gt;',result)

    def test_later_recovery_keeps_physical_and_logical_counts_separate(self):
        result=report.recovery_html({'recovery':{'additional_requests':5,
            'additional_raw':{'received':5,'raw_scorable':3},
            'final_logical_raw':{'raw_scorable':110},'all_physical_requests':149,
            'final_logical_requests':144,'reported_additional_cost_usd':0.3813755}})
        self.assertIn('149 physical requests',result)
        self.assertIn('144 logical jobs',result)
        self.assertIn('do not replace the original-attempt comparisons',result)
        self.assertIn('$0.3813755',result)
        self.assertIn('made no paid calls',result)

    def test_prepared_controls_and_literature_never_claim_execution(self):
        e={'historical':{'model_grading':{}},'grader_robustness':{
            'family':{'historical':{'comparable':6,'changed':2}},'sensitivity':{'comparisons':{}},'injection':{'comparison':{}}}}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config').mkdir()
            (root/'config/judge_controls_11.proposed.json').write_text('{}')
            (root/'output/measurement_update_11').mkdir(parents=True)
            (root/'output/measurement_update_11/literature-review.html').write_text('verified limits')
            result=report.measurement_html(e,root)
        self.assertIn('Prepared, NOT RUN',result)
        self.assertIn('repeated-original-prompt controls',result)
        self.assertIn('6 eligible cross-judge cases contain 2 disagreements',result)
        self.assertIn('Author expectations remain separate',result)
        self.assertIn('has not been prepared or run',result)
        self.assertIn('literature-review.html',result)


if __name__=='__main__':unittest.main()
