import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...dal.db import get_db
from ...dal.models import User, WowItemIcon
from ..auth import get_current_user
from ..battlenet import REGION, battlenet_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["BiS"])


def _slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").title()


@router.get("/specs")
async def list_specs(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    rows = db.execute(text("""
        SELECT DISTINCT s.spec_slug, s.class_slug
        FROM archon_spec_snapshots s
        JOIN archon_scrape_runs r ON r.id = s.run_id
        WHERE r.success = true
        ORDER BY s.class_slug, s.spec_slug
    """)).fetchall()
    return [
        {
            "spec_slug": row.spec_slug,
            "class_slug": row.class_slug,
            "spec_name": _slug_to_name(row.spec_slug),
            "class_name": _slug_to_name(row.class_slug),
        }
        for row in rows
    ]


@router.get("/snapshot")
async def get_snapshot(
    spec: str = Query(...),
    cls: str = Query(..., alias="class"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    snapshot = db.execute(text("""
        SELECT s.id, s.spec_slug, s.class_slug, s.scraped_at
        FROM archon_spec_snapshots s
        JOIN archon_scrape_runs r ON r.id = s.run_id
        WHERE r.success = true
          AND s.spec_slug = :spec
          AND s.class_slug = :cls
        ORDER BY s.scraped_at DESC
        LIMIT 1
    """), {"spec": spec, "cls": cls}).fetchone()

    if not snapshot:
        raise HTTPException(status_code=404, detail="No data for this spec")

    sid = snapshot.id

    popular = db.execute(text("""
        SELECT slot, rank, item_id, item_name, usage_percent, is_crafted, is_embellishment
        FROM archon_popular_items
        WHERE snapshot_id = :sid
        ORDER BY slot, rank
    """), {"sid": sid}).fetchall()

    enchants = db.execute(text("""
        SELECT slot, rank, enchant_id, enchant_name, usage_percent
        FROM archon_popular_enchants
        WHERE snapshot_id = :sid
        ORDER BY slot, rank
    """), {"sid": sid}).fetchall()

    gems = db.execute(text("""
        SELECT gem_quality, rank, item_id, gem_name, usage_percent
        FROM archon_popular_gems
        WHERE snapshot_id = :sid
        ORDER BY gem_quality DESC, rank
    """), {"sid": sid}).fetchall()

    wowhead_bis = db.execute(text("""
        SELECT slot, item_id, item_name
        FROM wowhead_bis_items
        WHERE snapshot_id = :sid
        ORDER BY id
    """), {"sid": sid}).fetchall()

    return {
        "spec_slug": snapshot.spec_slug,
        "class_slug": snapshot.class_slug,
        "scraped_at": snapshot.scraped_at,
        "popular_items": [dict(r._mapping) for r in popular],
        "popular_enchants": [dict(r._mapping) for r in enchants],
        "popular_gems": [dict(r._mapping) for r in gems],
        "wowhead_bis_items": [dict(r._mapping) for r in wowhead_bis],
    }


async def _fetch_icon(client, sem: asyncio.Semaphore, item_id: int) -> tuple[int, str | None]:
    async with sem:
        try:
            r = await client.get(
                f"/data/wow/media/item/{item_id}",
                params={"namespace": f"static-{REGION}"},
            )
            for asset in r.json().get("assets", []):
                if asset.get("key") == "icon":
                    return item_id, asset["value"]
        except Exception as e:
            logger.warning("Icon fetch failed for item %s: %s", item_id, e)
    return item_id, None


@router.get("/item-icons")
async def get_item_icons(
    ids: str = Query(..., description="Comma-separated item IDs"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    item_ids = list({int(x) for x in ids.split(",") if x.strip().isdigit()})
    if not item_ids:
        return {}

    # Pull whatever is already cached in the DB
    cached = db.query(WowItemIcon).filter(WowItemIcon.item_id.in_(item_ids)).all()
    result: dict[int, str] = {row.item_id: row.icon_url for row in cached}

    missing = [iid for iid in item_ids if iid not in result]
    if missing and current_user.blizzard_access_token:
        sem = asyncio.Semaphore(5)
        try:
            async with battlenet_client(current_user.blizzard_access_token) as client:
                fetched = await asyncio.gather(
                    *[_fetch_icon(client, sem, iid) for iid in missing],
                    return_exceptions=True,
                )
        except HTTPException:
            fetched = []

        for entry in fetched:
            if not isinstance(entry, tuple):
                continue
            item_id, icon_url = entry
            if not icon_url:
                continue
            result[item_id] = icon_url
            db.merge(WowItemIcon(item_id=item_id, icon_url=icon_url))
        db.commit()

    return result
