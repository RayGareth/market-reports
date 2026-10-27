"""Session-aware, permission-gated public close pipeline (no raw persistence)."""
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
MESSAGES = {
    'rights_pending':'공개 게시 근거 확인 대기',
    'calendar_unavailable':'거래일 달력 확인이 필요합니다',
    'verification_unavailable':'비교 출처의 검증 자료가 없습니다',
    'missing':'최근 마감 자료가 아직 반영되지 않았습니다',
    'provider_error':'데이터를 확인하지 못했습니다',
    'disagreement':'출처 간 수치가 달라 표시를 보류합니다',
    'invalid':'수치 또는 기준일 검증을 통과하지 못했습니다',
    'verified':'확정 종가 · 교차 검증 완료',
}

def session_pair(calendar_name, now, reviewed_through):
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
    return ready.index[-1].date(), ready.index[-2].date()

def public_allowed(policy, instrument, today):
    grant = policy.get('public', {})
    try:
        return policy.get('enabled') is True and policy.get('collectionAllowed') is True and instrument in policy.get('instruments', []) and all(grant.get(k) is True for k in ('display','redistribution','derivedReturns')) and instrument in grant.get('instruments', []) and grant.get('evidence', '').startswith('https://') and date.fromisoformat(grant['reviewedAt']) <= today <= date.fromisoformat(grant['validThrough'])
    except (KeyError, ValueError, TypeError):
        return False

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

def collect_private(config, now=None, adapters=None, calendar=session_pair):
    return _collect(config, now, adapters, calendar, audience='private')

def _collect(config, now, adapters, calendar, *, audience):
    now = now or datetime.now(timezone.utc)
    adapters = adapters if adapters is not None else ADAPTERS
    indices, statuses = [], []
    for instrument, meta in INSTRUMENTS.items():
        state = {'id':instrument,'name':meta['name'],'region':meta['region']}
        try:
            target, previous = calendar(meta['calendar'], now, config['calendarReviewedThrough'])
            state['expectedAsOf'] = target.isoformat()
        except Exception:
            state.update(status='calendar_unavailable', message=MESSAGES['calendar_unavailable']); statuses.append(state); continue
        allowed = public_allowed if audience == 'public' else private_allowed
        candidates = [(name, p) for name, p in config['providers'].items() if allowed(p, instrument, now.date()) and name in adapters]
        if not candidates:
            state.update(status='rights_pending', message=MESSAGES['rights_pending']); statuses.append(state); continue
        good, errors = {}, []
        for name, policy in config['providers'].items():
            if name not in adapters or policy.get('enabled') is not True or policy.get('collectionAllowed') is not True or instrument not in policy.get('instruments', []) or (audience == 'private' and not private_allowed(policy, instrument, now.date())):
                continue
            try:
                good[name] = checked_pair(fetch_pair(adapters[name], instrument, target, previous), target, previous)
            except LookupError:
                errors.append('missing')
            except ValueError:
                errors.append('invalid')
            except Exception:
                errors.append('provider_error')
        failure = errors[0] if errors else 'missing'
        for primary, policy in candidates:
            if primary not in good:
                continue
            a, prev_a, pct_a = good[primary]
            checkers = [(name, config['providers'][name]) for name in good if name != primary and config['providers'][name].get('family') != policy.get('family')]
            if not checkers:
                if not errors:
                    failure = 'verification_unavailable'
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
            row = {'id':instrument, 'name':meta['name'], 'region':meta['region'], 'asOf':target.isoformat(), 'previousAsOf':previous.isoformat(), 'close':round(a,2), 'changePct':round(pct_a,2), 'verified':True, 'source':policy['sourceUrls'][instrument], 'sourceName':policy.get('label', primary), 'verificationSource':checkers[0][1]['sourceUrls'][instrument], 'verificationSourceName':checkers[0][1].get('label', checkers[0][0]), 'publication':{'status':'approved_public' if audience == 'public' else 'private_only','evidence':policy['public' if audience == 'public' else 'private']['evidence']}}
            if audience == 'private':
                row['copyrightNotice'] = policy['private'].get('copyrightNotice', '')
                row['verificationCopyrightNotice'] = checkers[0][1]['private'].get('copyrightNotice', '')
            indices.append(row); state['status']='verified'; break
        if state.get('status') != 'verified':
            state['status'] = failure
        state['message'] = MESSAGES[state['status']]
        statuses.append(state)
    # Neither exception text, request URLs with credentials nor unapproved numbers leave this function.
    return {'indices':indices, 'marketStatus':statuses, 'checkedAt':now.isoformat()}

def collect_default(root, now=None):
    config = json.loads((Path(root) / 'config/market-sources.json').read_text())
    return collect(config, now=now)
