import json
import tempfile
import unittest
from datetime import date, datetime, time
from pathlib import Path

from scripts.check_publication import check, target_date
from scripts.section02_news import EVENING_SLOTS, KST


class PublicationCheckTests(unittest.TestCase):
    def test_delayed_friday_check_and_early_news_cutoff(self):
        self.assertEqual(target_date(datetime(2026, 11, 21, 2, tzinfo=KST)), date(2026, 11, 20))
        self.assertEqual(EVENING_SLOTS["7 8 * * 1-5"], time(17, 7))

    def test_public_artifacts_must_match_target_date(self):
        day = "2026-11-19"
        entry = {"date": day, "url": f"daily/{day}-r001.html"}
        archive = json.dumps([entry])
        title = f"<title>{day} | Market Daily</title>"
        responses = {"index.json": archive, entry["url"]: title, "latest.html": title}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reports").mkdir()
            (root / "reports/index.json").write_text(archive)
            (root / "content/daily").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "manuscript missing"):
                check(root, day, responses.__getitem__)
            (root / f"content/daily/{day}.json").write_text(json.dumps({"date": day}))
            check(root, day, responses.__getitem__)
            for path, bad in (("latest.html", title.replace(day, "2026-11-18")),
                              ("index.json", "[]"), (entry["url"], "not a report")):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    check(root, day, (responses | {path: bad}).__getitem__)
