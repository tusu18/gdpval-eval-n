import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_file_workflow import ROOT,NativeWorkspace,validate_content,valid_name,initial_message

class NativeWorkflowTests(unittest.TestCase):
    def task(self,family='original_supplier_landed_cost'):
        return json.loads((ROOT/'data/evidence_upgrade_01/solver'/f'{family}__conflict.json').read_text())
    def environment_with_file(self,tmp):
        e=NativeWorkspace(self.task(),tmp)
        state=json.loads((ROOT/'output/native_workflow_01/engineering_smoke/docx_revision/state.json').read_text())
        e.files=copy.deepcopy(state['files']);e.files['memo.docx'].update(inspected=False,viewed_pages=[])
        return e
    def test_traversal_and_absolute_names_rejected(self):
        for name in ('../secret.docx','/tmp/a.docx','sub/a.docx','a..docx','a.xlsx.exe'):
            with self.assertRaises(ValueError):valid_name(name)
    def test_external_formulas_rejected_before_authoring(self):
        for f in ('=WEBSERVICE("https://x")','=SUM([other.xlsx]A1)','=HYPERLINK("https://x")'):
            with self.assertRaises(ValueError):validate_content('xlsx',{'sheets':[{'name':'A','rows':[[f]]}]})
    def test_numeric_zero_and_missing_cell_are_preserved(self):
        c={'sheets':[{'name':'A','rows':[[0,None,'=A1+1']]}]};old=copy.deepcopy(c);validate_content('xlsx',c);self.assertEqual(c,old)
    def test_mismatched_docx_table_is_rejected(self):
        with self.assertRaises(ValueError):validate_content('docx',{'title':'X','sections':[{'table':{'headers':['A','B'],'rows':[['only one']]}}]})
    def test_view_request_is_not_image_exposure(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=self.environment_with_file(tmp);e.call('inspect_file',{'filename':'memo.docx'});e.call('view_page',{'filename':'memo.docx','page':1})
            self.assertEqual(e.files['memo.docx']['viewed_pages'],[])
            self.assertIn('error',e.call('submit_files',{'filenames':['memo.docx']}))
            e.acknowledge_images(e.image_queue)
            self.assertTrue(e.call('submit_files',{'filenames':['memo.docx']})['submitted'])
    def test_old_image_cannot_validate_new_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=self.environment_with_file(tmp);e.call('view_page',{'filename':'memo.docx','page':1})
            queued=copy.deepcopy(e.image_queue);e.files['memo.docx']['revision']+=1;e.acknowledge_images(queued)
            self.assertEqual(e.files['memo.docx']['viewed_pages'],[])
    def test_sources_cannot_read_private_map_or_other_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=NativeWorkspace(self.task(),tmp)
            for p in ('../grader/evidence_maps.json','/etc/passwd','../../native_workflow_01/runs/other.json'):
                self.assertIn('error',e.call('read_file',{'path':p}))
    def test_gold_is_not_in_initial_prompt_or_tool_state(self):
        t=self.task();msg=initial_message(t)
        self.assertNotIn('canonical_facts',msg);self.assertNotIn('23600',msg);self.assertNotIn('savings_usd',msg)
    def test_mixed_contract_refuses_two_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=NativeWorkspace(self.task('change_control'),tmp)
            self.assertIn('error',e.call('submit_files',{'filenames':['sop.docx','form.docx']}))
    def test_no_fake_approval_from_requester(self):
        with tempfile.TemporaryDirectory() as tmp:
            e=NativeWorkspace(self.task('original_delivery_appointment'),tmp)
            r=e.call('ask_requester',{'question':'What is the latest receiving deadline?'})
            self.assertFalse(r['new_approval_granted']);self.assertIn('2026-11-06 at 16:00',r['answer'])

if __name__=='__main__':unittest.main()
