import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_grader_checks import normalize
class QuoteNormalizationTests(unittest.TestCase):
    def test_exact_multi_cell_quotes_are_split_without_changing_values(self):
        packet={'artifacts':[{'id':'a','units':[{'locator':'sheet:A1','text':'50'},{'locator':'sheet:B1','text':'Approved'}]}]}
        j={'criteria':[{'id':'c','evidence_kind':'quoted','evidence':[{'artifact_id':'a','source_id':'s','source_quote':'source','output_quote':'sheet:A1\t50\nsheet:B1\tApproved'}]}]}
        result,changes=normalize(packet,j)
        self.assertEqual([e['output_quote'] for e in result['criteria'][0]['evidence']],['50','Approved'])
        self.assertEqual(len(changes),1)
        self.assertIn('sheet:A1',j['criteria'][0]['evidence'][0]['output_quote'])
    def test_wrong_value_or_unknown_locator_is_never_repaired(self):
        packet={'artifacts':[{'id':'a','units':[{'locator':'sheet:A1','text':'50'}]}]}
        for quote in ['sheet:A1\t500','sheet:B1\t50']:
            j={'criteria':[{'id':'c','evidence_kind':'quoted','evidence':[{'artifact_id':'a','output_quote':quote}]}]}
            result,changes=normalize(packet,j);self.assertEqual(result,j);self.assertEqual(changes,[])
if __name__=='__main__':unittest.main()
