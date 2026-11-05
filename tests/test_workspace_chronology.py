import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from repair_workspace_chronology import chronology_defect

class ChronologyTests(unittest.TestCase):
    def task(self,copied,created):
        return {'attachments':{'working-notes.txt':f'Working notes copied on {copied} from a revision-3 proposal.'},'workspace':{'project/decision-register.txt':f'planning/proposal-r3.txt was created {created} and remains unapproved.'}}
    def test_future_proposal_cannot_be_copied(self):
        self.assertIsNotNone(chronology_defect(self.task('2025-06-23','2026-10-22')))
    def test_same_day_or_later_copy_is_possible(self):
        self.assertIsNone(chronology_defect(self.task('2026-10-22','2026-10-22')))
        self.assertIsNone(chronology_defect(self.task('2026-10-23','2026-10-22')))
    def test_no_dated_copy_claim_does_not_invent_a_defect(self):
        self.assertIsNone(chronology_defect({'attachments':{},'workspace':{}}))

if __name__=='__main__':unittest.main()
