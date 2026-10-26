#!/usr/bin/env python3
"""Read-only live diagnostics: no prices, raw responses or keys in output/files.
Use a local, non-committed config with collection permission, independently of
public redistribution permission. Never invokes the report builder/publisher.
"""
import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from market_close import INSTRUMENTS, checked_pair, session_pair
from market_sources import ADAPTERS, fetch_pair
from collect_close import cross_check


def diagnose(config, now=None, adapters=None):
    now = now or datetime.now(timezone.utc)
    adapters = ADAPTERS if adapters is None else adapters
    output = {'checkedAt':now.isoformat(), 'publicDataWritten':False, 'instruments':[]}
    for instrument, meta in INSTRUMENTS.items():
        result = {'id':instrument, 'providers':[], 'crossCheck':'unavailable'}
        output['instruments'].append(result)
        try:
            target, previous = session_pair(meta['calendar'], now, config['calendarReviewedThrough'])
            result.update(expectedAsOf=target.isoformat(), previousAsOf=previous.isoformat())
        except Exception:
            result['status'] = 'calendar_unavailable'
            continue
        good = []
        for name, policy in config['providers'].items():
            if name not in adapters or instrument not in policy.get('instruments', []):
                continue
            provider = {'id':name, 'status':'collection_not_authorized'}
            result['providers'].append(provider)
            if policy.get('enabled') is not True or policy.get('collectionAllowed') is not True:
                continue
            try:
                bars = fetch_pair(adapters[name], instrument, target, previous)
                provider['latestObservedAsOf'] = max((date.fromisoformat(bar.day).isoformat() for bar in bars if date.fromisoformat(bar.day) <= target), default=None)
                current, prior, pct = checked_pair(bars, target, previous)
                provider['status'] = 'exact_sessions_valid'
                good.append((name, policy.get('family', name), current, prior, pct))
            except LookupError:
                provider['status'] = 'session_missing'
            except (ValueError, KeyError, TypeError):
                provider['status'] = 'invalid_response'
            except Exception:
                # Never serialize exception text: it may contain credentials/prices.
                provider['status'] = 'request_failed_or_credentials_missing'
        pairs = 0
        for i, a in enumerate(good):
            for b in good[i+1:]:
                if a[1] == b[1]:
                    continue
                pairs += 1
                try:
                    cross_check(instrument, {'close':a[2]}, b[2])
                    cross_check(instrument, {'close':a[3]}, b[3])
                    if abs(a[4]-b[4]) > 0.02:
                        raise ValueError('Return disagreement')
                except ValueError:
                    result['crossCheck'] = 'disagreement'
                    break
            if result['crossCheck'] == 'disagreement':
                break
        if pairs and result['crossCheck'] != 'disagreement':
            result['crossCheck'] = 'passed'
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path, help='Local authorized-collection config; never commit private settings')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    result = diagnose(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Suitable for a manual validation gate, not a scheduled publication job.
    return 0 if all(i['crossCheck'] == 'passed' for i in result['instruments']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
