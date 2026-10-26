import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('public_reports', Path(__file__).resolve().parents[1] / 'scripts/build_public_reports.py')
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)

class PublicReportTests(unittest.TestCase):
    def setUp(self):
        self.doc = app.make_doc(date(2099, 1, 2))

    def test_four_sections_and_quiz(self):
        page = app.generate(self.doc)
        self.assertEqual(page.count('class="eyebrow">SECTION '), 4)
        for title in app.TITLES:
            self.assertIn(title, page)
        self.assertIn('data-answer=', page)
        for removed in ['상대 강도', '액션 플랜', 'SCENARIOS', 'SECTION 05']:
            self.assertNotIn(removed, page)

    def test_unapproved_numbers_and_news_are_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manuscript = root / 'content/daily/2099-01-02.json'
            manuscript.parent.mkdir(parents=True)
            self.doc['indices'] = [{'name': 'KOSPI', 'region': 'kr', 'asOf': '2099-01-02', 'close': 1234, 'changePct': 1.0}]
            manuscript.write_text(json.dumps(self.doc))
            with self.assertRaises(ValueError):
                app.build(root, date(2099, 1, 2))
            self.assertFalse((root / 'reports').exists())
        for key in ['issues', 'distribution']:
            doc = copy.deepcopy(app.make_doc(date(2099, 1, 2)))
            doc[key] = [{'fact': 'Synthetic test', 'up': 1, 'down': 1, 'flat': 0}]
            with self.assertRaises(ValueError):
                app.generate(doc)

    def test_approved_synthetic_data_keeps_individual_dates(self):
        rights = {'status': 'approved_public', 'evidence': 'https://example.com/test-license'}
        self.doc['indices'] = [{'name': 'KOSPI', 'region': 'kr', 'asOf': '2099-01-01', 'close': 1234, 'changePct': 1.0, 'verified': True, 'publication': rights, 'source': 'https://example.com/test-source'}]
        self.doc['distribution'] = [{'name':'KOSPI', 'asOf':'2099-01-01', 'up':3, 'down':2, 'flat':1, 'verified':True, 'publication':rights, 'source':'https://example.com/test-source'}]
        self.doc['issues'] = [{'fact':'Synthetic fact', 'interpretation':'Synthetic view', 'verified':True, 'publication':rights, 'source':'https://example.com/test-source'}]
        page = app.generate(self.doc)
        for text in ['2099-01-01', '1,234.00', '+1.00%', '상승 3', '확인된 사실', '해석 · 작성자의 관점']:
            self.assertIn(text, page)
        self.doc['indices'][0]['close'] = float('nan')
        with self.assertRaises(ValueError):
            app.generate(self.doc)

    def test_idempotent_and_preserves_old_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / 'reports/daily/2000-01-01.html'
            old.parent.mkdir(parents=True)
            old.write_text('preserved legacy report')
            app.build(root, date(2099, 1, 2))
            current = root / 'reports/daily/2099-01-02.html'
            current.write_text(current.read_text() + '<!-- editorial edit -->')
            app.build(root, date(2099, 1, 2))
            self.assertTrue(current.read_text().endswith('<!-- editorial edit -->'))
            self.assertEqual(old.read_text(), 'preserved legacy report')
            self.assertEqual(len(json.loads((root / 'reports/index.json').read_text())), 1)
            alias = (root / 'reports/latest.html').read_text()
            self.assertIn('href="../assets/style.css"', alias)
            self.assertIn('href="./">리포트 아카이브', alias)
            self.assertIn('href="../">대시보드', alias)
            self.assertIn('editorial edit', alias)

if __name__ == '__main__':
    unittest.main()
