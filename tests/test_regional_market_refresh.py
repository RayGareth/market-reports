"""Regional publication tests. All provider observations are synthetic."""
import json
import shutil
import subprocess
import tempfile
import unittest
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
        self.assertEqual([row["id"] for row in morning["indices"]], ["sp500"])
        self.assertEqual(morning["indices"][0]["closeAt"], CLOSE.isoformat())
        self.assertEqual(morning["indices"][0]["verifiedAt"], (MORNING + timedelta(seconds=2)).isoformat())
        self.assertEqual(morning["indices"][0]["changePct"], 1.0)
        self.assertEqual(morning["marketStatus"][1]["collection"], "partial")
        self.assertEqual(morning["marketStatus"][1]["crossCheck"], "pending")

        adapters = {"yahoo": Source(), "fred": Source()}
        afternoon = collect(cfg, "us", morning["indices"], MORNING + timedelta(hours=6), adapters)
        self.assertEqual(adapters["fred"].calls, ["nasdaq"])
        self.assertEqual(adapters["yahoo"].calls, ["nasdaq"])
        self.assertEqual(afternoon["indices"][0], morning["indices"][0])

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
        adapters = {"yahoo": Source(), "fred": Source(missing=("sp500", "nasdaq"))}
        result = collect(cfg, "us", [old], adapters=adapters)
        self.assertEqual(result["indices"], [old])
        self.assertEqual(result["marketStatus"][0]["expectedAsOf"], DAY.isoformat())
        self.assertIn("최신 거래일 검증 대기", result["marketStatus"][0]["message"])
        cfg["providers"]["fred"]["enabled"] = False
        result = collect(cfg, "us", [old], adapters=adapters)
        self.assertEqual(result["indices"], [])

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
