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
        self.assertEqual(collect(AFTER, CUTOFF, seen=[ORIGINAL], fetch=feed)["outcomes"]["policy"], "duplicate")
        self.assertEqual(collect(AFTER - timedelta(days=1), AFTER, fetch=feed)["status"], "pending")

    def test_failed_and_invalid_feeds_are_pending(self):
        def unavailable(url):
            if url == SOURCES["policy"][0]:
                raise TimeoutError()
            return "<!DOCTYPE rss><rss>"
        result = collect(AFTER, CUTOFF, fetch=unavailable)
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["outcomes"], {"policy": "timeout", "prices": "error", "jobs": "error"})
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

    def test_news_and_close_revisions_preserve_both_orders(self):
        from scripts.refresh_public_market import dated_study, refresh
        from test_regional_market_refresh import Source, collect as prices, configuration

        early = CUTOFF.replace(hour=17, minute=7)
        late = CUTOFF.replace(minute=30)
        release_url = ORIGINAL.replace("1111a", "1112a")
        rss = RSS.replace(ORIGINAL, release_url).replace("Wed, 11 Nov 2026 19:00", "Thu, 12 Nov 2026 09:20")

        def fetch(url):
            return {SOURCES["policy"][0]: rss, release_url: RELEASE,
                    SOURCES["prices"][0]: LATE_CPI, SOURCES["jobs"][0]: "<feed/>"}[url]

        for close_first, article_first in ((True, False), (False, False), (True, True), (False, True)):
            with self.subTest(close_first=close_first, article=article_first), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "config").mkdir()
                (root / "config/market-sources.json").write_text(json.dumps(configuration()))
                reviewed = root / "config/reviewed-economic-news.json"
                article = ReviewedArticleTests.article(
                    1, "orders_exports", "2026-11-12T18:20:00+09:00")
                if article_first:
                    reviewed.write_text(json.dumps([article]))
                def run(at, verified, available):
                    def quotes(config, region, existing, now):
                        source = Source(day=DAY, previous=DAY-timedelta(days=1))
                        checker = source if verified else Source(missing={"kospi","kosdaq"}, day=DAY,
                                                                 previous=DAY-timedelta(days=1))
                        return prices(config, region, existing, now, {"yahoo": source, "naver": checker})
                    def news(root, day, cutoff):
                        return collect(AFTER, cutoff,
                                       fetch=fetch if available and not article_first else lambda url: "<rss><channel/></rss>",
                                       reviewed_path=reviewed if available and article_first else None)
                    refresh(root, "kr", at, quotes, news=news, news_slot=at.time())

                run(early, False, True)
                original = root / f"content/daily/{DAY}.json"
                first = original.read_bytes()
                first_html = (root / f"reports/daily/{DAY}.html").read_bytes()
                self.assertEqual(json.loads(first)["section02"]["status"], "pending")
                run(late, close_first, not close_first)
                run(late, True, True)
                current = dated_study(root, DAY)
                self.assertEqual(current["revision"], 2)
                self.assertTrue(all(row["verified"] for row in current["indices"]))
                self.assertEqual(current["lesson"], json.loads(first)["lesson"])
                self.assertEqual(current["section02"]["firstCutoff"], early.isoformat())
                self.assertEqual([i["source"] for i in current["section02"]["issues"]],
                                 [article["source"] if article_first else release_url])
                self.assertEqual(original.read_bytes(), first)
                self.assertEqual((root / f"reports/daily/{DAY}.html").read_bytes(), first_html)
                page = (root / "reports/latest.html").read_text()
                self.assertIn("정답과 해설 보기", page)
                self.assertIn(current["lesson"]["question"], page)
                run(late, True, True)
                self.assertEqual(dated_study(root, DAY), current)


class ReviewedArticleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "reviewed-economic-news.json"

    @staticmethod
    def article(number, topic, published, **fields):
        return dict(
            topic=topic, publishedAt=published, verified=True, region="kr",
            source=f"https://n.news.naver.com/article/050/{number:010d}",
            sourceName="한경비즈니스", eventId=f"synthetic-{number}",
            title="테스트용 기사", fact="테스트용 확인 사실",
            interpretation="테스트용 시장 해석", study="테스트용 공부 포인트",
        ) | fields

    def collect(self, rows, cutoff=CUTOFF, seen=()):
        self.path.write_text(json.dumps(rows), encoding="utf-8")
        return collect(AFTER, cutoff, seen=seen, fetch=feed, reviewed_path=self.path)

    def test_domestic_priority_and_official_fallback(self):
        domestic = self.article(1, "market_links", "2026-11-12T09:14:00+09:00",
                                observedAt="2026-11-12T09:10:00+09:00")
        exports = self.article(2, "orders_exports", "2026-11-12T14:08:00+09:00", priority=3)
        foreign = self.article(3, "global_sentiment", "2026-11-12T08:00:00+09:00",
                               region="overseas", priority=3)
        self.assertEqual([row["topic"] for row in self.collect([domestic, exports, foreign])["issues"]],
                         ["orders_exports", "market_links"])
        self.assertEqual([row["topic"] for row in self.collect([exports])["issues"]],
                         ["orders_exports", "policy"])
        self.assertEqual([row["topic"] for row in self.collect([])["issues"]], ["policy"])

    def test_time_validation_and_history(self):
        article = self.article(1, "orders_exports", "2026-11-12T17:08:00+09:00")
        self.assertEqual(self.collect([article], CUTOFF.replace(hour=17, minute=7))
                         ["outcomes"]["reviewed_articles"], "outside_window")
        self.assertEqual(self.collect([article], seen=["event:synthetic-1"])
                         ["outcomes"]["reviewed_articles"], "duplicate")
        invalid = dict(article, topic="market_links")
        self.assertEqual(self.collect([invalid])["outcomes"]["reviewed_articles"], "validation_failed")
        copied = dict(article, topic="global_sentiment", eventId="another-id")
        self.assertEqual(len(self.collect([article, copied])["issues"]), 2)
        self.assertEqual(sum("eventId" in item for item in self.collect([article, copied])["issues"]), 1)

    def test_article_revision_keeps_original_and_existing_official_news(self):
        from scripts.refresh_public_market import supplement_news

        early = CUTOFF.replace(hour=17, minute=7)
        now = CUTOFF.replace(minute=31)
        build(self.root, DAY, section02=self.collect([], early),
              market={"indices": [], "marketStatus": [], "firstPublishedAt": early.isoformat()})
        path = self.root / f"content/daily/{DAY}.json"
        original = path.read_bytes()
        article = self.article(1, "market_links", "2026-11-12T17:08:00+09:00",
                               observedAt="2026-11-12T09:10:00+09:00")
        news = self.collect([article])
        self.assertTrue(supplement_news(self.root, DAY, CUTOFF, now, lambda *_: news))
        self.assertFalse(supplement_news(self.root, DAY, CUTOFF, now, lambda *_: news))
        self.assertEqual(path.read_bytes(), original)
        page = (self.root / "reports/latest.html").read_text()
        for text in ("2026-11-12 17:08", "내용 기준 시각 · 2026-11-12 09:10", "정책금리",
                     "국제 증시의 연결", "오전 등락률", json.loads(original)["lesson"]["question"]):
            self.assertIn(text, page)
