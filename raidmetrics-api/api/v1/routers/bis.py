from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...dal.db import get_db
from ..auth import get_current_user

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

    bis = db.execute(text("""
        SELECT slot, item_id, item_name, is_bis, usage_percent, gem_ids, enchant_id
        FROM archon_bis_items
        WHERE snapshot_id = :sid
        ORDER BY slot
    """), {"sid": sid}).fetchall()

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

    return {
        "spec_slug": snapshot.spec_slug,
        "class_slug": snapshot.class_slug,
        "scraped_at": snapshot.scraped_at,
        "bis_items": [dict(r._mapping) for r in bis],
        "popular_items": [dict(r._mapping) for r in popular],
        "popular_enchants": [dict(r._mapping) for r in enchants],
        "popular_gems": [dict(r._mapping) for r in gems],
    }
