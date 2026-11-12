#!/usr/bin/env python3
"""Update one regional dashboard snapshot, optionally creating the daily study."""
import argparse
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from .build_public_reports import build, make_doc, validate
    from .market_close import INSTRUMENTS, MESSAGES, collect_region, session_close
except ImportError:
    from build_public_reports import build, make_doc, validate
    from market_close import INSTRUMENTS, MESSAGES, collect_region, session_close

ROOT = Path(__file__).resolve().parents[1]
DISPLAY_STATES = {"verified", "single_source"}
REVISION_WINDOW = 7


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
    targets = {state["id"]: state.get("expectedAsOf") for state in states if state["status"] in DISPLAY_STATES}
    return {
        "indices": [row for row in snapshot["indices"] if targets.get(row["id"]) == row["asOf"]],
        "marketStatus": states,
    }


def dated_study(root, session_day):
    report = root / "reports/daily" / f"{session_day}.html"
    manuscript = root / "content/daily" / f"{session_day}.json"
    if not report.is_file() or not manuscript.is_file():
        return None
    variants = sorted((root / "content/daily").glob(f"{session_day}-r*.json"))
    return json.loads((variants[-1] if variants else manuscript).read_text())


def revise_dated_study(root, session_day, region, result):
    """Append changed closes or a review notice, preserving all previous editions."""
    current = dated_study(root, session_day)
    if current is None:
        return False
    target = session_day.isoformat()
    affected = {
        state["id"]: state for state in result["marketStatus"]
        if state["region"] == region and state.get("expectedAsOf") == target
        and (state["status"] in DISPLAY_STATES
             or (region == "us" and state["status"] in {"disagreement", "invalid"}))
    }
    candidates = {
        row["id"]: row for row in result["indices"]
        if row["region"] == region and row["asOf"] == target and row["id"] in affected
        and affected[row["id"]]["status"] in DISPLAY_STATES
    }
    merged = {row["id"]: row for row in current.get("indices", [])}
    status_by_id = {state["id"]: state for state in current.get("marketStatus", [])}
    meaningful = ("asOf", "previousAsOf", "close", "changePct", "closeAt",
                  "source", "verificationSource", "verified", "verificationStatus")
    changed = False
    for key, state in affected.items():
        before, after = merged.get(key, {}), candidates.get(key)
        if before.get("verified") is True and before["asOf"] == target and (
            after is None or after.get("verified") is not True
        ):
            continue
        prior_status = status_by_id.get(key, {})
        if state["status"] in {"disagreement", "invalid"}:
            if before.get("verificationStatus") == "pending" and before["asOf"] == target:
                del merged[key]
            elif prior_status.get("status") == state["status"] and prior_status.get("expectedAsOf") == target:
                continue
        elif after is None or all(before.get(field) == after.get(field) for field in meaningful):
            continue
        else:
            merged[key] = after
        status_by_id[key] = state
        changed = True
    if not changed:
        return False

    order = list(INSTRUMENTS)
    rows = sorted(merged.values(), key=lambda row: order.index(row["id"]))
    states = sorted(status_by_id.values(), key=lambda state: order.index(state["id"]))
    build(root, session_day, market={"indices": rows, "marketStatus": states}, write_dashboard=False)
    return True


def preserve_us_reviews(result, previous, verified):
    """A transient source failure cannot republish an already disputed quote."""
    reviews = {
        (state["id"], state.get("expectedAsOf")): state
        for state in previous if state["status"] == "disagreement"
    }
    for index, state in enumerate(result["marketStatus"]):
        key = state["id"]
        review = reviews.get((key, state.get("expectedAsOf")))
        if review is None or state["status"] in ("verified", "disagreement"):
            continue
        result["marketStatus"][index] = review
        result["indices"] = [row for row in result["indices"] if row["id"] != key]
        if key in verified:
            result["indices"].append(verified[key])


def retry_dated_us_study(root, day, config, current, collect):
    """Retry one older unfinished report per slot, separately from the dashboard."""
    latest = {state.get("expectedAsOf") for state in current["marketStatus"]}
    for days_ago in range(REVISION_WINDOW, 0, -1):
        session = day - timedelta(days=days_ago)
        target = session.isoformat()
        if target in latest:
            continue
        study = dated_study(root, session)
        if study is None:
            continue
        unfinished = {
            state["id"] for state in study.get("marketStatus", [])
            if state["region"] == "us" and state.get("expectedAsOf") == target
            and state["status"] in ("single_source", "disagreement", "missing", "provider_error", "invalid", "verification_unavailable")
        }
        if not unfinished:
            continue
        scoped = {**config, "providers": {
            name: {**policy, "instruments": [key for key in policy.get("instruments", []) if key in unfinished]}
            for name, policy in config["providers"].items()
        }}
        # The existing calendar still selects and validates both sessions.
        cutoff = datetime.combine(session, time(23, 59), timezone.utc)
        result = collect(scoped, "us", existing=study.get("indices", []), now=cutoff)
        preserve_us_reviews(result, study.get("marketStatus", []), {})
        return int(revise_dated_study(root, session, "us", result))
    return 0


def refresh(root, region, now=None, collect=collect_region):
    now = now or datetime.now(timezone.utc)
    local_now = now.astimezone(ZoneInfo("Asia/Seoul"))
    day = local_now.date()
    path = root / "data/public-market.json"
    snapshot = json.loads(path.read_text()) if path.is_file() else {}
    config = json.loads((root / "config/market-sources.json").read_text())
    existing = snapshot.get("indices", [])
    verified_us = {row["id"]: row for row in snapshot.get("lastVerifiedUs", []) + existing
                   if row["region"] == "us" and row.get("verified") is True}
    if region == "us":
        result = collect(config, region, existing=[*verified_us.values(), *existing], now=now)
        preserve_us_reviews(result, snapshot.get("marketStatus", []), verified_us)
    else:
        result = collect(config, region, existing=existing, now=now)
    updated = dict(snapshot)
    for field in ("indices", "marketStatus"):
        untouched = [row for row in snapshot.get(field, []) if row["region"] != region]
        order = list(INSTRUMENTS)
        updated[field] = sorted(untouched + result[field], key=lambda row: order.index(row["id"]))
    if region == "us":
        fallback = [verified_us[row["id"]] for row in updated["indices"]
                    if row.get("verificationStatus") == "pending" and row["id"] in verified_us]
        if fallback:
            updated["lastVerifiedUs"] = fallback
        else:
            updated.pop("lastVerifiedUs", None)

    updated.setdefault("distribution", [])
    # Validate public observations, including retained fallbacks, before writing.
    doc = make_doc(day)
    doc.update(indices=updated["indices"] + updated.get("lastVerifiedUs", []),
               distribution=updated["distribution"])
    validate(doc)

    # The Korean evening slots are scheduled on the same UTC date as their
    # Korean session. A delayed run can cross Korean midnight before UTC
    # midnight. The exchange calendar still has to verify that exact session.
    study_time = now
    if region == "kr" and now.astimezone(timezone.utc).date() < day:
        day = now.astimezone(timezone.utc).date()
        study_time = datetime.combine(day, time.max, local_now.tzinfo)
    report = root / "reports/daily" / f"{day}.html"
    built = False
    if region == "kr" and not report.is_file():
        market = study_snapshot(updated, config, study_time)
        if any(row["region"] == "kr" and row["asOf"] == day.isoformat() and row.get("verified") is True
               for row in market["indices"]):
            build(root, day, market=market, write_dashboard=False)
            updated["reportDate"] = max(day.isoformat(), snapshot.get("reportDate", ""))
            built = True
        else:
            print(f'::warning::No verified Korean close for {day}; daily study not created')

    revisions = 0
    if region == "kr" and not built:
        revisions += int(revise_dated_study(root, day, region, result))
    if region == "us":
        # U.S. trading date is one day earlier in KST, or older after holidays.
        sessions = {date.fromisoformat(state["expectedAsOf"]) for state in result["marketStatus"]
                    if state["status"] in DISPLAY_STATES | {"disagreement", "invalid"} and state.get("expectedAsOf")}
        for session_day in sorted(sessions):
            if 0 <= (day - session_day).days <= REVISION_WINDOW:
                revisions += int(revise_dated_study(root, session_day, region, result))
        revisions += retry_dated_us_study(root, day, config, result, collect)

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
