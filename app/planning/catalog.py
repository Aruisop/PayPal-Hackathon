"""Public availability snapshots; booking always rechecks the actual inventory."""
import json
from datetime import datetime, timezone

from .interpreter import DeterministicCatalogMatcher


def availability(offers, now=None):
    now = now or datetime.now(timezone.utc)
    result = []
    matcher = DeterministicCatalogMatcher()
    for offer in offers:
        start = datetime.fromisoformat(offer['scheduleTime'].replace('Z', '+00:00'))
        upcoming = start.tzinfo is not None and start > now
        candidate = dict(offer, meta=json.loads(offer['meta']) if isinstance(offer['meta'], str) else offer['meta'],
                         resources=[dict(resource, row_label=resource.get('row_label', resource.get('row')),
                                         col_number=resource.get('col_number', resource.get('col')))
                                    for resource in offer['resources']])
        sizes = [size for size in (2, 3, 4) if upcoming and
                 matcher.match([{} for _ in range(size)], [candidate], size)['matches']]
        result.append(dict(offer, availability=dict(status='past' if not upcoming else 'available' if sizes else 'unavailable',
                                                    groupSizes=sizes)))
    return dict(offers=result, summary=dict(upcomingCount=sum(o['availability']['status'] != 'past' for o in result),
                pastCount=sum(o['availability']['status'] == 'past' for o in result), checkedAt=now.isoformat(),
                inventoryReserved=False))
