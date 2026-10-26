import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import market_close as app
from market_sources import Bar, Provider, parse_fred, parse_naver, parse_fsc, parse_krx, KrxProvider
import build_public_reports as builder

NOW=datetime.fromisoformat('2026-10-26T09:00:00+00:00')
class Fake:
    def __init__(self,bars=None,error=None):self.bars=bars;self.error=error;self.calls=0
    def fetch(self,instrument,target):
        self.calls+=1
        if self.error:raise self.error
        return self.bars or [Bar('2026-10-23',100.0),Bar('2026-10-26',101.0)]

def calendar(name,now,through):return date(2026,10,26),date(2026,10,23)
def config():
    return {'calendarReviewedThrough':'2026-12-31','providers':{
      key:{'enabled':True,'collectionAllowed':True,'family':key,'instruments':['kospi'], 'sourceUrls':{'kospi':'https://example.invalid/'+key}, 'public':{'display':key=='primary','redistribution':key=='primary','derivedReturns':key=='primary','instruments':['kospi'],'evidence':'https://example.invalid/test-license','reviewedAt':'2026-01-01','validThrough':'2026-12-31'}} for key in ['primary','check']}}

class CloseTests(unittest.TestCase):
    def test_default_registry_never_fetches_or_emits_unapproved_values(self):
        cfg=json.loads((ROOT/'config/market-sources.json').read_text())
        adapters={k:Fake(error=AssertionError('must never fetch')) for k in cfg['providers']}
        result=app.collect(cfg,NOW,adapters,calendar)
        self.assertEqual(result['indices'],[])
        self.assertTrue(all(s['status']=='rights_pending' for s in result['marketStatus']))
        self.assertTrue(all(a.calls==0 for a in adapters.values()))

    def test_cross_check_and_rate(self):
        result=app.collect(config(),NOW,{'primary':Fake(),'check':Fake()},calendar)
        self.assertEqual(len(result['indices']),1)
        self.assertEqual(result['indices'][0]['changePct'],1.0)
        self.assertEqual(result['indices'][0]['previousAsOf'],'2026-10-23')

    def test_disagreement_missing_nonfinite_and_network_fail_closed(self):
        cases=[(Fake([Bar('2026-10-23',100),Bar('2026-10-26',110)]),'disagreement'),
               (Fake([Bar('2026-10-23',100)]),'missing'),
               (Fake([Bar('2026-10-23',100),Bar('2026-10-26',float('nan'))]),'invalid'),
               (Fake(error=RuntimeError('SECRET_KEY_PRIVATE_PRICE_9876')),'provider_error')]
        for checker,reason in cases:
            with self.subTest(reason=reason):
                result=app.collect(config(),NOW,{'primary':Fake(),'check':checker},calendar)
                self.assertEqual(result['indices'],[])
                self.assertEqual(result['marketStatus'][0]['status'],reason)
                self.assertNotIn('SECRET_KEY',json.dumps(result))
                self.assertNotIn('9876',json.dumps(result))

    def test_cannot_bypass_expired_grant_or_same_family(self):
        cfg=config();cfg['providers']['primary']['public']['validThrough']='2026-10-25'
        self.assertEqual(app.collect(cfg,NOW,{'primary':Fake(),'check':Fake()},calendar)['indices'],[])
        cfg=config();cfg['providers']['check']['family']='primary'
        self.assertEqual(app.collect(cfg,NOW,{'primary':Fake(),'check':Fake()},calendar)['indices'],[])

    def test_requires_exact_prior_session_and_checks_reported_rate(self):
        with self.assertRaises(LookupError):app.checked_pair([Bar('2026-10-22',100),Bar('2026-10-26',101)],date(2026,10,26),date(2026,10,23))
        with self.assertRaises(ValueError):app.checked_pair([Bar('2026-10-23',100),Bar('2026-10-26',101,8.0)],date(2026,10,26),date(2026,10,23))

    def test_kr_us_sessions_differ_on_monday_evening(self):
        self.assertEqual(app.session_pair('XKRX',NOW,'2026-12-31')[0],date(2026,10,26))
        self.assertEqual(app.session_pair('XNAS',NOW,'2026-12-31')[0],date(2026,10,23))

    def test_us_holiday_and_early_close_and_dst(self):
        self.assertEqual(app.session_pair('XNYS',datetime.fromisoformat('2026-07-03T22:00:00+00:00'),'2026-12-31')[0],date(2026,7,2))
        # Thanksgiving Friday early close is 18:00 UTC + 30-minute safety buffer.
        self.assertEqual(app.session_pair('XNAS',datetime.fromisoformat('2026-11-27T18:20:00+00:00'),'2026-12-31')[0],date(2026,11,25))
        self.assertEqual(app.session_pair('XNAS',datetime.fromisoformat('2026-11-27T18:40:00+00:00'),'2026-12-31')[0],date(2026,11,27))
        self.assertEqual(app.session_pair('XNYS',datetime.fromisoformat('2026-03-09T20:20:00+00:00'),'2026-12-31')[0],date(2026,3,6))
        self.assertEqual(app.session_pair('XNYS',datetime.fromisoformat('2026-03-09T20:40:00+00:00'),'2026-12-31')[0],date(2026,3,9))

    def test_kr_holiday_and_expired_calendar(self):
        # Korean National Liberation Day observed: August 17, 2026.
        self.assertEqual(app.session_pair('XKRX',datetime.fromisoformat('2026-08-17T10:00:00+00:00'),'2026-12-31')[0],date(2026,8,14))
        with self.assertRaises(ValueError):app.session_pair('XKRX',datetime.fromisoformat('2027-01-05T10:00:00+00:00'),'2026-12-31')

    def test_provider_parsers_with_only_synthetic_data(self):
        self.assertEqual(parse_fred('observation_date,SP500\n2026-10-23,100\n2026-10-26,.\n','sp500'),[Bar('2026-10-23',100)])
        self.assertEqual(parse_naver('[{"localTradedAt":"2026-10-23","closePrice":"1,000"}]')[0].close,1000)
        text=json.dumps({'response':{'header':{'resultCode':'00'},'body':{'items':{'item':[{'idxNm':'코스피','basDt':'20261023','clpr':'100','hipr':'101','lopr':'99','fltRt':'1'}]}}}})
        self.assertEqual(parse_fsc(text,'kospi')[0],Bar('2026-10-23',100,1))
        with patch.dict('os.environ',{'FSC_API_KEY':'TEST_ONLY'},clear=False):
            captured=[]
            provider=Provider('fsc',lambda url,params:captured.append((url,params)) or text)
            provider.fetch('kospi',date(2026,10,26))
            self.assertIn('_V2',captured[0][0]);self.assertEqual(captured[0][1]['idxNm'],'코스피')

    def test_krx_exact_index_sessions_headers_and_rate(self):
        calls=[]
        def transport(url, params, headers=None):
            calls.append((url,params,headers))
            return json.dumps({'OutBlock_1':[{'IDX_NM':'코스피','BAS_DD':params['basDd'],'CLSPRC_IDX':'101' if params['basDd']=='20261026' else '100','LWPRC_IDX':'99','HGPRC_IDX':'102','OPNPRC_IDX':'100','FLUC_RT':'1'}, {'IDX_NM':'코스피 200'}]})
        with patch.dict('os.environ',{'KRX_API_KEY':'TEST_ONLY'}):
            bars=KrxProvider(transport).fetch_pair('kospi',date(2026,10,26),date(2026,10,23))
        self.assertEqual(app.checked_pair(bars,date(2026,10,26),date(2026,10,23)),(101,100,1.0000000000000009))
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][2],{'AUTH_KEY':'TEST_ONLY'})
        self.assertNotIn('TEST_ONLY',calls[0][0])
        with self.assertRaises(KeyError):parse_krx('{"error":"not_authorized"}','kospi')
        with patch.dict('os.environ',{'KRX_API_KEY':'TEST_ONLY'}):
            with self.assertRaises(ValueError):
                KrxProvider(lambda *a,**kw:transport(a[0],{'basDd':'20261022'})).fetch_pair('kospi',date(2026,10,26),date(2026,10,23))

    def test_diagnostic_is_separate_from_public_rights_and_redacts_prices(self):
        from check_market_connection import diagnose
        cfg=config()
        cfg['providers']['primary']['public']['display']=False
        adapters={'primary':Fake(),'check':Fake()}
        result=diagnose(cfg,NOW,adapters)
        self.assertEqual(result['instruments'][0]['crossCheck'],'passed')
        self.assertFalse(result['publicDataWritten'])
        self.assertNotIn('101',json.dumps(result))
        self.assertEqual(app.collect(cfg,NOW,adapters,calendar)['indices'],[])
        broken=diagnose(cfg,NOW,{'primary':Fake(error=RuntimeError('SECRET_PRICE_9876')),'check':Fake()})
        self.assertNotIn('SECRET_PRICE',json.dumps(broken))
        self.assertNotIn('9876',json.dumps(broken))

    def test_late_data_revision_preserves_original_and_retry_is_idempotent(self):
        market=app.collect(config(),NOW,{'primary':Fake(),'check':Fake()},calendar)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);builder.build(root,date(2026,10,26))
            original=(root/'reports/daily/2026-10-26.html').read_bytes()
            manuscript=(root/'content/daily/2026-10-26.json').read_bytes()
            builder.build(root,date(2026,10,26),market=market)
            self.assertEqual((root/'reports/daily/2026-10-26.html').read_bytes(),original)
            self.assertEqual((root/'content/daily/2026-10-26.json').read_bytes(),manuscript)
            idx=json.loads((root/'reports/index.json').read_text())
            self.assertEqual(idx[0]['url'],'daily/2026-10-26-r001.html')
            page=(root/'reports/latest.html').read_text()
            self.assertIn('101.00',page)
            builder.build(root,date(2026,10,26),market=market)
            self.assertEqual(len(list((root/'reports/daily').glob('*-r*.html'))),1)
            missing=copy.deepcopy(market);missing['indices']=[];missing['marketStatus'][0].update(status='missing',message='자료 미반영')
            builder.build(root,date(2026,10,26),market=missing)
            self.assertEqual(len(list((root/'reports/daily').glob('*-r*.html'))),2)
            self.assertNotIn('101.00',(root/'reports/latest.html').read_text())
            self.assertTrue((root/'reports/daily/2026-10-26-r001.html').exists())

if __name__=='__main__':unittest.main()
