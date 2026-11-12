"""Section 02 tests use synthetic feeds and release HTML."""
import json
import subprocess
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from scripts.build_public_reports import build, validate
from scripts.refresh_public_market import prepare_section02
from scripts.section02_news import SOURCES, collect, policy_rate, release_fact

DAY = date(2026, 11, 12)
CUTOFF = datetime.fromisoformat("2026-11-12T18:00:00+09:00")
ORIGINAL = "https://www.federalreserve.gov/newsevents/pressreleases/monetary20261111a.htm"
RSS = f"""<rss><channel><item><title>Federal Reserve issues FOMC statement</title>
<link>{ORIGINAL}?tracking=test</link><pubDate>Wed, 11 Nov 2026 19:00:00 GMT</pubDate>
</item></channel></rss>"""
RELEASE = "<p>The Committee decided to maintain the target range for the federal funds rate at 3-3/4 to 4 percent.</p>"
LATE_CPI = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<title>Test price release</title><link href="https://www.bls.gov/news.release/archives/cpi_11122026.htm"/>
<published>2026-11-12T03:10:00-05:00</published>
<content>In October, the Consumer Price Index for All Urban Consumers rose 0.4 percent, seasonally adjusted.</content>
</entry></feed>"""


def feed(url):
    return {
        SOURCES["policy"][0]: RSS, ORIGINAL: RELEASE,
        SOURCES["prices"][0]: LATE_CPI, SOURCES["jobs"][0]: "<feed/>",
    }[url]


class Section02Tests(unittest.TestCase):
    def test_same_day_release_window_and_concept(self):
        selection = collect(DAY, CUTOFF, fetch=feed)
        self.assertEqual(selection["status"], "ready")
        self.assertEqual(len(selection["issues"]), 1)
        self.assertEqual(selection["issues"][0]["source"], ORIGINAL)
        self.assertIn("3.75~4%", selection["issues"][0]["fact"])
        self.assertEqual(selection["concept"]["term"], "정책금리")
        self.assertIn("3.75~4%", selection["concept"]["application"])
        self.assertEqual(collect(DAY, CUTOFF, seen=[ORIGINAL], fetch=feed)["status"], "pending")
        self.assertEqual(collect(date(2026, 11, 11), CUTOFF, fetch=feed)["status"], "pending")

    def test_failed_and_invalid_feeds_are_pending(self):
        def unavailable(url):
            if url == SOURCES["policy"][0]:
                raise TimeoutError()
            return "<!DOCTYPE rss><rss>"
        self.assertEqual(collect(DAY, CUTOFF, fetch=unavailable), {"status": "pending", "issues": []})
        self.assertIsNone(policy_rate("The target range could change next meeting."))
        self.assertIn("0.4%", release_fact("prices", "In October, the Consumer Price Index for All Urban Consumers rose 0.4 percent, seasonally adjusted."))
        self.assertIn("4.1%", release_fact("jobs", "Employment rose in October and the unemployment rate changed little at 4.1 percent."))

    def test_news_isolated_from_publication_and_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            news = collect(DAY, CUTOFF, fetch=feed)
            build(root, DAY, section02=news)
            manuscript = root / "content/daily/2026-11-12.json"
            original = manuscript.read_bytes()
            html = (root / "reports/daily/2026-11-12.html").read_text()
            self.assertIn("시장과 연결해 보기", html)
            self.assertIn("경제 개념 · 정책금리", html)
            self.assertIn("2026-11-12 04:00 KST", html)
            self.assertEqual(html.count('<div class="eyebrow">SECTION '), 4)
            with patch("scripts.refresh_public_market.subprocess.run", side_effect=subprocess.TimeoutExpired("news", 13)):
                pending = prepare_section02(root, DAY, CUTOFF)
            self.assertEqual(pending, {"status": "pending", "issues": []})
            build(root, DAY, section02=pending)
            self.assertEqual(manuscript.read_bytes(), original)
            doc = json.loads(original)
            doc["section02"]["issues"][0]["publishedAt"] = "2026-11-10T00:00:00+09:00"
            with self.assertRaises(ValueError):
                validate(doc)
