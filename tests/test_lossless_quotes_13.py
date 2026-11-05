"""Ensure interface repairs never conceal unsupported quoted evidence."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_lossless_quotes_13 import (audit_record, lossless_normalize,
    preserved_judgment_fields, score_lossless_judgment)
from evidence_grader import score_judgment


def fixture(quote='sheet:A1\t50\nsheet:B1\tApproved'):
    packet = {'source_documents': {'policy':'Finance must approve before release.'},
        'criteria':[{'id':'release','critical':True}],
        'artifacts':[{'id':'a.xlsx','units':[{'locator':'sheet:A1','text':'50'},
            {'locator':'sheet:B1','text':'Approved'}]}],
        'engineering_checks':{'native_count_and_types_pass':True}}
    judgment = {'task_defect':{'status':'no','reason':'Sources adequate.'},
        'criteria':[{'id':'release','status':'pass','rationale':'Test fixture rationale.',
            'evidence_kind':'quoted','evidence':[{'source_id':'policy',
                'source_quote':'Finance must approve before release.',
                'artifact_id':'a.xlsx','output_quote':quote}]}]}
    return packet, judgment


class LosslessEvidenceTests(unittest.TestCase):
    def test_all_multicell_values_locators_and_source_evidence_survive(self):
        packet, judgment=fixture(); original=copy.deepcopy(judgment)
        result, changes, rejects=lossless_normalize(packet, judgment)
        self.assertEqual(judgment, original)
        self.assertEqual(rejects, [])
        evidence=result['criteria'][0]['evidence']
        self.assertEqual([x['output_quote'] for x in evidence], ['50','Approved'])
        self.assertEqual([x['verified_output_locator'] for x in evidence], ['sheet:A1','sheet:B1'])
        self.assertTrue(all(x['source_quote']==judgment['criteria'][0]['evidence'][0]['source_quote'] for x in evidence))
        self.assertTrue(preserved_judgment_fields(judgment,result,changes))
        self.assertEqual(score_lossless_judgment(packet,result)['status'],'automated_assessment_not_human_acceptance')

    def test_multiline_native_value_is_not_split_or_shortened(self):
        packet, judgment=fixture('sheet:A1\tApproval is conditional.\nFinance remains required.\nsheet:B1\tApproved')
        packet['artifacts'][0]['units'][0]['text']='Approval is conditional.\nFinance remains required.'
        result, changes, rejects=lossless_normalize(packet,judgment)
        self.assertEqual(rejects, [])
        self.assertEqual(result['criteria'][0]['evidence'][0]['output_quote'],'Approval is conditional.\nFinance remains required.')
        self.assertEqual(changes[0]['values_after'],2)

    def test_wrong_later_value_rejects_whole_quote_not_just_suffix(self):
        packet, judgment=fixture('sheet:A1\t50\nsheet:B1\tNot approved')
        result, changes, rejects=lossless_normalize(packet, judgment)
        self.assertEqual(result,judgment);self.assertEqual(changes,[])
        self.assertEqual(rejects[0]['reason'],'native_value_mismatch')
        self.assertEqual(score_lossless_judgment(packet,result)['status'],'invalid_grader_evidence')

    def test_value_prefix_does_not_accept_changed_number(self):
        packet, judgment=fixture('sheet:A1\t500')
        result, changes, rejects=lossless_normalize(packet,judgment)
        self.assertEqual(result,judgment);self.assertEqual(changes,[])
        self.assertEqual(rejects[0]['reason'],'unconsumed_quote_content')

    def test_unknown_locator_not_repaired_even_if_value_exists_elsewhere(self):
        packet, judgment=fixture('sheet:Z9\t50')
        result, changes, rejects=lossless_normalize(packet,judgment)
        self.assertEqual(result,judgment);self.assertEqual(changes,[])
        self.assertEqual(rejects[0]['reason'],'unknown_locator_in_named_artifact')

    def test_cross_artifact_locator_cannot_borrow_another_file_value(self):
        packet, judgment=fixture('sheet:A1\t50')
        packet['artifacts'].append({'id':'b.xlsx','units':[{'locator':'other:A1','text':'50'}]})
        judgment['criteria'][0]['evidence'][0]['artifact_id']='b.xlsx'
        result, changes, rejects=lossless_normalize(packet,judgment)
        self.assertEqual(result,judgment);self.assertEqual(changes,[])
        self.assertEqual(rejects[0]['reason'],'unknown_locator_in_named_artifact')

    def test_empty_or_whitespace_output_evidence_cannot_become_valid(self):
        for quote in ('sheet:A1\t','sheet:A1\t ', ' ', ''):
            packet, judgment=fixture(quote)
            packet['artifacts'][0]['units'][0]['text']=' '
            result, changes, rejects=lossless_normalize(packet,judgment)
            self.assertEqual(changes,[])
            self.assertEqual(score_lossless_judgment(packet,result)['status'],'invalid_grader_evidence')

    def test_literal_native_quote_with_tabs_is_preserved_without_reinterpretation(self):
        packet, judgment=fixture('sheet:A1\t50')
        packet['artifacts'][0]['units'][0]['text']='The literal label reads sheet:A1\t50 today.'
        result, changes, rejects=lossless_normalize(packet,judgment)
        self.assertEqual(result,judgment);self.assertEqual(changes,[]);self.assertEqual(rejects,[])

    def test_duplicate_locator_definition_is_ambiguous(self):
        packet, judgment=fixture('sheet:A1\t50')
        packet['artifacts'][0]['units'].append({'locator':'sheet:A1','text':'500'})
        result, changes, rejects=lossless_normalize(packet,judgment)
        self.assertEqual(changes,[])
        self.assertEqual(rejects[0]['reason'],'duplicate_artifact_locator')

    def test_duplicate_artifact_ids_fail_secondary_validation(self):
        packet, judgment=fixture('50')
        packet['artifacts'].append(copy.deepcopy(packet['artifacts'][0]))
        self.assertIn('duplicate_artifact_id',score_lossless_judgment(packet,judgment)['errors'])

    def test_preexisting_locator_metadata_is_never_overwritten(self):
        packet, judgment=fixture('sheet:A1\t50')
        judgment['criteria'][0]['evidence'][0]['verified_output_locator']='sheet:Z9'
        result, changes, rejects=lossless_normalize(packet,judgment)
        self.assertEqual(result,judgment);self.assertEqual(changes,[])
        self.assertEqual(rejects[0]['reason'],'preexisting_normalizer_metadata')

    def test_raw_literal_with_unknown_verified_locator_is_rejected(self):
        packet, judgment=fixture('50')
        judgment['criteria'][0]['evidence'][0]['verified_output_locator']='sheet:Z9'
        result, changes, _=lossless_normalize(packet,judgment)
        self.assertEqual(changes,[])
        self.assertIn('release:unverifiable_verified_output_locator',score_lossless_judgment(packet,result)['errors'])

    def test_raw_literal_cannot_claim_locator_of_another_value(self):
        packet, judgment=fixture('50')
        judgment['criteria'][0]['evidence'][0]['verified_output_locator']='sheet:B1'
        self.assertIn('release:unverifiable_verified_output_locator',score_lossless_judgment(packet,judgment)['errors'])

    def test_verified_locator_cannot_borrow_another_artifact_unit(self):
        packet, judgment=fixture('50')
        packet['artifacts'].append({'id':'b.xlsx','units':[{'locator':'other:A1','text':'50'}]})
        judgment['criteria'][0]['evidence'][0].update({'artifact_id':'b.xlsx','verified_output_locator':'sheet:A1'})
        self.assertIn('release:unverifiable_verified_output_locator',score_lossless_judgment(packet,judgment)['errors'])

    def test_verified_locator_must_resolve_to_exactly_one_unit(self):
        packet, judgment=fixture('50')
        packet['artifacts'][0]['units'].append({'locator':'sheet:A1','text':'50'})
        judgment['criteria'][0]['evidence'][0]['verified_output_locator']='sheet:A1'
        self.assertIn('release:unverifiable_verified_output_locator',score_lossless_judgment(packet,judgment)['errors'])

    def test_uncertain_row_does_not_hide_false_verified_locator_claim(self):
        packet, judgment=fixture('50')
        judgment['criteria'][0]['status']='uncertain'
        judgment['criteria'][0]['evidence'][0]['verified_output_locator']='sheet:Z9'
        self.assertIn('release:unverifiable_verified_output_locator',score_lossless_judgment(packet,judgment)['errors'])

    def test_raw_literal_with_valid_exact_locator_is_traceable(self):
        packet, judgment=fixture('50')
        judgment['criteria'][0]['evidence'][0]['verified_output_locator']='sheet:A1'
        self.assertEqual(score_lossless_judgment(packet,judgment)['status'],'automated_assessment_not_human_acceptance')

    def test_invalid_source_quote_is_not_fixed_by_output_alignment(self):
        packet, judgment=fixture()
        judgment['criteria'][0]['evidence'][0]['source_quote']='Purchase alone can approve.'
        result, changes, _=lossless_normalize(packet,judgment)
        self.assertTrue(changes)
        self.assertIn('release:unverifiable_source_quote',score_lossless_judgment(packet,result)['errors'])

    def test_empty_evidence_and_malformed_judgment_remain_invalid(self):
        packet, judgment=fixture();judgment['criteria'][0]['evidence']=[]
        for invalid in (judgment, None, [], {'criteria':[None]}):
            result, changes, _=lossless_normalize(packet,invalid)
            self.assertEqual(changes,[])
            self.assertEqual(score_lossless_judgment(packet,result)['status'],'invalid_grader_evidence')

    def test_audit_preserves_raw_and_reports_repair_only_as_secondary(self):
        packet, judgment=fixture()
        for unit in packet['artifacts'][0]['units']:
            unit['locator']=unit['locator'].replace('sheet:', 'xl/worksheets/sheet1.xml:')
        judgment['criteria'][0]['evidence'][0]['output_quote']=judgment['criteria'][0]['evidence'][0]['output_quote'].replace('sheet:', 'xl/worksheets/sheet1.xml:')
        original=copy.deepcopy(judgment)
        record={'id':'test','status':'received','judgment':judgment,'assessment':score_judgment(packet,judgment)}
        row=audit_record(record,packet,'original_attempts')
        self.assertFalse(row['raw_primary_eligible']);self.assertTrue(row['lossless_secondary_scorable'])
        self.assertEqual(record['judgment'],original)
        self.assertEqual(row['lossless_discarded_value_segments'],0)
        self.assertEqual(row['frozen_discarded_value_segments'],1)

    def test_execution_failure_never_turns_into_a_judgment(self):
        packet,_=fixture()
        row=audit_record({'id':'failed','status':'execution_error'},packet,'original_attempts')
        self.assertFalse(row['raw_primary_eligible'])
        self.assertFalse(row['frozen_secondary_scorable'])
        self.assertFalse(row['lossless_secondary_scorable'])

    def test_preservation_check_catches_changed_rationale_or_source(self):
        packet, judgment=fixture();result,changes,_=lossless_normalize(packet,judgment)
        result['criteria'][0]['rationale']='Different claim'
        self.assertFalse(preserved_judgment_fields(judgment,result,changes))
        result,changes,_=lossless_normalize(packet,judgment)
        result['criteria'][0]['evidence'][0]['source_quote']='Different source'
        self.assertFalse(preserved_judgment_fields(judgment,result,changes))


if __name__=='__main__':
    unittest.main()
