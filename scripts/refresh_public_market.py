#!/usr/bin/env python3
"""Update one regional dashboard snapshot, optionally creating the daily study."""
import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from .build_public_reports import build, make_doc, validate
    from .section02_news import EVENING_SLOTS, KST, LAST_SLOT
    from .market_close import INSTRUMENTS, MESSAGES, collect_region, session_close
except ImportError:
    from build_public_reports import build, make_doc, validate
    from section02_news import EVENING_SLOTS, KST, LAST_SLOT
    from market_close import INSTRUMENTS, MESSAGES, collect_region, session_close

ROOT = Path(__file__).resolve().parents[1]
DISPLAY_STATES = {"verified", "single_source"}
REVISION_WINDOW = 7
RAY_CLOSE_REQUEST = "국내 종가가 확보되지 않아서, Ray가 직접 확인해서 알려줘."


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


def prepare_section02(root, day, cutoff):
    """Use published report history and keep source delays off the publication path."""
    pending = {"status": "pending", "issues": []}
    try:
        index = root / 'reports/index.json'
        entries = json.loads(index.read_text()) if index.exists() else []
        after = None
        seen = set()
        for report in sorted(entries, key=lambda item: item['date'], reverse=True):
            if report.get('status') != 'published':
                continue
            report_day = date.fromisoformat(report['date'])
            prior = dated_study(root, report_day)
            if prior is None:
                continue
            news = prior.get('section02', {})
            seen.update(item['source'] for item in news.get('issues', []))
            if after is None and report_day < day:
                # Existing reports have no news cutoff. Use their last scheduled slot.
                through = news.get('window', {}).get('through')
                after = (datetime.fromisoformat(through) if through
                         else datetime.combine(report_day, LAST_SLOT, KST))
        if after is None:
            after = datetime.combine(day - timedelta(days=1), LAST_SLOT, KST)
        window = {'after': after.isoformat(), 'through': cutoff.isoformat()}
        validate(dict(make_doc(day), section02={**pending, 'window': window}))
        pending['window'] = window
        result = subprocess.run([sys.executable, str(root / 'scripts/section02_news.py'),
                                 window['after'], window['through'], *sorted(seen)],
                                timeout=13, capture_output=True, check=True)
        news = json.loads(result.stdout)
        validate(dict(make_doc(day), section02=news))
        if news.get('window') != window or any(item['source'] in seen for item in news['issues']):
            raise ValueError('Official news does not match the publication window or history')
        return news
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
        print(f"::warning::Official news unavailable for {day}; continuing daily study")
        return pending


def revise_dated_study(root, session_day, region, result, recorded_at=None):
    """Append changed closes or a review notice, preserving all previous editions."""
    current = dated_study(root, session_day)
    if current is None:
        return False
    target = session_day.isoformat()
    affected = {
        state["id"]: state for state in result["marketStatus"]
        if state["region"] == region and state.get("expectedAsOf") == target
        and (state["status"] in DISPLAY_STATES
             or state["status"] in {"disagreement", "invalid"})
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
    market = {"indices": rows, "marketStatus": states}
    if current.get("firstPublishedAt"):
        market["closeSupplementedAt"] = (recorded_at or datetime.now(timezone.utc)).isoformat()
    build(root, session_day, market=market, write_dashboard=False)
    if region == "kr" and recorded_at is not None:
        had_close = any(row["region"] == "kr" and row["asOf"] == target
                        for row in current.get("indices", []))
        has_close = any(row["region"] == "kr" and row["asOf"] == target for row in rows)
        if not had_close and has_close and recorded_at > datetime.combine(session_day, time(19), KST):
            print(f"::warning::{session_day}: late domestic close manuscript; 19:00 KST target missed")
    return True


def preserve_source_disagreements(result, previous, verified):
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
        preserve_source_disagreements(result, study.get("marketStatus", []), {})
        return int(revise_dated_study(root, session, "us", result))
    return 0



def record_first_manuscript(day, now):
    if now > datetime.combine(day, time(19), KST):
        print(f"::warning::Publication {day}: late first manuscript; 19:00 KST target missed")


def recover_missing_kr_study(root, now, config, collect, snapshot, news=None, skip_day=None):
    """Recover one missing or unfinished Korean report in the morning slot."""
    local_now = now.astimezone(ZoneInfo("Asia/Seoul"))
    for days_ago in range(1, 8):
        session = local_now.date() - timedelta(days=days_ago)
        if session == skip_day:
            continue
        current = dated_study(root, session)
        if current and {row["id"] for row in current.get("indices", [])
                        if row["region"] == "kr" and row["asOf"] == session.isoformat()
                        and row.get("verified") is True} == {"kospi", "kosdaq"}:
            continue
        study_time = datetime.combine(session, time(18, 0), ZoneInfo("Asia/Seoul"))
        try:
            completed, _, _ = session_close("XKRX", study_time, config["calendarReviewedThrough"])
        except (KeyError, ValueError):
            continue
        if completed != session:
            continue  # Weekends and Korean exchange holidays have no study.
        result = collect(config, "kr", existing=current.get("indices", []) if current else (),
                         now=study_time)
        if current:
            preserve_source_disagreements(result, current.get("marketStatus", []), {})
            return session if revise_dated_study(root, session, "kr", result, now) else None
        korean = [row for row in result["indices"] if row["region"] == "kr"
                  and row["asOf"] == session.isoformat()]
        us_rows = [row for row in snapshot["indices"] if row["region"] == "us"]
        us_states = [state for state in snapshot["marketStatus"] if state["region"] == "us"]
        historical = study_snapshot(
            {"indices": us_rows + korean, "marketStatus": us_states + result["marketStatus"]},
            config, study_time)
        # Newer U.S. data is excluded by the historical date filter.
        if not any(row["region"] == "kr" for row in historical["indices"]):
            print(f"::warning::{session}: {RAY_CLOSE_REQUEST}")
            return None
        historical["firstPublishedAt"] = now.isoformat()
        build(root, session, market=historical, write_dashboard=False,
              section02=news(root, session, datetime.combine(session, LAST_SLOT, KST)) if news else None)
        record_first_manuscript(session, now)
        print(f"Recovered missing Korean study for {session}; dashboard preserved")
        return session
    return None


def refresh(root, region, now=None, collect=collect_region, recover=False, news=None, news_slot=LAST_SLOT):
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
        preserve_source_disagreements(result, snapshot.get("marketStatus", []), verified_us)
    else:
        result = collect(config, region, existing=existing, now=now)
        previous = snapshot.get("marketStatus", [])
        # The dashboard can advance to a newer session before an older study is recovered.
        for target in {state.get("expectedAsOf") for state in result["marketStatus"]} - {None}:
            current = dated_study(root, date.fromisoformat(target))
            if current:
                previous = previous + current.get("marketStatus", [])
        preserve_source_disagreements(result, previous, {})
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
    if region == "kr" and recover:
        # The extra morning check targets the most recent completed session.
        targets = {state.get("expectedAsOf") for state in result["marketStatus"]
                   if state["region"] == "kr" and state.get("expectedAsOf")}
        if len(targets) == 1:
            day = date.fromisoformat(targets.pop())
            study_time = datetime.combine(day, time(18, 0), ZoneInfo("Asia/Seoul"))
    report = root / "reports/daily" / f"{day}.html"
    built = False
    completed_session = False
    if region == "kr":
        try:
            completed, _, _ = session_close("XKRX", study_time, config["calendarReviewedThrough"])
            completed_session = completed == day
        except (KeyError, ValueError):
            print(f"::warning::Publication date unavailable for {day}; study not created")
    if region == "kr" and completed_session and not report.is_file():
        market = study_snapshot(updated, config, study_time)
        market["firstPublishedAt"] = now.isoformat()
        news_cutoff = min(local_now, datetime.combine(day, LAST_SLOT if recover else news_slot, KST))
        build(root, day, market=market, write_dashboard=False,
              section02=news(root, day, news_cutoff) if news else None)
        updated["reportDate"] = max(day.isoformat(), snapshot.get("reportDate", ""))
        record_first_manuscript(day, now)
        built = True

    revisions = 0
    current_revised = False
    if region == "kr" and not built:
        current_revised = revise_dated_study(root, day, region, result, now)
        revisions += int(current_revised)
    if region == "us":
        # U.S. trading date is one day earlier in KST, or older after holidays.
        sessions = {date.fromisoformat(state["expectedAsOf"]) for state in result["marketStatus"]
                    if state["status"] in DISPLAY_STATES | {"disagreement", "invalid"} and state.get("expectedAsOf")}
        for session_day in sorted(sessions):
            if 0 <= (day - session_day).days <= REVISION_WINDOW:
                revisions += int(revise_dated_study(root, session_day, region, result))
        revisions += retry_dated_us_study(root, day, config, result, collect)

    if region == "kr" and recover:
        repaired = recover_missing_kr_study(root, now, config, collect, updated, news, skip_day=day)
        if repaired is not None:
            revisions += 1
            updated["reportDate"] = max(updated.get("reportDate", ""), repaired.isoformat())

    # build() regenerates a dated archive alias; the dashboard remains the
    # independent latest-by-region snapshot, never the dated study's snapshot.
    if built or revisions or updated != snapshot:
        updated["checkedAt"] = result["checkedAt"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
    if region == "kr" and completed_session and (built or report.is_file()):
        current = dated_study(root, day)
        archive = json.loads((root / "reports/index.json").read_text())
        entry = next((entry for entry in archive if entry["date"] == day.isoformat()), None)
        revision = current.get("revision", 0) if current else 0
        stem = day.isoformat() + (f"-r{revision:03d}" if revision else "")
        if (current is None or entry is None or entry["url"] != f"daily/{stem}.html"
                or not (root / "reports" / entry["url"]).is_file()):
            raise RuntimeError(f"Publication incomplete for {day}; manuscript, HTML or archive missing")
        status = "created" if built else "revised" if current_revised else "already_published"
        domestic = [row for row in current.get("indices", [])
                    if row["region"] == "kr" and row["asOf"] == day.isoformat()]
        ready = {row["id"] for row in domestic if row.get("verified") is True} == {"kospi", "kosdaq"}
        if not domestic:
            print(f"::warning::{day}: {RAY_CLOSE_REQUEST}")
            if local_now >= datetime.combine(day, time(19), KST):
                print(f"::warning::{day}: 19:00 KST domestic close publication target missed")
        close_status = "verified" if ready else "pending" if domestic else "unavailable"
        print(f"Publication {day}: {status}; Korean closes: {close_status}")
    print(f"Refreshed public {region.upper()} market status; study created: {built}; revisions: {revisions}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True, choices=("kr", "us"))
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    refresh(ROOT, args.region, recover=args.recover, news=prepare_section02 if args.region == 'kr' else None,
            news_slot=EVENING_SLOTS.get(os.environ.get('MARKET_NEWS_SCHEDULE'), LAST_SLOT))
