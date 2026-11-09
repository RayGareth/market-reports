#!/usr/bin/env python3
"""Update one regional dashboard snapshot, optionally creating the daily study."""
import argparse
import json
from datetime import date, datetime, timezone
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
                if state.get("expectedAsOf") != expected and state["status"] != "source_unavailable":
                    state.update(status="missing", message=MESSAGES["latest_pending"],
                                 collection="not_attempted", crossCheck="not_attempted", publication="pending")
                state.update(expectedAsOf=expected, expectedCloseAt=close.isoformat())
        states.append(state)
    targets = {state["id"]: state.get("expectedAsOf") for state in states if state["status"] == "verified"}
    return {
        "indices": [row for row in snapshot["indices"] if targets.get(row["id"]) == row["asOf"]],
        "marketStatus": states,
    }


def revise_dated_study(root, session_day, region, result):
    """Append a dated revision for newly verified closes, preserving the original."""
    report = root / "reports/daily" / f"{session_day}.html"
    manuscript = root / "content/daily" / f"{session_day}.json"
    if not report.is_file() or not manuscript.is_file():
        return False

    variants = sorted((root / "content/daily").glob(f"{session_day}-r*.json"))
    current = json.loads((variants[-1] if variants else manuscript).read_text())
    verified_ids = {
        state["id"] for state in result["marketStatus"]
        if state["status"] == "verified"
    }
    candidates = {
        row["id"]: row for row in result["indices"]
        if row["region"] == region and row["asOf"] == session_day.isoformat()
        and row.get("verified") is True and row["id"] in verified_ids
    }
    if not candidates:
        return False

    # A later confirmation of the same close must not create another revision.
    merged = {row["id"]: row for row in current.get("indices", [])}
    meaningful = ("id", "asOf", "previousAsOf", "close", "changePct",
                  "closeAt", "source", "verificationSource")
    if not any(
        key not in merged
        or any(merged[key].get(field) != row.get(field) for field in meaningful)
        for key, row in candidates.items()
    ):
        return False

    merged.update(candidates)
    order = list(INSTRUMENTS)
    rows = sorted(merged.values(), key=lambda row: order.index(row["id"]))
    status_by_id = {state["id"]: state for state in current.get("marketStatus", [])}
    status_by_id.update({
        state["id"]: state for state in result["marketStatus"]
        if state["id"] in candidates
    })
    states = sorted(status_by_id.values(), key=lambda state: order.index(state["id"]))
    build(root, session_day, market={"indices": rows, "marketStatus": states})
    return True


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
    # Validate the verified snapshot shape before writing the dashboard.
    doc = make_doc(day)
    doc.update(indices=updated["indices"], distribution=updated["distribution"])
    validate(doc)

    # The collector uses the exchange calendar and waits for the close to
    # settle. An earlier session or a pending close cannot start today's note.
    report = root / "reports/daily" / f"{day}.html"
    built = False
    if region == "kr" and not report.is_file():
        market = study_snapshot(updated, config, now)
        if any(row["region"] == "kr" and row["asOf"] == day.isoformat()
               for row in market["indices"]):
            build(root, day, market=market)
            updated["reportDate"] = max(day.isoformat(), snapshot.get("reportDate", ""))
            built = True

    revisions = 0
    if region == "kr" and not built:
        revisions += int(revise_dated_study(root, day, region, result))
    if region == "us":
        # U.S. trading date is one day earlier in KST, or older after holidays.
        sessions = {
            date.fromisoformat(row["asOf"]) for row in result["indices"]
            if row["region"] == "us" and row.get("verified") is True
            and any(state["id"] == row["id"] and state["status"] == "verified"
                    for state in result["marketStatus"])
        }
        for session_day in sorted(sessions):
            if 0 <= (day - session_day).days <= 7:
                revisions += int(revise_dated_study(root, session_day, region, result))

    # build() regenerates a dated archive alias; the dashboard remains the
    # independent latest-by-region snapshot, never the dated study's snapshot.
    if built or revisions or updated != snapshot:
        updated["checkedAt"] = result["checkedAt"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
    print(f"Refreshed public {region.upper()} market status; study created: {built}; revisions: {revisions}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True, choices=("kr", "us"))
    refresh(ROOT, parser.parse_args().region)
