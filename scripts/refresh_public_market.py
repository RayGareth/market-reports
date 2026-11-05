#!/usr/bin/env python3
"""Update one regional dashboard snapshot, optionally creating the daily study."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from .build_public_reports import build, make_doc, validate
    from .market_close import INSTRUMENTS, MESSAGES, collect_region, session_close
except ImportError:
    from build_public_reports import build, make_doc, validate
    from market_close import INSTRUMENTS, MESSAGES, collect_region, session_close

ROOT = Path(__file__).resolve().parents[1]


def study_snapshot(snapshot, config, now):
    """A dated note only includes rows for the session expected at publication."""
    states = []
    for original in snapshot["marketStatus"]:
        state = dict(original)
        if state["region"] == "us":
            # U.S. slots can be delayed independently. A cached verified state
            # must not authorize an earlier close for the new dated note.
            try:
                target, _, close = session_close(
                    INSTRUMENTS[state["id"]]["calendar"], now, config["calendarReviewedThrough"]
                )
            except (KeyError, ValueError):
                state.pop("expectedAsOf", None)
                state.pop("expectedCloseAt", None)
                state.update(status="calendar_unavailable", message=MESSAGES["calendar_unavailable"],
                             collection="not_attempted", crossCheck="not_attempted", publication="pending")
            else:
                expected = target.isoformat()
                if state.get("expectedAsOf") != expected and state["status"] != "rights_pending":
                    state.update(status="missing", message=MESSAGES["latest_pending"],
                                 collection="not_attempted", crossCheck="not_attempted", publication="pending")
                state.update(expectedAsOf=expected, expectedCloseAt=close.isoformat())
        states.append(state)
    targets = {state["id"]: state.get("expectedAsOf") for state in states if state["status"] == "verified"}
    return {
        "indices": [row for row in snapshot["indices"] if targets.get(row["id"]) == row["asOf"]],
        "marketStatus": states,
    }


def refresh(root, region, now=None, collect=collect_region):
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(ZoneInfo("Asia/Seoul")).date()
    path = root / "data/public-market.json"
    snapshot = json.loads(path.read_text()) if path.is_file() else {}
    config = json.loads((root / "config/market-sources.json").read_text())
    result = collect(config, region, existing=snapshot.get("indices", []), now=now)
    updated = dict(snapshot)
    for field in ("indices", "marketStatus"):
        untouched = [row for row in snapshot.get(field, []) if row["region"] != region]
        order = list(INSTRUMENTS)
        updated[field] = sorted(untouched + result[field], key=lambda row: order.index(row["id"]))

    updated.setdefault("distribution", [])
    # Use the existing allowlist/shape checks before writing public outputs.
    doc = make_doc(day)
    doc.update(indices=updated["indices"], distribution=updated["distribution"])
    validate(doc)

    # Leave a dated report as the record of its original publication. Retries
    # and U.S. checks can update the dashboard without creating revisions.
    manuscript = root / "content/daily" / f"{day}.json"
    report = root / "reports/daily" / f"{day}.html"
    built = region == "kr" and day.weekday() < 5 and not report.is_file()
    if built:
        market = None if manuscript.is_file() else study_snapshot(updated, config, now)
        build(root, day, market=market)
        updated["reportDate"] = max(day.isoformat(), snapshot.get("reportDate", ""))

    if built or updated != snapshot:
        updated["checkedAt"] = result["checkedAt"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
    print(f"Refreshed public {region.upper()} market status; study created: {built}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True, choices=("kr", "us"))
    refresh(ROOT, parser.parse_args().region)
