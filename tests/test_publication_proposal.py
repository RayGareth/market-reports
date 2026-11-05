"""Exercise the isolated proposal; never change the production publisher."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('noop_proposal', ROOT/'experiments/publication_noop_proposal.py')
proposal = importlib.util.module_from_spec(spec); spec.loader.exec_module(proposal)

class PublicationProposalTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {'reportDate':'2026-10-30','indices':[], 'marketStatus':[{'id':'sp500','status':'rights_pending','expectedAsOf':'2026-10-29'}], 'checkedAt':'2026-10-30T09:00:00Z'}
        self.files = {'reports/latest.html':b'original', 'reports/index.json':b'[]', proposal.MARKET:json.dumps(self.snapshot).encode()}

    def outputs(self, **changes):
        result = dict(self.files); value=copy.deepcopy(self.snapshot);value.update(changes)
        result[proposal.MARKET]=json.dumps(value).encode();return result

    def test_three_scheduled_attempts_need_one_publication(self):
        before={}; publications=0
        for stamp in ['09:00:00','09:15:00','09:30:00']:
            after=self.outputs(checkedAt='2026-10-30T'+stamp+'Z')
            if proposal.publication_required(before, after):before=after;publications+=1
        self.assertEqual(publications,1)
        self.assertEqual(json.loads(before[proposal.MARKET])['checkedAt'],'2026-10-30T09:00:00Z')

    def test_actual_close_and_return_changes_publish(self):
        for row in [{'close':123.45}, {'changePct':-1.23}, {'asOf':'2026-10-30'}, {'publication':{'status':'revoked'}}]:
            self.assertTrue(proposal.publication_required(self.files,self.outputs(indices=[row])))

    def test_status_date_or_new_schema_changes_publish(self):
        for changes in [{'marketStatus':[{'status':'disagreement'}]}, {'reportDate':'2026-11-02'}, {'publishedAt':'new'}]:
            self.assertTrue(proposal.publication_required(self.files,self.outputs(**changes)))

    def test_report_archive_and_removals_publish(self):
        for name in ['reports/latest.html','reports/index.json']:
            after=dict(self.files);after[name]=b'changed';self.assertTrue(proposal.publication_required(self.files,after))
        self.assertTrue(proposal.publication_required(self.files,{}))

    def test_malformed_and_missing_timestamps_publish(self):
        for body in [b'invalid',b'[]',b'{"checkedAt":null}',b'{}',b'{"checkedAt":"not-a-date"}',b'{"checkedAt":"2026-10-30T09:00:00"}']:
            after=dict(self.files);after[proposal.MARKET]=body
            self.assertTrue(proposal.publication_required(self.files,after))

    def test_unchanged_outputs_are_noop_and_inputs_untouched(self):
        before=copy.deepcopy(self.files);after=self.outputs(checkedAt='2026-10-30T10:00:00Z')
        saved=copy.deepcopy(after)
        self.assertFalse(proposal.publication_required(before,after))
        self.assertEqual(before,self.files);self.assertEqual(after,saved)
        self.assertFalse(proposal.publication_required(self.files,self.files))

if __name__=='__main__': unittest.main()
