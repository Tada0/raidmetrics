import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import (
    ArchonPopularEnchant, ArchonPopularGem,
    ArchonPopularItem, ArchonScrapeRun, ArchonSpecSnapshot, BossLootItem, SeasonConfig, WowheadBisItem,
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


def update_season_config(db: Session, season_name: str, zone_ids: list[int], ilvl_caps: dict) -> None:
    """Upsert the single SeasonConfig row."""
    config = db.query(SeasonConfig).first()
    if config is None:
        config = SeasonConfig()
        db.add(config)
    config.season_name = season_name
    config.zone_ids = zone_ids
    config.mythic_ilvl_cap = ilvl_caps["mythic"]
    config.heroic_ilvl_cap = ilvl_caps["heroic"]
    config.normal_ilvl_cap = ilvl_caps["normal"]
    config.updated_at = datetime.now(timezone.utc)
    db.commit()


def save_boss_loot(db: Session, loot: list[dict]) -> None:
    """Replace all boss_loot_items rows with fresh data from the Journal API."""
    db.query(BossLootItem).delete()
    for row in loot:
        db.add(BossLootItem(
            encounter_id=row["encounter_id"],
            zone_id=row["zone_id"],
            boss_name=row["boss_name"],
            item_id=row["item_id"],
            item_name=row["item_name"],
            is_token=row.get("is_token", False),
            synthesizes_slot=row.get("synthesizes_slot"),
            allowed_class_ids=row.get("allowed_class_ids"),
        ))
    db.commit()
    logger.info("Saved %d boss loot items", len(loot))


def prune_old_loot_reports(db: Session, max_age_hours: int = 12) -> None:
    """Delete loot reports (and their items) older than max_age_hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    db.execute(
        text("""
            DELETE FROM loot_report_items
            WHERE report_id IN (
                SELECT id FROM loot_reports WHERE updated_at < :cutoff
            )
        """),
        {"cutoff": cutoff},
    )
    result = db.execute(
        text("DELETE FROM loot_reports WHERE updated_at < :cutoff"),
        {"cutoff": cutoff},
    )
    db.commit()
    if result.rowcount:
        logger.info("Pruned %d expired loot reports (older than %dh)", result.rowcount, max_age_hours)


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
