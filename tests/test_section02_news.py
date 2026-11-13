"""Section 02 tests use synthetic feeds and release HTML."""
import json
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts.build_public_reports import build, validate
from scripts.refresh_public_market import prepare_section02
from scripts.section02_news import SOURCES, collect, policy_rate, release_fact

DAY = date(2026, 11, 12)
CUTOFF = datetime.fromisoformat("2026-11-12T18:00:00+09:00")
AFTER = datetime.fromisoformat("2026-11-11T18:30:00+09:00")
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
    def test_release_window_and_concept(self):
        selection = collect(AFTER, CUTOFF, fetch=feed)
        self.assertEqual(selection["status"], "ready")
        self.assertEqual(len(selection["issues"]), 1)
        self.assertEqual(selection["issues"][0]["source"], ORIGINAL)
        self.assertIn("3.75~4%", selection["issues"][0]["fact"])
        self.assertEqual(selection["concept"]["term"], "정책금리")
        self.assertIn("3.75~4%", selection["concept"]["application"])
        self.assertEqual(collect(AFTER, CUTOFF, seen=[ORIGINAL], fetch=feed)["status"], "pending")
        self.assertEqual(collect(AFTER - timedelta(days=1), AFTER, fetch=feed)["status"], "pending")

    def test_failed_and_invalid_feeds_are_pending(self):
        def unavailable(url):
            if url == SOURCES["policy"][0]:
                raise TimeoutError()
            return "<!DOCTYPE rss><rss>"
        self.assertEqual(collect(AFTER, CUTOFF, fetch=unavailable)["status"], "pending")
        self.assertIsNone(policy_rate("The target range could change next meeting."))
        self.assertIn("0.4%", release_fact("prices", "In October, the Consumer Price Index for All Urban Consumers rose 0.4 percent, seasonally adjusted."))
        self.assertIn("4.1%", release_fact("jobs", "Employment rose in October and the unemployment rate changed little at 4.1 percent."))

    def test_news_isolated_from_publication_and_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            news = collect(AFTER, CUTOFF, fetch=feed)
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
            self.assertEqual(pending["status"], "pending")
            build(root, DAY, section02=pending)
            self.assertEqual(manuscript.read_bytes(), original)
            doc = json.loads(original)
            doc["section02"]["issues"][0]["publishedAt"] = "2026-11-10T00:00:00+09:00"
            with self.assertRaises(ValueError):
                validate(doc)


    def test_overnight_bls_release_and_weekend_or_holiday_gap(self):
        friday = datetime.fromisoformat("2026-11-13T18:30:00+09:00")
        release = friday + timedelta(hours=4)
        monday = friday + timedelta(days=3)
        tuesday = monday + timedelta(days=1)
        friday_cpi = LATE_CPI.replace("11122026", "11132026").replace("2026-11-12", "2026-11-13")

        def prices_only(url):
            return friday_cpi if url == SOURCES["prices"][0] else "<feed/>"

        self.assertEqual(collect(AFTER, friday, fetch=prices_only)["status"], "pending")
        self.assertEqual(collect(AFTER, release - timedelta(seconds=1), fetch=prices_only)["status"], "pending")
        self.assertEqual(collect(AFTER, release, fetch=prices_only)["status"], "ready")
        for cutoff in (monday, tuesday):
            news = collect(friday, cutoff, fetch=prices_only)
            self.assertEqual(datetime.fromisoformat(news["issues"][0]["publishedAt"]), release)
            self.assertEqual(news["concept"]["term"], "계절조정")
        self.assertEqual(collect(release, tuesday, fetch=prices_only)["status"], "pending")

    def test_previous_report_cutoff_and_duplicate_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            day = date(2026, 11, 16)
            cutoff = datetime.fromisoformat("2026-11-16T18:15:00+09:00")
            build(root, DAY, section02=collect(AFTER, CUTOFF, fetch=feed))

            def collect_process(args, **kwargs):
                self.assertEqual(kwargs["timeout"], 13)
                self.assertEqual(args[2:5], [CUTOFF.isoformat(), cutoff.isoformat(), ORIGINAL])
                return subprocess.CompletedProcess(args, 0, json.dumps(
                    collect(datetime.fromisoformat(args[2]), cutoff, seen=args[4:], fetch=feed)))

            with patch("scripts.refresh_public_market.subprocess.run", side_effect=collect_process):
                self.assertEqual(prepare_section02(root, day, cutoff)["status"], "ready")

    def test_manuscript_rejects_future_time_duplicate_topic_and_invalid_source(self):
        from copy import deepcopy
        from scripts.build_public_reports import make_doc

        doc = dict(make_doc(DAY), section02=collect(AFTER, CUTOFF, fetch=feed))
        validate(doc)
        for key, value in (("publishedAt", "2026-11-12T18:30:01+09:00"),
                           ("publishedAt", "2026-11-12T18:00:00"),
                           ("source", "https://example.invalid/monetary20261111a.htm")):
            invalid = deepcopy(doc)
            invalid["section02"]["issues"][0][key] = value
            with self.assertRaises(ValueError):
                validate(invalid)
        duplicate = deepcopy(doc)
        duplicate["section02"]["issues"].append(
            dict(duplicate["section02"]["issues"][0], source=ORIGINAL + "?repeat"))
        with self.assertRaises(ValueError):
            validate(duplicate)
