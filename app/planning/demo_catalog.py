"""Explicitly append fictional development sessions; never reschedule a booking."""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert, select

from app.shared.storage import catalog_offers, catalog_resources, versions


SESSIONS = (
    ('movie-cosmic-odyssey-fri', 4, 19, 30),
    ('movie-neon-shadows-sat', 5, 21, 0),
    ('movie-silent-echoes-sun', 6, 14, 0),
    ('excursion-kayak-canyon-sat', 5, 9, 0),
    ('excursion-mountain-trek-sun', 6, 15, 0),
)


def prepare_demo_catalog(store, today=None):
    today = today or datetime.now(timezone.utc).date()
    created = []
    with store.engine.begin() as connection:
        if connection.execute(select(versions.c.revision).where(versions.c.id == 1)).scalar() != 5:
            raise RuntimeError('Demo sessions require the existing revision 5 application schema.')
        for source_id, weekday, hour, minute in SESSIONS:
            day = today + timedelta(days=(weekday - today.weekday()) % 7 or 7)
            offer_id = f'demo-{source_id}-{day:%Y%m%d}'
            if connection.execute(select(catalog_offers.c.id).where(catalog_offers.c.id == offer_id)).first():
                continue
            source = connection.execute(select(catalog_offers).where(catalog_offers.c.id == source_id)).mappings().first()
            if not source:
                raise RuntimeError('The original fictional catalog templates are missing. No sessions were added.')
            record = dict(source)
            meta = json.loads(record['meta_json'])
            meta['demo_session'] = True
            if source_id == 'excursion-kayak-canyon-sat':
                meta['runtime_min'] = 180
            record.update(id=offer_id, schedule_time=datetime.combine(day, datetime.min.time(), timezone.utc).replace(
                hour=hour, minute=minute).isoformat(), meta_json=json.dumps(meta))
            connection.execute(insert(catalog_offers).values(**record))
            cinema = source['domain'] == 'movie'
            for number in range(1, 9 if cinema else 5):
                label = f'A{number}' if cinema else f'P{number}'
                connection.execute(insert(catalog_resources).values(id=f'res-{offer_id}-{label}', offer_id=offer_id,
                    resource_key=f'{offer_id}:{label}', label=f'Seat {label}' if cinema else f'Place #{number}',
                    row_label='A' if cinema else 'G', col_number=number, state='FREE'))
            created.append(offer_id)
    return dict(createdCount=len(created), existingRecordsChanged=False)
