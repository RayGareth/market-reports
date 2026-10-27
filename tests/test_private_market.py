"""Synthetic fixtures exercise private grants, public rejection and refresh."""
import copy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_public_reports as builder
from check_private_market import preview
from market_close import INSTRUMENTS, collect, collect_private
from market_sources import Bar

NOW = datetime(2026, 10, 27, 10, tzinfo=timezone.utc)


def config():
    grant = {'display':True, 'derivedReturns':True, 'temporaryStorage':True,
             'evidence':'https://example.invalid/private-test-grant',
             'reviewedAt':'2026-10-27', 'validThrough':'2026-10-27'}
    providers = {}
    for name in ('a', 'b'):
        providers[name] = {'enabled':True, 'collectionAllowed':True, 'family':name,
                           'instruments':list(INSTRUMENTS), 'label':name,
                           'sourceUrls':{i:'https://example.invalid/' + name for i in INSTRUMENTS},
                           'public':{}, 'private':copy.deepcopy(grant)}
    return {'providers':providers, 'calendarReviewedThrough':'2026-12-31'}


class Fake:
    def __init__(self, value=101, missing=False):
        self.value, self.missing, self.calls = value, missing, 0

    def fetch(self, instrument, target):
        self.calls += 1
        return [Bar('2026-10-26',100)] + ([] if self.missing else [Bar('2026-10-27',self.value)])


def calendar(*args):
    return date(2026,10,27), date(2026,10,26)


class PrivateTests(unittest.TestCase):
    def test_transient_retry_is_bounded_and_rate_limits_are_not_retried(self):
        import requests
        from market_sources import get_text
        class Reply:
            def __init__(self, status):self.status_code, self.text = status, 'TEST_ONLY'
        with patch.object(requests, 'get', side_effect=[Reply(503),Reply(200)]) as fetch:
            self.assertEqual(get_text('https://example.invalid'), 'TEST_ONLY')
            self.assertEqual(fetch.call_count,2)
        with patch.object(requests, 'get', return_value=Reply(429)) as fetch:
            with self.assertRaises(RuntimeError):get_text('https://example.invalid')
            self.assertEqual(fetch.call_count,1)
        with patch.object(requests, 'get', side_effect=requests.Timeout('SECRET_123')) as fetch:
            with self.assertRaisesRegex(RuntimeError,'^Provider unavailable$'):get_text('https://example.invalid')
            self.assertEqual(fetch.call_count,2)

    def test_private_grants_never_authorize_public_calls_or_rendering(self):
        adapters = {'a':Fake(), 'b':Fake()}
        self.assertEqual(collect(config(),NOW,adapters,calendar)['indices'], [])
        self.assertEqual(sum(a.calls for a in adapters.values()), 0)
        market = collect_private(config(),NOW,adapters,calendar)
        self.assertEqual(len(market['indices']), 4)
        self.assertTrue(all(r['publication']['status']=='private_only' for r in market['indices']))
        doc = builder.make_doc(NOW.date());doc['indices'] = market['indices']
        with self.assertRaises(ValueError):builder.generate(doc)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):builder.build(Path(tmp),NOW.date(),market=market)
            self.assertFalse(any(Path(tmp).rglob('*')))
        self.assertIn('101.00',builder.generate(doc,audience='private'))

    def test_missing_expired_or_incomplete_grants_never_collect(self):
        for key,value in [('temporaryStorage',False),('display',False),('derivedReturns',False),('evidence',''),('validThrough','2026-10-26')]:
            cfg=config()
            for p in cfg['providers'].values():p['private'][key]=value
            adapters={'a':Fake(),'b':Fake()}
            self.assertEqual(collect_private(cfg,NOW,adapters,calendar)['indices'],[])
            self.assertEqual(sum(a.calls for a in adapters.values()),0)

    def test_refresh_changes_values_then_removes_missing_or_disagreeing_rows(self):
        for a,b,status,count in [(101,101,'verified',4),(102,102,'verified',4),(101,104,'disagreement',0)]:
            result=collect_private(config(),NOW,{'a':Fake(a),'b':Fake(b)},calendar)
            self.assertEqual(len(result['indices']),count)
            self.assertTrue(all(s['status']==status for s in result['marketStatus']))
        result=collect_private(config(),NOW,{'a':Fake(),'b':Fake(missing=True)},calendar)
        self.assertEqual(result['indices'],[])
        self.assertTrue(all(s['status']=='missing' for s in result['marketStatus']))

    def test_preview_keeps_private_markers_and_original_source_unchanged(self):
        root=Path(__file__).resolve().parents[1]
        original=(root/'assets/market.js').read_bytes()
        market=collect_private(config(),NOW,{'a':Fake(),'b':Fake()},calendar)
        with tempfile.TemporaryDirectory() as tmp:
            preview(Path(tmp),market,NOW)
            saved=json.loads((Path(tmp)/'data/public-market.json').read_text())
            self.assertTrue(all(r['publication']['status']=='private_only' for r in saved['indices']))
            html=(Path(tmp)/'reports/daily/2026-10-27.html').read_text()
            self.assertIn('비공개 연결 검증',html)
            self.assertEqual(html.count('SECTION 0'),4)
            self.assertIn("status==='private_only'",(Path(tmp)/'assets/market.js').read_text())
        self.assertEqual((root/'assets/market.js').read_bytes(),original)
        doc=builder.make_doc(NOW.date());doc['previewAudience']='private'
        with self.assertRaises(ValueError):builder.generate(doc)


if __name__ == '__main__':
    unittest.main()
