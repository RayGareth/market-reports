"""Offline proposal only. Not imported by production or Actions publication."""
import json
from datetime import datetime

MARKET = 'data/public-market.json'

def publication_required(before, after):
    """Compare complete output maps, ignoring only a valid top-level checkedAt.

    Missing files, malformed snapshots, new schema fields and every other byte
    change fail open to publication. Callers must still validate public grants.
    """
    if before.keys() != after.keys():
        return True
    for path in before:
        if before[path] == after[path]:
            continue
        if path != MARKET:
            return True
        try:
            old, new = json.loads(before[path]), json.loads(after[path])
            if not isinstance(old, dict) or not isinstance(new, dict):
                return True
            # Missing/non-string timestamps are not an approved no-op case.
            if not all(isinstance(x.get('checkedAt'), str) for x in (old, new)):
                return True
            for value in (old, new):
                if datetime.fromisoformat(value['checkedAt'].replace('Z', '+00:00')).tzinfo is None:
                    return True
            old.pop('checkedAt'); new.pop('checkedAt')
            if old != new:
                return True
        except (ValueError, TypeError, OverflowError):
            return True
    return False
