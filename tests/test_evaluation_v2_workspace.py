"""Offline checks for original-source isolation, revisions and native formats."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from evaluation_v2_workspace import Workspace,initial_message,extract_native,validate_content,sha

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.source=self.folder/'source.txt';self.source.write_text('Original source\n'+('x'*24001)+'\nLAST SOURCE LINE')
        self.task={'task_id':'test','prompt':'ORIGINAL PROMPT\nUnchanged.', 'references':[{'path':str(self.source),'name':'source.txt','sha256':sha(self.source)}]}
        self.w=Workspace(self.task,self.folder/'run')
    def tearDown(self):self.temp.cleanup()
    def test_exact_original_prompt(self):self.assertEqual(initial_message(self.task),self.task['prompt'])
    def test_complete_chunk_read_and_path_isolation(self):
        chunks=[];offset=0
        while True:
            reply=self.w.call('read_file',{'path':'source.txt','offset':offset,'limit':5000});chunks.append(reply['text'])
            if reply['next_offset'] is None:break
            offset=reply['next_offset']
        self.assertIn('LAST SOURCE LINE',''.join(chunks));self.assertNotIn('error',reply)
        self.assertIn('error',self.w.call('read_file',{'path':'../../private'}))
    def test_source_hash_mutation_rejected(self):
        self.source.write_text('Changed')
        self.assertIn('error',self.w.call('read_file',{'path':'source.txt'}))
    def test_string_paragraphs_rejected(self):
        with self.assertRaises(ValueError):validate_content('docx',{'sections':[{'paragraphs':'letters'}]})
    def test_revision_requires_fresh_inspection_and_rehydrates(self):
        self.assertNotIn('error',self.w.call('write_text',{'filename':'draft.txt','content':{'text':'first'}}))
        self.assertIn('error',self.w.call('submit_files',{'filenames':['draft.txt']}))
        self.w.call('inspect_file',{'filename':'draft.txt'})
        restored=Workspace(self.task,self.folder/'run')
        self.assertTrue(restored.files['draft.txt']['inspected'])
        restored.call('write_text',{'filename':'draft.txt','content':{'text':'second'}})
        self.assertEqual(restored.files['draft.txt']['revision'],2)
        self.assertIn('error',restored.call('submit_files',{'filenames':['draft.txt']}))
        restored.call('inspect_file',{'filename':'draft.txt'})
        self.assertTrue(restored.call('submit_files',{'filenames':['draft.txt']})['submitted'])
    def test_missing_view_blocks_and_old_revision_ack_does_not_count(self):
        path=self.folder/'run'/'test.docx';path.write_bytes(b'test')
        self.w.files['test.docx']={'path':str(path),'sha256':sha(path),'revision':2,'inspected':True,'previews':[{'path':'x'}],'viewed_pages':[]}
        self.w.acknowledge_images([{'filename':'test.docx','revision':1,'page':1}])
        self.assertEqual(self.w.files['test.docx']['viewed_pages'],[])
        self.assertIn('error',self.w.call('submit_files',{'filenames':['test.docx']}))

@unittest.skipUnless(os.environ.get('EVAL_V2_NATIVE_SMOKE')=='1','Optional actual native engines; set EVAL_V2_NATIVE_SMOKE=1')
class NativeSmokeTests(unittest.TestCase):
    def test_all_formats_and_template_roundtrip(self):
        folder=Path(os.environ.get('EVAL_V2_SMOKE_OUTPUT','/tmp/evaluation_v2_native_smoke'))
        folder.mkdir(parents=True,exist_ok=True)
        task={'task_id':'engineering-fixture','prompt':'Neutral engineering fixture; no business answer.','references':[]}
        w=Workspace(task,folder/'create')
        cases=[('write_document','memo.docx',{'title':'Engineering fixture','sections':[{'heading':'Content','paragraphs':['A neutral paragraph used to verify file creation and rendering.']}]}),
               ('write_workbook','calc.xlsx',{'sheets':[{'name':'Numbers','rows':[['Item','Value'],['A',2],['B',3],['Total','=SUM(B2:B3)']]}]}),
               ('write_presentation','deck.pptx',{'slides':[{'title':'Engineering fixture','paragraphs':['Native editable content.'],'table':{'headers':['Item','Value'],'rows':[['A','2'],['B','3']]},'notes':'Neutral engineering check.'}]}),
               ('write_pdf','memo.pdf',{'title':'Engineering fixture','sections':[{'paragraphs':['PDF generation check.']}]} )]
        results=[]
        for tool,name,content in cases:
            reply=w.call(tool,{'filename':name,'content':content});self.assertNotIn('error',reply,msg=str(reply))
            inspect=w.call('inspect_file',{'filename':name});self.assertNotIn('error',inspect)
            w.call('view_page',{'filename':name,'pages':list(range(1,reply['views']+1))});w.acknowledge_images(w.image_queue);w.image_queue=[]
            results.append({'name':name,'sha256':w.files[name]['sha256'],'views':reply['views']})
        self.assertTrue(w.call('submit_files',{'filenames':[x[1] for x in cases]})['submitted'])
        xlsx=Path(w.files['calc.xlsx']['path']);pdf=Path(w.files['memo.pdf']['path'])
        derived_task={**task,'references':[{'path':str(p),'name':p.name,'sha256':sha(p)} for p in (xlsx,pdf)]}
        edit=Workspace(derived_task,folder/'template')
        for tool,name,content in [('write_workbook','updated.xlsx',{'template_source':'calc.xlsx','sheets':[{'name':'Numbers','updates':[{'cell':'B2','value':7}]}]}),('write_pdf','filled.pdf',{'template_source':'memo.pdf','overlays':[{'page':1,'x':70,'y':250,'text':'Overlay fixture','font_size':10}]})]:
            reply=edit.call(tool,{'filename':name,'content':content});self.assertNotIn('error',reply,msg=str(reply));results.append({'name':name,'sha256':edit.files[name]['sha256'],'views':reply['views']})
        metadata=edit.files['updated.xlsx']['metadata'];self.assertEqual(metadata['sheets'][0]['values'][3][1],10)
        self.assertIn('Overlay fixture',extract_native(edit.files['filled.pdf']['path'])['text'])
        (folder/'smoke-results.json').write_text(json.dumps({'status':'passed','model_calls':0,'fixtures':results},indent=2))

if __name__=='__main__':unittest.main()
