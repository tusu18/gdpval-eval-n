"""Keep automated delivery flags separate from human content findings."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_strengthening_13 import queue_audit


def save(root,path,obj):
    p=root/path;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj))


def fixture(root):
    def human(cid,accept,error):
        return {'review_id':cid,'endpoints':{'content_acceptable':{'human_label':accept},'consequential_error':{'human_label':error}}}
    save(root,'output/assignment_final/evidence.json',{'human':{
        'calibration':{'case_level_comparisons':[human('page','yes','no'),human('schedule','no','yes'),human('outside','yes','no')]},
        'taxonomy':{'examples':[{'review_id':'schedule','category':'tooling_gate','category_label':'Tooling release gate missing'}]}}})
    save(root,'output/submission_audit/review_selection.json',{'failure_ids':['page','schedule','pending']})
    save(root,'output/submission_audit/private_review_key.json',[
        {'review_id':cid,'run_id':cid,'family_id':'family','failure_queue':True,'triage_category':cat}
        for cid,cat in [('page','page_overflow'),('schedule','unsupported_continuity'),('pending','unsupported_continuity')]])
    save(root,'output/submission_audit/taxonomy.json',{'denominator':3,'categories':[
        {'id':cat,'name':cat,'definition':'Original automated flag','data_fix':'Unresolved','candidate_count':n}
        for cat,n in [('page_overflow',1),('unsupported_continuity',2)]]})


class QueueAuditTests(unittest.TestCase):
    def test_content_acceptance_does_not_clear_native_page_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);fixture(root);audit=queue_audit(root)
            page=next(x for x in audit['cases'] if x['review_id']=='page')
            self.assertEqual(page['human_content_acceptable'],'yes')
            self.assertIn('remains a separate mechanical observation',page['original_flag_disposition'])
            self.assertIsNone(page['human_finding_category'])
            self.assertEqual(audit['unreviewed_candidates'],1)
            self.assertEqual(audit['documented_content_findings_in_queue'],1)
            self.assertEqual(audit['reviewed_cases_outside_queue'],['outside'])

    def test_original_triage_is_not_replaced_with_human_category(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);fixture(root);audit=queue_audit(root)
            row=next(x for x in audit['cases'] if x['review_id']=='schedule')
            self.assertEqual(row['original_triage_category'],'unsupported_continuity')
            self.assertEqual(row['human_finding_category'],'tooling_gate')

    def test_duplicate_selection_cannot_inflate_review_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);fixture(root)
            save(root,'output/submission_audit/review_selection.json',{'failure_ids':['page','page','pending']})
            with self.assertRaises(ValueError):queue_audit(root)


if __name__=='__main__':unittest.main()
