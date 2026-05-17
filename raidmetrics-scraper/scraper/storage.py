import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import (
    ArchonPopularEnchant, ArchonPopularGem,
    ArchonPopularItem, ArchonScrapeRun, ArchonSpecSnapshot, WowheadBisItem,
)
from .parsers import ScrapedSpec

logger = logging.getLogger(__name__)

RUNS_TO_KEEP = 5


def create_run(db: Session) -> ArchonScrapeRun:
    run = ArchonScrapeRun(started_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info("Created run %d", run.id)
    return run


def finish_run(db: Session, run: ArchonScrapeRun, *, success: bool, error: str | None = None):
    run.completed_at = datetime.now(timezone.utc)
    run.success = success
    run.error_message = error
    db.commit()
    logger.info("Run %d finished (success=%s)", run.id, success)


def save_spec(db: Session, run: ArchonScrapeRun, spec: ScrapedSpec) -> ArchonSpecSnapshot:
    snapshot = ArchonSpecSnapshot(
        run_id=run.id,
        spec_slug=spec.spec_slug,
        class_slug=spec.class_slug,
        scraped_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    db.flush()

    for item in spec.popular_items:
        db.add(ArchonPopularItem(
            snapshot_id=snapshot.id,
            slot=item.slot,
            rank=item.rank,
            item_id=item.item_id,
            item_id2=item.item_id2,
            item_name=item.item_name,
            usage_percent=item.usage_percent,
            is_crafted=item.is_crafted,
            is_embellishment=item.is_embellishment,
        ))

    for enchant in spec.popular_enchants:
        db.add(ArchonPopularEnchant(
            snapshot_id=snapshot.id,
            slot=enchant.slot,
            rank=enchant.rank,
            enchant_id=enchant.enchant_id,
            enchant_name=enchant.enchant_name,
            usage_percent=enchant.usage_percent,
            icon_name=enchant.icon_name,
        ))

    for gem in spec.popular_gems:
        db.add(ArchonPopularGem(
            snapshot_id=snapshot.id,
            gem_quality=gem.gem_quality,
            rank=gem.rank,
            item_id=gem.item_id,
            gem_name=gem.gem_name,
            usage_percent=gem.usage_percent,
        ))

    for bis in spec.wowhead_bis_items:
        db.add(WowheadBisItem(
            snapshot_id=snapshot.id,
            slot=bis.slot,
            item_id=bis.item_id,
            item_name=bis.item_name,
        ))

    run.specs_scraped += 1
    db.commit()
    return snapshot


def prune_old_runs(db: Session):
    """Delete runs beyond the most recent RUNS_TO_KEEP successful ones, and failed runs older than 24h."""
    old_successful = (
        db.query(ArchonScrapeRun)
        .filter(ArchonScrapeRun.success == True)
        .order_by(ArchonScrapeRun.completed_at.desc())
        .offset(RUNS_TO_KEEP)
        .all()
    )
    for run in old_successful:
        logger.info("Pruning old run %d (%s)", run.id, run.completed_at)
        db.delete(run)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    old_failed = (
        db.query(ArchonScrapeRun)
        .filter(ArchonScrapeRun.success == False, ArchonScrapeRun.started_at < cutoff)
        .all()
    )
    for run in old_failed:
        logger.info("Pruning failed run %d (%s)", run.id, run.started_at)
        db.delete(run)

    db.commit()
