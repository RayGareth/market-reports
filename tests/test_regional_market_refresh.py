"""Regional publication tests. All provider observations are synthetic."""
import json
import io
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.build_public_reports import build, generate, make_doc, market_close_label
from scripts.market_close import collect_region, session_close
from scripts.market_sources import Bar
from scripts.publish_public_study import publish
from scripts.refresh_public_market import refresh, revise_dated_study

ROOT = Path(__file__).resolve().parents[1]
REVIEWED = "2026-12-31"
DAY = date(2026, 11, 4)
PREVIOUS = date(2026, 11, 3)
CLOSE = datetime.fromisoformat("2026-11-04T21:00:00+00:00")
MORNING = datetime.fromisoformat("2026-11-04T23:00:00+00:00")


class Source:
    def __init__(self, missing=(), day=DAY, previous=PREVIOUS):
        self.calls = []
        self.missing = missing
        self.day = day
        self.previous = previous

    def fetch(self, instrument, target):
        self.calls.append(instrument)
        prices = [Bar(self.previous.isoformat(), 100)]
        if instrument not in self.missing:
            prices.append(Bar(self.day.isoformat(), 101))
        return prices


def configuration():
    config = json.loads((ROOT / "config/market-sources.json").read_text())
    for key in ("yahoo", "naver", "fred"):
        config["providers"][key].update(enabled=True, collectionAllowed=True)
    return config


def collect(config, region, existing=(), now=MORNING, adapters=None):
    if region == "kr":
        target, previous, _ = session_close("XKRX", now, REVIEWED)
        if adapters is None:
            adapters = {key: Source(day=target, previous=previous) for key in ("yahoo", "naver")}
        return collect_region(config, region, existing, now, adapters,
                              verified_clock=lambda: now + timedelta(seconds=2))
    return collect_region(
        config, region, existing, now,
        adapters if adapters is not None else {key: Source() for key in ("yahoo", "naver", "fred")},
        lambda *args: (DAY, PREVIOUS, CLOSE),
        verified_clock=lambda: now + timedelta(seconds=2),
    )


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


class RegionalRefreshTests(unittest.TestCase):
    def test_section_01_closing_timestamp_and_signed_change(self):
        self.assertEqual(market_close_label("2026-11-04T21:00:00+00:00"), "11.05 06:00 KST")
        self.assertEqual(market_close_label("invalid"), "")
        document = make_doc(DAY)
        index = collect(configuration(), "us")["indices"][0]
        document["indices"] = [index]
        page = generate(document)
        self.assertIn("마감 11.05 06:00 KST", page)
        self.assertIn('class="market-up">+1.00%</td>', page)
        index["changePct"] = -0.85
        page = generate(document)
        self.assertIn('class="market-down">−0.85%</td>', page)

    def test_exact_cross_check_pairs_and_source_switches(self):
        cfg = configuration()
        adapters = {key: Source() for key in ("yahoo", "naver", "fred", "fsc")}
        kr = collect(cfg, "kr", adapters=adapters)
        self.assertEqual([row["id"] for row in kr["indices"]], ["kospi", "kosdaq"])
        self.assertEqual(adapters["naver"].calls, ["kospi", "kosdaq"])
        self.assertEqual(adapters["fred"].calls, [])
        self.assertEqual(adapters["fsc"].calls, [])

        cfg["providers"]["fred"]["enabled"] = False
        blocked = collect(cfg, "us", adapters=adapters)
        self.assertEqual(blocked["indices"], [])
        self.assertEqual(adapters["fred"].calls, [])
        self.assertEqual(adapters["yahoo"].calls, ["kospi", "kosdaq"])
        self.assertTrue(all(state["status"] == "source_unavailable" for state in blocked["marketStatus"]))

    def test_delayed_us_close_updates_matching_date_as_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / "config").mkdir()
            (repo / "config/market-sources.json").write_text(json.dumps(configuration()))
            build(repo, DAY)
            report = repo / "reports/daily/2026-11-04.html"
            original = report.read_bytes()

            # Thu 08:00 KST receives Wed U.S. closes.
            refresh(repo, "us", MORNING, collect)
            revision = repo / "reports/daily/2026-11-04-r001.html"
            self.assertTrue(revision.is_file())
            self.assertEqual(report.read_bytes(), original)
            self.assertIn("101.00", revision.read_text())
            self.assertIn("마감 11.05 06:00 KST", revision.read_text())
            archive = json.loads((repo / "reports/index.json").read_text())
            self.assertEqual(archive[0]["url"], "daily/2026-11-04-r001.html")
            self.assertEqual(json.loads((repo / "data/public-market.json").read_text())["reportDate"],
                             DAY.isoformat())

            # A successful repeat check must not create a duplicate revision.
            refresh(repo, "us", MORNING + timedelta(hours=6), collect)
            self.assertEqual(len(list(report.parent.glob("2026-11-04-r*.html"))), 1)
            self.assertFalse((repo / "reports/daily/2026-11-05.html").exists())

    def test_kr_late_close_updates_existing_study_as_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            build(repo, DAY)
            report = repo / "reports/daily/2026-11-04.html"
            original = report.read_bytes()
            result = collect(configuration(), "kr")
            self.assertTrue(revise_dated_study(repo, DAY, "kr", result))
            self.assertTrue((repo / "reports/daily/2026-11-04-r001.html").is_file())
            self.assertEqual(report.read_bytes(), original)
            self.assertFalse(revise_dated_study(repo, DAY, "kr", result))

    def test_us_retries_only_missing_index_and_preserves_verification_time(self):
        cfg = configuration()
        adapters = {"yahoo": Source(), "fred": Source(missing=("nasdaq",))}
        morning = collect(cfg, "us", adapters=adapters)
        self.assertEqual([row["id"] for row in morning["indices"]], ["sp500", "nasdaq"])
        self.assertEqual(morning["indices"][0]["closeAt"], CLOSE.isoformat())
        self.assertEqual(morning["indices"][0]["verifiedAt"], (MORNING + timedelta(seconds=2)).isoformat())
        self.assertEqual(morning["indices"][0]["changePct"], 1.0)
        self.assertEqual(morning["marketStatus"][1]["collection"], "partial")
        self.assertEqual(morning["marketStatus"][1]["crossCheck"], "pending")
        pending = morning["indices"][1]
        self.assertFalse(pending["verified"])
        self.assertEqual(pending["verificationStatus"], "pending")
        self.assertEqual(pending["previousAsOf"], PREVIOUS.isoformat())
        self.assertEqual(pending["collectedAt"], (MORNING + timedelta(seconds=2)).isoformat())
        self.assertNotIn("verificationSource", pending)
        doc = make_doc(DAY)
        for changes in ({"region": "kr"}, {"collectedAt": "2026-11-04T20:00:00Z"},
                        {"collectedAt": "2026-11-04T23:00:00"},
                        {"verificationSource": "https://fred.stlouisfed.org/series/NASDAQCOM"},
                        {"publication": {"status": "private_only"}}):
            with self.subTest(changes=changes):
                doc["indices"] = [{**pending, **changes}]
                with self.assertRaises(ValueError):
                    generate(doc)

        adapters = {"yahoo": Source(), "fred": Source()}
        afternoon = collect(cfg, "us", morning["indices"], MORNING + timedelta(hours=6), adapters)
        self.assertEqual(adapters["fred"].calls, ["nasdaq"])
        self.assertEqual(adapters["yahoo"].calls, ["nasdaq"])
        self.assertEqual(afternoon["indices"][0], morning["indices"][0])
        self.assertTrue(afternoon["indices"][1]["verified"])
        self.assertEqual(afternoon["indices"][1]["collectedAt"], pending["collectedAt"])
        self.assertEqual(afternoon["marketStatus"][1]["crossCheck"], "passed")

        adapters = {"yahoo": Source(), "fred": Source()}
        evening = collect(cfg, "us", afternoon["indices"], MORNING + timedelta(hours=10), adapters)
        self.assertEqual(adapters["fred"].calls, [])
        self.assertEqual(adapters["yahoo"].calls, [])
        self.assertEqual(evening["indices"], afternoon["indices"])

    def test_retains_old_verified_quote_with_original_dates_when_sources_work(self):
        cfg = configuration()
        old = collect(cfg, "us")["indices"][0]
        old.update(asOf=PREVIOUS.isoformat(), closeAt="2026-11-03T21:00:00+00:00",
                   verifiedAt="2026-11-03T23:01:00+00:00")
        adapters = {"yahoo": Source(missing=("sp500", "nasdaq")), "fred": Source()}
        result = collect(cfg, "us", [old], adapters=adapters)
        self.assertEqual(result["indices"], [old])
        self.assertEqual(result["marketStatus"][0]["expectedAsOf"], DAY.isoformat())
        self.assertIn("최신 거래일 검증 대기", result["marketStatus"][0]["message"])
        cfg["providers"]["fred"]["enabled"] = False
        result = collect(cfg, "us", [old], adapters=adapters)
        self.assertEqual(result["indices"], [])

    def test_us_provisional_requires_valid_yahoo_and_a_transient_comparison_failure(self):
        class Reply:
            def __init__(self, bars=None):
                self.bars = bars

            def fetch(self, instrument, target):
                if self.bars is None:
                    raise TimeoutError("DO_NOT_PUBLISH_THIS")
                return self.bars

        cfg = configuration()
        valid = [Bar(PREVIOUS.isoformat(), 100), Bar(DAY.isoformat(), 101)]
        delayed = collect(cfg, "us", adapters={"yahoo": Reply(valid), "fred": Reply()})
        self.assertTrue(all(state["status"] == "single_source" for state in delayed["marketStatus"]))
        self.assertTrue(all(state["verificationReason"] == "provider_error" for state in delayed["marketStatus"]))
        self.assertNotIn("DO_NOT_PUBLISH_THIS", json.dumps(delayed))
        retry = collect(cfg, "us", delayed["indices"], adapters={"yahoo": Reply(), "fred": Reply(valid)})
        self.assertEqual(retry["indices"], delayed["indices"])
        for bars in (valid[1:], [*valid, valid[1]], [valid[0], Bar(DAY.isoformat(), 0)],
                     [valid[0], Bar(DAY.isoformat(), 101, 9.5)],
                     [valid[0], Bar("2026-11-05", 101)]):
            with self.subTest(bars=bars):
                self.assertEqual(collect(cfg, "us", adapters={"yahoo": Reply(bars), "fred": Reply()})["indices"], [])
        for fred in ([valid[0], Bar(DAY.isoformat(), 103)],
                     [Bar(PREVIOUS.isoformat(), 97), valid[1]]):
            result = collect(cfg, "us", adapters={"yahoo": Reply(valid), "fred": Reply(fred)})
            self.assertEqual(result["indices"], [])
            self.assertTrue(all(state["crossCheck"] == "failed" for state in result["marketStatus"]))
        result = collect(cfg, "us", adapters={"yahoo": Reply(valid), "fred": Reply([valid[0], Bar(DAY.isoformat(), 0)])})
        self.assertTrue(all(row["verificationStatus"] == "pending" for row in result["indices"]))
        self.assertTrue(all(state["verificationReason"] == "invalid" for state in result["marketStatus"]))

    def test_long_pending_close_survives_new_sessions_and_advances_without_fred(self):
        class Feed:
            def __init__(self, mode):
                self.mode = mode

            def fetch(self, instrument, target):
                if self.mode == 'timeout':
                    raise TimeoutError('private diagnostic')
                if self.mode == 'invalid':
                    return [Bar((target - timedelta(days=1)).isoformat(), 100), Bar(target.isoformat(), 0)]
                return [Bar((target - timedelta(days=1)).isoformat(), 100), Bar(target.isoformat(), 101)]

        def run(now, rows=(), mode='valid'):
            return collect_region(configuration(), 'us', rows, now,
                                  {'yahoo': Feed(mode), 'fred': Feed('timeout')},
                                  verified_clock=lambda: now + timedelta(seconds=2))

        initial = run(MORNING)
        rows = initial['indices']
        for days in (1, 2, 7, 14, 28):
            delayed = run(MORNING + timedelta(days=days), rows, 'timeout')
            self.assertEqual(delayed['indices'], rows)
            self.assertTrue(all(state['expectedAsOf'] > rows[0]['asOf'] for state in delayed['marketStatus']))
            self.assertTrue(all(row['verificationStatus'] == 'pending' for row in delayed['indices']))
        invalid = run(MORNING + timedelta(days=1), rows, 'invalid')
        self.assertEqual(invalid['indices'], rows)
        self.assertTrue(all(state['status'] == 'invalid' for state in invalid['marketStatus']))
        advanced = run(MORNING + timedelta(days=1), rows)
        self.assertTrue(all(row['asOf'] > rows[0]['asOf'] for row in advanced['indices']))
        self.assertTrue(all(state['status'] == 'single_source' for state in advanced['marketStatus']))
        # An invalid replacement for the same session is never accepted.
        self.assertEqual(run(MORNING, rows, 'invalid')['indices'], [])

    def test_nov06_missing_sp500_is_retried_without_replacing_newer_report(self):
        from scripts.refresh_public_market import retry_dated_us_study

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for folder in ('content/daily', 'reports/daily'):
                (root / folder).mkdir(parents=True)
                for suffix in ('', '-r001'):
                    extension = '.json' if folder.startswith('content') else '.html'
                    source = ROOT / folder / ('2026-11-06' + suffix + extension)
                    shutil.copy2(source, root / folder / source.name)
            originals = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            build(root, date(2026, 11, 10))
            dashboard = root / "data/public-market.json"
            latest_snapshot = json.loads(dashboard.read_text())
            latest_snapshot["checkedAt"] = "2026-11-11T00:00:00+00:00"
            dashboard.write_text(json.dumps(latest_snapshot))
            originals[dashboard] = dashboard.read_bytes()
            current = {'marketStatus': [{'expectedAsOf': '2026-11-09'}]}
            calls = []

            def feed(config, region, existing, now):
                calls.append(config['providers']['yahoo']['instruments'])
                return collect_region(config, region, existing, now,
                                      {'yahoo': Source(day=date(2026, 11, 6), previous=date(2026, 11, 5)),
                                       'fred': Source(missing=('sp500',), day=date(2026, 11, 6), previous=date(2026, 11, 5))},
                                      verified_clock=lambda: datetime.fromisoformat('2026-11-11T00:00:00+00:00'))

            self.assertEqual(retry_dated_us_study(root, date(2026, 11, 11), configuration(), current, feed), 1)
            edition = root / 'content/daily/2026-11-06-r002.json'
            row = next(row for row in json.loads(edition.read_text())['indices'] if row['id'] == 'sp500')
            self.assertEqual(row['verificationStatus'], 'pending')
            self.assertEqual(calls, [['sp500']])
            self.assertEqual(retry_dated_us_study(root, date(2026, 11, 11), configuration(), current, feed), 0)
            self.assertFalse((root / 'content/daily/2026-11-06-r003.json').exists())
            for path, content in originals.items():
                self.assertEqual(path.read_bytes(), content)
            archive = json.loads((root / 'reports/index.json').read_text())
            self.assertIn('2026-11-10', archive[0]['url'])
            self.assertIn('2026-11-06-r002', archive[1]['url'])

    def test_invalid_yahoo_withdraws_dated_provisional_with_review_notice(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pending = collect(configuration(), 'us', adapters={
                'yahoo': Source(), 'fred': Source(missing=('sp500', 'nasdaq'))})
            build(root, DAY, market=pending)
            before = (root / f'reports/daily/{DAY}.html').read_bytes()
            invalid = {'indices': [], 'marketStatus': [
                dict(state, status='invalid', message='수치 검증 보류')
                for state in pending['marketStatus']]}
            self.assertTrue(revise_dated_study(root, DAY, 'us', invalid))
            reviewed = root / f'reports/daily/{DAY}-r001.html'
            self.assertIn('재검토 중', reviewed.read_text())
            self.assertNotIn('101.00', reviewed.read_text())
            self.assertFalse(revise_dated_study(root, DAY, 'us', invalid))
            self.assertEqual((root / f'reports/daily/{DAY}.html').read_bytes(), before)

    def test_us_disagreement_withdraws_provisional_and_recovers_without_duplicate_editions(self):
        class Different(Source):
            def fetch(self, instrument, target):
                return [Bar(PREVIOUS.isoformat(), 100), Bar(DAY.isoformat(), 103)]

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config").mkdir()
            (root / "config/market-sources.json").write_text(json.dumps(configuration()))
            build(root, DAY)
            originals = {p: p.read_bytes() for p in (
                root / f"reports/daily/{DAY}.html", root / f"content/daily/{DAY}.json"
            )}
            build(root, DAY + timedelta(days=1))
            latest = (root / "reports/latest.html").read_bytes()
            dashboard = root / "data/public-market.json"
            seed = json.loads(dashboard.read_text())
            retained = collect(configuration(), "us")["indices"][0]
            retained.update(asOf=PREVIOUS.isoformat(), previousAsOf="2026-11-02",
                            closeAt="2026-11-03T21:00:00+00:00", collectedAt="2026-11-03T23:00:00+00:00",
                            verifiedAt="2026-11-03T23:01:00+00:00")
            seed["indices"] = [retained]
            dashboard.write_text(json.dumps(seed))

            def run(fred, offset):
                def feed(config, region, existing, now):
                    return collect(config, region, existing, now, {"yahoo": Source(), "fred": fred})
                refresh(root, "us", MORNING + timedelta(hours=offset), feed)
                return json.loads(dashboard.read_text())

            pending = run(Source(missing=("sp500", "nasdaq")), 0)
            self.assertEqual(pending["lastVerifiedUs"], [retained])
            first = root / f"reports/daily/{DAY}-r001.html"
            pending_page = first.read_bytes()
            self.assertIn("교차 검증 전", pending_page.decode())
            self.assertNotIn("FRED", pending_page.decode())
            run(Source(missing=("sp500", "nasdaq")), 1)
            self.assertEqual(len(list(first.parent.glob(f"{DAY}-r*.html"))), 1)

            conflict = run(Different(), 2)
            self.assertEqual(conflict["indices"], [retained])
            self.assertEqual(conflict["marketStatus"][0]["status"], "disagreement")
            second = first.with_name(f"{DAY}-r002.html")
            self.assertIn("재검토 중", second.read_text())
            self.assertNotIn("101.00", second.read_text())
            self.assertEqual(run(Source(missing=("sp500", "nasdaq")), 3)["indices"], [retained])
            self.assertEqual(len(list(first.parent.glob(f"{DAY}-r*.html"))), 2)

            resolved = run(Source(), 4)
            self.assertTrue(all(row["verified"] for row in resolved["indices"]))
            third = first.with_name(f"{DAY}-r003.html")
            self.assertIn("교차 검증 완료", third.read_text())
            self.assertEqual(first.read_bytes(), pending_page)
            self.assertTrue(all(path.read_bytes() == before for path, before in originals.items()))
            self.assertEqual((root / "reports/latest.html").read_bytes(), latest)
            archive = json.loads((root / "reports/index.json").read_text())
            self.assertEqual(archive[1]["url"], f"daily/{DAY}-r003.html")
            run(Source(), 5)
            self.assertEqual(len(list(first.parent.glob(f"{DAY}-r*.html"))), 3)

    def test_late_comparison_revises_older_session_without_replacing_latest_snapshot(self):
        class Feed:
            def __init__(self, missing=False):
                self.missing = missing

            def fetch(self, instrument, target):
                return [Bar((target - timedelta(days=1)).isoformat(), 100)] + (
                    [] if self.missing else [Bar(target.isoformat(), 101)]
                )

        def feed(config, region, existing, now):
            return collect_region(config, region, existing, now,
                                  {"yahoo": Feed(), "fred": Feed(missing=now == MORNING)},
                                  verified_clock=lambda: now + timedelta(seconds=2))

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config").mkdir()
            (root / "config/market-sources.json").write_text(json.dumps(configuration()))
            build(root, DAY)
            refresh(root, "us", MORNING, feed)
            new_day = DAY + timedelta(days=1)
            refresh(root, "us", MORNING + timedelta(days=1), feed)
            old_doc = json.loads((root / f"content/daily/{DAY}-r002.json").read_text())
            self.assertTrue(all(row["verified"] for row in old_doc["indices"]))
            snapshot = json.loads((root / "data/public-market.json").read_text())
            self.assertEqual({row["asOf"] for row in snapshot["indices"]}, {new_day.isoformat()})

    def test_real_exchange_calendar_close_metadata_including_holiday_dst_and_early_close(self):
        cases = [
            ("XKRX", "2026-11-04T09:00:00+00:00", DAY, "2026-11-04T06:30:00+00:00"),
            ("XNYS", "2026-11-04T23:00:00+00:00", DAY, "2026-11-04T21:00:00+00:00"),
            ("XNAS", "2026-07-03T23:00:00+00:00", date(2026, 7, 2), "2026-07-02T20:00:00+00:00"),
            ("XNAS", "2026-11-27T23:00:00+00:00", date(2026, 11, 27), "2026-11-27T18:00:00+00:00"),
        ]
        for exchange, now, day, close in cases:
            with self.subTest(exchange=exchange, now=now):
                actual_day, _, actual_close = session_close(exchange, datetime.fromisoformat(now), REVIEWED)
                self.assertEqual(actual_day, day)
                self.assertEqual(actual_close.isoformat(), close)

    def test_kr_first_publication_waits_for_same_day_verified_close(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / "config").mkdir()
            (repo / "config/market-sources.json").write_text(json.dumps(configuration()))
            build(repo, date(2026, 10, 8))
            archive = repo / "reports/index.json"
            original_archive = archive.read_bytes()
            original = repo / "reports/daily/2026-10-08.html"
            original_html = original.read_bytes()
            # Friday October 9 is a Korean exchange holiday. On November 4
            # there is also no settled current close before 16:00 KST.
            for stamp in ("2026-10-09T09:00:00+00:00",
                          "2026-11-04T06:29:00+00:00",
                          "2026-11-04T06:59:00+00:00"):
                with self.subTest(now=stamp):
                    refresh(repo, "kr", datetime.fromisoformat(stamp), collect)
                    self.assertEqual(archive.read_bytes(), original_archive)
                    self.assertEqual(original.read_bytes(), original_html)
                    self.assertFalse((repo / "reports/daily/2026-10-09.html").exists())
                    self.assertFalse((repo / "reports/daily/2026-11-04.html").exists())

            publish_time = datetime.fromisoformat("2026-11-04T09:00:00+00:00")
            def missing_close(config, region, existing, now):
                feeds = {"yahoo": Source(), "naver": Source(missing=("kospi", "kosdaq"))}
                return collect(config, region, existing, now, feeds)

            refresh(repo, "kr", publish_time, missing_close)
            self.assertEqual(archive.read_bytes(), original_archive)
            self.assertFalse((repo / "content/daily/2026-11-04.json").exists())

            refresh(repo, "kr", publish_time + timedelta(minutes=15), collect)
            report = repo / "reports/daily/2026-11-04.html"
            published = report.read_bytes()
            self.assertIn(b"101.00", published)
            self.assertEqual([x["date"] for x in json.loads(archive.read_text())],
                             ["2026-11-04", "2026-10-08"])
            refresh(repo, "kr", publish_time + timedelta(minutes=30), collect)
            self.assertEqual(report.read_bytes(), published)
            self.assertEqual(original.read_bytes(), original_html)
            self.assertEqual(list(report.parent.glob("2026-11-04-r*.html")), [])

    def test_us_never_creates_report_and_retry_does_not_rewrite_dated_study(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / "config").mkdir()
            (repo / "config/market-sources.json").write_text(json.dumps(configuration()))
            refresh(repo, "us", MORNING, collect)
            self.assertFalse((repo / "reports").exists())
            kr_now = datetime.fromisoformat("2026-11-05T09:00:00+00:00")
            refresh(repo, "kr", kr_now, collect)
            report = repo / "reports/daily/2026-11-05.html"
            original = report.read_bytes()
            refresh(repo, "kr", kr_now + timedelta(minutes=15), collect)
            refresh(repo, "us", kr_now, collect)
            self.assertEqual(report.read_bytes(), original)
            self.assertEqual(len(list(report.parent.glob("*.html"))), 1)
            snapshot = json.loads((repo / "data/public-market.json").read_text())
            self.assertEqual([row["region"] for row in snapshot["indices"]], ["kr", "kr", "us", "us"])
            self.assertEqual(snapshot["reportDate"], "2026-11-05")

    def test_kr_delayed_past_seoul_midnight_publishes_the_completed_session(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / "config").mkdir()
            (repo / "config/market-sources.json").write_text(json.dumps(configuration()))
            build(repo, date(2026, 11, 10))
            prior = repo / "reports/daily/2026-11-10.html"
            original = prior.read_bytes()
            delayed = datetime.fromisoformat("2026-11-11T16:54:23+00:00")
            report = repo / "reports/daily/2026-11-11.html"
            manuscript = repo / "content/daily/2026-11-11.json"

            class InvalidClose(Source):
                def fetch(self, instrument, target):
                    return [Bar("2026-11-10", 100), Bar("2026-11-11", 0)]

            def invalid_close(config, region, existing, now):
                valid = Source(day=date(2026, 11, 11), previous=date(2026, 11, 10))
                return collect(config, region, existing, now, {"yahoo": InvalidClose(), "naver": valid})

            with redirect_stdout(io.StringIO()) as log:
                refresh(repo, "kr", delayed, invalid_close)
            self.assertIn("kospi yahoo 2026-11-11 / 2026-11-10: Invalid price", log.getvalue())
            self.assertIn("kospi naver 2026-11-11 / 2026-11-10: valid session pair", log.getvalue())
            self.assertIn("No verified Korean close for 2026-11-11", log.getvalue())
            self.assertFalse(report.exists())
            self.assertFalse(manuscript.exists())

            refresh(repo, "kr", delayed, collect)
            self.assertTrue(report.is_file())
            doc = json.loads(manuscript.read_text())
            self.assertEqual(doc["date"], "2026-11-11")
            self.assertEqual({row["asOf"] for row in doc["indices"]}, {"2026-11-11"})
            self.assertTrue(all(row["verified"] for row in doc["indices"]))
            archive = json.loads((repo / "reports/index.json").read_text())
            self.assertEqual([row["date"] for row in archive], ["2026-11-11", "2026-11-10"])
            self.assertEqual(archive[0]["url"], "daily/2026-11-11.html")
            self.assertFalse((report.parent / "2026-11-12.html").exists())
            self.assertEqual(prior.read_bytes(), original)

            generated = (report.read_bytes(), manuscript.read_bytes())
            refresh(repo, "kr", delayed + timedelta(minutes=15), collect)
            self.assertEqual((report.read_bytes(), manuscript.read_bytes()), generated)
            self.assertEqual(list(report.parent.glob("2026-11-11-r*.html")), [])

    def test_kr_study_excludes_stale_us_snapshot_when_us_slots_were_missed(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / "config").mkdir()
            (repo / "config/market-sources.json").write_text(json.dumps(configuration()))
            refresh(repo, "us", MORNING, collect)
            # By Friday evening in Seoul, the completed U.S. session is Nov 5.
            # The Nov 4 cached dashboard values must stay dated Nov 4 and
            # must not enter the new study note as the currently expected close.
            kr_now = datetime.fromisoformat("2026-11-06T09:00:00+00:00")
            refresh(repo, "kr", kr_now, collect)
            doc = json.loads((repo / "content/daily/2026-11-06.json").read_text())
            self.assertFalse(any(row["region"] == "us" for row in doc["indices"]))
            us = [state for state in doc["marketStatus"] if state["region"] == "us"]
            self.assertEqual({state["expectedAsOf"] for state in us}, {"2026-11-05"})
            self.assertEqual({state["status"] for state in us}, {"missing"})
            live = json.loads((repo / "data/public-market.json").read_text())
            self.assertEqual({row["asOf"] for row in live["indices"] if row["region"] == "us"},
                             {"2026-11-04"})

    def test_overlapping_fast_forward_publish_preserves_both_regions(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            remote, kr, us = (base / name for name in ("remote.git", "kr", "us"))
            git(base, "init", "--bare", "--initial-branch=main", str(remote))
            git(base, "clone", str(remote), str(kr))
            git(kr, "config", "user.name", "Fixture")
            git(kr, "config", "user.email", "fixture@example.invalid")
            (kr / "scripts").mkdir()
            for name in ("build_public_reports.py", "market_close.py", "market_sources.py", "collect_close.py"):
                shutil.copy(ROOT / "scripts" / name, kr / "scripts")
            shutil.copy(ROOT / "scripts/refresh_public_market.py", kr / "scripts/refresh_impl.py")
            (kr / "scripts/refresh_public_market.py").write_text(
                "from datetime import datetime\n"
                "import sys\n"
                "from refresh_impl import ROOT, refresh, collect_region\n"
                "from market_sources import Bar\n"
                "class Feed:\n"
                "    def fetch(self, instrument, target):\n"
                "        return [Bar('2026-11-04', 100), Bar('2026-11-05', 101)]\n"
                "def collect(config, region, existing, now):\n"
                "    return collect_region(config, region, existing, now, "
                "{'yahoo': Feed(), 'naver': Feed()}, verified_clock=lambda: now)\n"
                "refresh(ROOT, sys.argv[-1], datetime.fromisoformat('2026-11-05T09:00:00+00:00'), collect)\n"
            )
            (kr / "config").mkdir()
            shutil.copy(ROOT / "config/market-sources.json", kr / "config/market-sources.json")
            # An isolated Git concurrency fixture must never request live prices.
            isolated = json.loads((kr / "config/market-sources.json").read_text())
            isolated["providers"]["fred"].update(enabled=False, collectionAllowed=False)
            (kr / "config/market-sources.json").write_text(json.dumps(isolated))
            git(kr, "add", ".")
            git(kr, "commit", "-m", "baseline")
            git(kr, "push", "origin", "main")
            git(base, "clone", str(remote), str(us))
            git(us, "config", "user.name", "Fixture")
            git(us, "config", "user.email", "fixture@example.invalid")

            def concurrent_us(attempt):
                if attempt == 0:
                    publish(us, region="us")

            publish(kr, region="kr", before_push=concurrent_us)
            head = git(remote, "rev-parse", "main")
            self.assertEqual(publish(kr, region="kr"), head)
            self.assertEqual(publish(us, region="us"), head)
            self.assertEqual(git(remote, "rev-list", "--count", "main"), "3")
            snapshot = json.loads(git(remote, "show", "main:data/public-market.json"))
            self.assertEqual([row["region"] for row in snapshot["marketStatus"]], ["kr", "kr", "us", "us"])
            self.assertEqual({row["id"] for row in snapshot["indices"]}, {"kospi", "kosdaq"})
            self.assertEqual(len(json.loads(git(remote, "show", "main:reports/index.json"))), 1)

    def test_us_publication_commits_revision_and_archive_without_replacing_original(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            remote, repo = base / "remote.git", base / "repo"
            git(base, "init", "--bare", "--initial-branch=main", str(remote))
            git(base, "clone", str(remote), str(repo))
            git(repo, "config", "user.name", "Fixture")
            git(repo, "config", "user.email", "fixture@example.invalid")
            build(repo, DAY)
            (repo / "scripts").mkdir()
            for name in ("build_public_reports.py", "market_close.py", "market_sources.py", "collect_close.py"):
                shutil.copy(ROOT / "scripts" / name, repo / "scripts")
            shutil.copy(ROOT / "scripts/refresh_public_market.py", repo / "scripts/refresh_impl.py")
            (repo / "scripts/refresh_public_market.py").write_text(
                "from datetime import datetime\n"
                "from refresh_impl import ROOT, refresh, collect_region\n"
                "from market_sources import Bar\n"
                "class Feed:\n"
                "    def fetch(self, instrument, target):\n"
                "        return [Bar('2026-11-03', 100), Bar('2026-11-04', 101)]\n"
                "now = datetime.fromisoformat('2026-11-04T23:00:00+00:00')\n"
                "def collect(config, region, existing, now):\n"
                "    return collect_region(config, region, existing, now, "
                "{'yahoo': Feed(), 'fred': Feed()}, verified_clock=lambda: now)\n"
                "refresh(ROOT, 'us', now, collect)\n"
            )
            (repo / "config").mkdir()
            (repo / "config/market-sources.json").write_text(json.dumps(configuration()))
            git(repo, "add", ".")
            git(repo, "commit", "-m", "baseline")
            git(repo, "push", "origin", "main")
            original_paths = (f"reports/daily/{DAY}.html", f"content/daily/{DAY}.json")
            originals = [git(remote, "rev-parse", f"main:{path}") for path in original_paths]

            head = publish(repo, region="us")
            archive = json.loads(git(remote, "show", "main:reports/index.json"))
            self.assertEqual([entry["url"] for entry in archive], [f"daily/{DAY}-r001.html"])
            self.assertIn("101.00", git(remote, "show", f"main:reports/daily/{DAY}-r001.html"))
            self.assertIn("101.00", git(remote, "show", "main:reports/latest.html"))
            revision = json.loads(git(remote, "show", f"main:content/daily/{DAY}-r001.json"))
            self.assertEqual({row["id"] for row in revision["indices"]}, {"sp500", "nasdaq"})
            self.assertEqual([git(remote, "rev-parse", f"main:{path}") for path in original_paths], originals)
            self.assertEqual(publish(repo, region="us"), head)
