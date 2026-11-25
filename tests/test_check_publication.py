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
        page = title + '<link href="../../assets/style.css">'
        responses = {"index.json": archive, entry["url"]: page,
                     "latest.html": title + '<link href="../assets/style.css">'}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "reports").mkdir()
            (root / "reports/index.json").write_text(archive)
            (root / "content/daily").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "manuscript missing"):
                check(root, day, responses.__getitem__)
            (root / f"content/daily/{day}.json").write_text(json.dumps({"date": day}))
            (root / "reports/daily").mkdir()
            html = root / "reports" / entry["url"]
            html.write_text(page)
            doc = root / "content/daily" / (html.stem + ".json")
            doc.write_text(json.dumps({"date": day, "indices": []}))
            self.assertFalse(check(root, day, responses.__getitem__))
            row = {"id": "kospi", "region": "kr", "asOf": day, "verified": True,
                   "source": "https://example.invalid/fixture"}
            doc.write_text(json.dumps({"date": day, "indices": [row]}))
            self.assertTrue(check(root, day, responses.__getitem__))
            with self.assertRaisesRegex(ValueError, "edition mismatch"):
                check(root, day, (responses | {"latest.html": title + "old content"}).__getitem__)
            doc.write_text(json.dumps({"date": day, "indices": [{**row, "asOf": "2026-11-18"}]}))
            self.assertFalse(check(root, day, responses.__getitem__))
            for path, bad in (("latest.html", title.replace(day, "2026-11-18")),
                              ("index.json", "[]"), (entry["url"], "not a report")):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    check(root, day, (responses | {path: bad}).__getitem__)
