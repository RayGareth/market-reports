"""Read-only observation of the domestic report on main and public Pages."""
import json
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .market_close import session_close
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
    title = f"<title>{day} | Market Daily</title>"
    for path in (entry["url"], "latest.html"):
        if title not in fetch(path):
            raise ValueError(f"Pages: report date mismatch in {path}")


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
        check(ROOT, day.isoformat(), download)
    except (HTTPError, URLError, TimeoutError) as error:
        raise SystemExit(f"{day}: public HTTP check failed: {error}") from error
    observed = datetime.now(KST)
    timing = ("confirmed by 19:00" if observed <= datetime.combine(day, time(19), KST)
              else "checked after deadline; first public time unknown")
    print(f"{day}: publicly visible at {observed.isoformat()}; {timing}")


if __name__ == "__main__":
    main()
