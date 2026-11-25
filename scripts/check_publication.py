"""Read-only observation of the domestic report on main and public Pages."""
import json
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .market_close import session_close
from .build_public_reports import approved, pending_public_close
from .section02_news import KST

ROOT = Path(__file__).resolve().parents[1]
PAGES = "https://raygareth.github.io/market-reports/reports/"


def target_date(now):
    day = now.date()
    if now.time() < time(18, 50):
        day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def download(path):
    with urlopen(PAGES + path, timeout=6) as response:
        return response.read().decode("utf-8")


def check(root, day, fetch):
    manuscript = root / "content/daily" / f"{day}.json"
    if not manuscript.exists():
        raise ValueError("main: first manuscript missing")
    if json.loads(manuscript.read_text())["date"] != day:
        raise ValueError("main: manuscript date mismatch")
    local = json.loads((root / "reports/index.json").read_text())
    if not any(item["date"] == day for item in local):
        raise ValueError("main: archive entry missing")
    public = json.loads(fetch("index.json"))
    entry = next((item for item in public if item["date"] == day), None)
    if not entry or not re.fullmatch(rf"daily/{day}(?:-r[0-9]+)?\.html", entry["url"]):
        raise ValueError("Pages: dated archive entry missing or invalid")
    # Read the exact edition referenced by the public archive. A learning-only
    # first edition may be visible while a close-bearing revision is still deploying.
    html = root / "reports" / entry["url"]
    edition = root / "content/daily" / (html.stem + ".json")
    if not html.is_file() or not edition.is_file():
        raise ValueError("main: public edition missing")
    doc = json.loads(edition.read_text())
    if doc["date"] != day:
        raise ValueError("main: public edition date mismatch")
    expected = html.read_text()
    title = f"<title>{day} | Market Daily</title>"
    # Match build_public_reports' relative paths for the latest alias.
    alias = expected.replace('href="../../', 'href="../').replace('src="../../', 'src="../')
    alias = alias.replace('href="../">리포트 아카이브', 'href="./">리포트 아카이브').replace(
        'href="../">← 아카이브', 'href="./">← 아카이브')
    for path, expected_html in ((entry["url"], expected), ("latest.html", alias)):
        visible = fetch(path)
        if title not in visible:
            raise ValueError(f"Pages: report date mismatch in {path}")
        if visible != expected_html:
            raise ValueError(f"Pages: public edition mismatch in {path}")
    return any(row.get("id") in {"kospi", "kosdaq"} and row.get("region") == "kr"
               and row.get("asOf") == day and (approved(row) or pending_public_close(row))
               for row in doc.get("indices", []))


def main():
    now = datetime.now(KST)
    day = target_date(now)
    config = json.loads((ROOT / "config/market-sources.json").read_text())
    slot = datetime.combine(day, time(18, 50), KST)
    completed, _, _ = session_close("XKRX", slot, config["calendarReviewedThrough"])
    if completed != day:
        print(f"{day}: no completed Korean session at check time")
        return
    try:
        has_close = check(ROOT, day.isoformat(), download)
    except (HTTPError, URLError, TimeoutError) as error:
        raise SystemExit(f"{day}: public HTTP check failed: {error}") from error
    observed = datetime.now(KST)
    timing = ("confirmed by 19:00" if observed <= datetime.combine(day, time(19), KST)
              else "checked after deadline; first public time unknown")
    print(f"{day}: publicly visible at {observed.isoformat()}; {timing}")
    if not has_close:
        raise SystemExit(f"{day}: public study confirmed, but domestic closing prices are unavailable")
    print(f"{day}: actual public report contains a domestic close; {timing}")


if __name__ == "__main__":
    main()
