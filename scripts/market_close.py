"""Session-aware closing-price collection and cross-source validation."""
import json
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

try:
    from .market_sources import ADAPTERS, fetch_pair
    from .collect_close import cross_check
except ImportError:
    from market_sources import ADAPTERS, fetch_pair
    from collect_close import cross_check

INSTRUMENTS = {
    'kospi': {'name':'KOSPI','region':'kr','calendar':'XKRX'},
    'kosdaq': {'name':'KOSDAQ','region':'kr','calendar':'XKRX'},
    'sp500': {'name':'S&P 500','region':'us','calendar':'XNYS'},
    'nasdaq': {'name':'NASDAQ','region':'us','calendar':'XNAS'},
}
PUBLIC_PAIRS = {
    "kr": ("yahoo", "naver"),
    "us": ("yahoo", "fred"),
}
MESSAGES = {
    'source_unavailable':'연결된 데이터 출처가 없습니다',
    'calendar_unavailable':'거래일 달력 확인이 필요합니다',
    'verification_unavailable':'비교 출처의 검증 자료가 없습니다',
    'missing':'최근 마감 자료가 아직 반영되지 않았습니다',
    'provider_error':'데이터를 확인하지 못했습니다',
    'disagreement':'출처 간 수치가 달라 표시를 보류합니다',
    'invalid':'수치 또는 기준일 검증을 통과하지 못했습니다',
    'verified':'확정 종가 · 교차 검증 완료',
    'latest_pending':'최신 거래일 검증 대기',
    'single_source':'확정 종가 · 단일 출처 검증 · 교차 검증 대기',
}
PUBLIC_US_PENDING = '교차 검증 전'

def session_close(calendar_name, now, reviewed_through):
    import exchange_calendars as xc
    import pandas as pd
    if now.tzinfo is None:
        raise ValueError('Timezone-aware collection time required')
    if now.date() > date.fromisoformat(reviewed_through):
        raise ValueError('Calendar review expired')
    start = (now - timedelta(days=45)).date().isoformat()
    calendar = xc.get_calendar(calendar_name, start=start, end=reviewed_through)
    ready = calendar.schedule[calendar.schedule['close'] <= pd.Timestamp(now - timedelta(minutes=30))]
    if len(ready) < 2:
        raise ValueError('Insufficient completed sessions')
    return ready.index[-1].date(), ready.index[-2].date(), ready["close"].iloc[-1].to_pydatetime()


def session_pair(calendar_name, now, reviewed_through):
    target, previous, _ = session_close(calendar_name, now, reviewed_through)
    return target, previous

def public_allowed(policy, instrument, today):
    """An enabled normal data-source entry can participate in two-source checks."""
    return (
        policy.get('enabled') is True
        and policy.get('collectionAllowed') is True
        and instrument in policy.get('instruments', [])
        and bool(policy.get('sourceUrls', {}).get(instrument, '').startswith('https://'))
        and not policy.get('private')
    )

def checked_pair(bars, target, previous):
    from math import isfinite
    values = {}
    for bar in bars:
        day = date.fromisoformat(bar.day)
        if day > target:
            # A mixed intraday/future record is never treated as a completed close.
            continue
        if day in values:
            raise ValueError('Duplicate observation date')
        if not isfinite(bar.close) or bar.close <= 0:
            raise ValueError('Invalid price')
        values[day] = bar
    if target not in values or previous not in values:
        raise LookupError('Latest session or prior session unavailable')
    current, prior = values[target], values[previous]
    pct = (current.close / prior.close - 1) * 100
    if not isfinite(pct) or abs(pct) > 25:
        raise ValueError('Implausible return')
    if current.reported_pct is not None and (not isfinite(current.reported_pct) or abs(current.reported_pct - pct) > 0.02):
        raise ValueError('Reported rate differs from close-to-close calculation')
    return current.close, prior.close, pct

def private_allowed(policy, instrument, today):
    """Private preview is a separate, explicit grant, never public approval."""
    grant = policy.get('private', {})
    try:
        return (policy.get('enabled') is True and policy.get('collectionAllowed') is True
                and instrument in policy.get('instruments', [])
                and all(grant.get(k) is True for k in ('display', 'derivedReturns', 'temporaryStorage'))
                and grant.get('evidence', '').startswith('https://')
                and date.fromisoformat(grant['reviewedAt']) <= today <= date.fromisoformat(grant['validThrough']))
    except (KeyError, ValueError, TypeError):
        return False

def collect(config, now=None, adapters=None, calendar=session_pair):
    return _collect(config, now, adapters, calendar, audience='public')

def collect_private(config, now=None, adapters=None, calendar=session_pair, *, allow_single_source=False):
    return _collect(config, now, adapters, calendar, audience='private', allow_single_source=allow_single_source)

def collect_region(config, region, existing=(), now=None, adapters=None, calendar=session_close,
                   verified_clock=None):
    """Scheduled regional refresh using one primary and one independent checker."""
    primary, checker = PUBLIC_PAIRS[region]
    verified_clock = verified_clock or (lambda: datetime.now(timezone.utc))
    config = {**config, "providers": {
        name: config["providers"].get(name, {}) for name in (primary, checker)
    }}
    return _collect(config, now, adapters, calendar, audience="public",
                    region=region, existing=existing, verified_clock=verified_clock)


def _collect(config, now, adapters, calendar, *, audience, allow_single_source=False,
             region=None, existing=(), verified_clock=None):
    now = now or datetime.now(timezone.utc)
    adapters = adapters if adapters is not None else ADAPTERS
    indices, statuses = [], []
    provisional = {row["id"]: row for row in existing if row.get("verificationStatus") == "pending"}
    existing = {row["id"]: row for row in existing if row.get("verified") is True}
    for instrument, meta in INSTRUMENTS.items():
        if region and meta["region"] != region:
            continue
        state = {'id':instrument,'name':meta['name'],'region':meta['region']}
        if region:
            state.update(collection="not_attempted", crossCheck="not_attempted")
        try:
            target, previous, *close = calendar(meta['calendar'], now, config['calendarReviewedThrough'])
            if region:
                state["expectedCloseAt"] = close[0].isoformat()
            state['expectedAsOf'] = target.isoformat()
        except Exception:
            state.update(status='calendar_unavailable', message=MESSAGES['calendar_unavailable']); statuses.append(state); continue
        allowed = public_allowed if audience == 'public' else private_allowed
        candidates = [(name, p) for name, p in config['providers'].items() if allowed(p, instrument, now.date()) and name in adapters]
        if region and len(candidates) != len(PUBLIC_PAIRS[region]):
            candidates = []
        if not candidates:
            state.update(status='source_unavailable', message=MESSAGES['source_unavailable'])
            statuses.append(state)
            continue
        retained = None
        if region:
            # The scheduled primary is always Yahoo. A checker may verify a
            # close, but never becomes the fallback origin of the public row.
            primary, checker = PUBLIC_PAIRS[region]
            candidates = [(primary, config["providers"][primary])]
            retained = reusable_row(existing.get(instrument), instrument, target,
                                    config["providers"][primary], config["providers"][checker])
            if retained and retained["asOf"] == target.isoformat():
                if retained["closeAt"] == state["expectedCloseAt"]:
                    indices.append(retained)
                    state.update(status="verified", message=MESSAGES["verified"],
                                 collection="complete", crossCheck="passed")
                    statuses.append(state)
                    continue
                # A changed exchange close time invalidates the cached session metadata.
                retained = None
        good, errors = {}, []
        collected_at = None
        for name, policy in config['providers'].items():
            if name not in adapters or policy.get('enabled') is not True or policy.get('collectionAllowed') is not True or instrument not in policy.get('instruments', []) or (audience == 'private' and not private_allowed(policy, instrument, now.date())):
                continue
            try:
                good[name] = checked_pair(fetch_pair(adapters[name], instrument, target, previous), target, previous)
                if region == 'us' and name == 'yahoo':
                    collected_at = verified_clock().isoformat()
            except LookupError:
                errors.append('missing')
            except ValueError:
                errors.append('invalid')
            except Exception:
                errors.append('provider_error')
        failure = errors[0] if errors else 'missing'
        pending = None
        for primary, policy in candidates:
            if primary not in good:
                continue
            a, prev_a, pct_a = good[primary]
            row = {'id':instrument, 'name':meta['name'], 'region':meta['region'], 'asOf':target.isoformat(), 'previousAsOf':previous.isoformat(), 'close':round(a,2), 'changePct':round(pct_a,2), 'source':policy['sourceUrls'][instrument], 'sourceName':policy.get('label', primary)}
            if region == 'us':
                row.update(closeAt=state['expectedCloseAt'], collectedAt=collected_at)
                cached = provisional.get(instrument, {})
                if cached.get('collectedAt') and all(cached.get(key) == row[key] for key in (
                    'asOf', 'previousAsOf', 'closeAt', 'close', 'changePct', 'source'
                )):
                    row['collectedAt'] = cached['collectedAt']
            checkers = [(name, config['providers'][name]) for name in good if name != primary and config['providers'][name].get('family') != policy.get('family')]
            if not checkers:
                if not errors:
                    failure = 'verification_unavailable'
                if region == 'us' and failure in ('missing', 'provider_error', 'invalid'):
                    pending = dict(row, verified=False, validated=True, verificationStatus='pending')
                continue
            try:
                for other, other_policy in checkers:
                    b, prev_b, pct_b = good[other]
                    # Reuse legacy Yahoo/Naver tolerance for current and prior closes.
                    cross_check(instrument, {'close':a}, b)
                    cross_check(instrument, {'close':prev_a}, prev_b)
                    if abs(pct_a-pct_b) > 0.02:
                        raise ValueError('Return disagreement')
            except ValueError:
                failure = 'disagreement'
                break  # Do not shop for an agreeing pair after a valid source disagrees.
            other, other_policy = checkers[0]
            row.update(verified=True, verificationSource=other_policy['sourceUrls'][instrument],
                       verificationSourceName=other_policy.get('label', other))
            if region:
                row.update(closeAt=state["expectedCloseAt"], verifiedAt=verified_clock().isoformat())
            if audience == 'private':
                row['publication'] = {'status':'private_only', 'evidence':policy['private']['evidence']}
                row['copyrightNotice'] = policy['private'].get('copyrightNotice', '')
                row['verificationCopyrightNotice'] = checkers[0][1]['private'].get('copyrightNotice', '')
            indices.append(row); state['status']='verified'; break
        if (audience == 'private' and allow_single_source and state.get('status') != 'verified'
                and failure in ('missing', 'provider_error', 'verification_unavailable') and 'invalid' not in errors):
            # A delayed comparison source need not hide a validated close in a
            # private preview. Never label it cross-verified or allow it public.
            for primary, policy in candidates:
                if primary not in good:
                    continue
                a, prev_a, pct_a = good[primary]
                row = {'id':instrument, 'name':meta['name'], 'region':meta['region'],
                       'asOf':target.isoformat(), 'previousAsOf':previous.isoformat(),
                       'close':round(a,2), 'changePct':round(pct_a,2), 'verified':False,
                       'validated':True, 'verificationStatus':'pending', 'verificationReason':failure,
                       'source':policy['sourceUrls'][instrument], 'sourceName':policy.get('label',primary),
                       'publication':{'status':'private_only','evidence':policy['private']['evidence']},
                       'copyrightNotice':policy['private'].get('copyrightNotice','')}
                indices.append(row);state['status']='single_source';break
        if state.get('status') not in ('verified', 'single_source'):
            state['status'] = failure
        state['message'] = MESSAGES[state['status']]
        if region == 'us':
            if pending is None and 'yahoo' not in good and failure in ('missing', 'provider_error') and 'invalid' not in errors:
                cached = provisional.get(instrument, {})
                if (cached.get('asOf') == target.isoformat() and cached.get('previousAsOf') == previous.isoformat()
                        and cached.get('closeAt') == state['expectedCloseAt']
                        and cached.get('source') == config['providers']['yahoo']['sourceUrls'][instrument]):
                    pending = cached
            if pending is not None:
                indices.append(pending)
                state.update(status='single_source', message=PUBLIC_US_PENDING,
                             verificationReason=failure)
        if region:
            state.update(
                collection="complete" if len(good) == 2 else ("partial" if good else "unavailable"),
                crossCheck="passed" if state["status"] == "verified" else
                ("failed" if state["status"] == "disagreement" else "pending"),
            )
            if retained and state["status"] not in ("verified", "single_source"):
                indices.append(retained)
                state["message"] = MESSAGES["latest_pending"] + " · " + state["message"]
        statuses.append(state)
    # Never disclose provider errors or request URLs containing credentials.
    return {'indices':indices, 'marketStatus':statuses, 'checkedAt':now.isoformat()}

def reusable_row(row, instrument, target, primary, checker):
    if not row or row.get("verified") is not True:
        return None
    if not row.get("closeAt") or not row.get("verifiedAt"):
        return None
    if row.get("asOf", "") > target.isoformat():
        return None
    if (row.get("source") != primary["sourceUrls"][instrument]
            or row.get("verificationSource") != checker["sourceUrls"][instrument]):
        return None
    return row


def collect_default(root, now=None):
    config = json.loads((Path(root) / 'config/market-sources.json').read_text())
    return collect(config, now=now)
