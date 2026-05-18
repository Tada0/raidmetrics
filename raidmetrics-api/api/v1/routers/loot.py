"""Loot report endpoints — upload and retrieve Raidbots Droptimizer reports."""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...dal.db import get_db
from ...dal.models import LootReport, LootReportItem, SeasonConfig, User, UserCharacter
from ..auth import get_current_user
from ..permissions import assert_guild_member
from ..services.raidbots import process_report

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_season_config(db: Session) -> SeasonConfig:
    config = db.query(SeasonConfig).first()
    if not config:
        raise HTTPException(
            status_code=503,
            detail="Season configuration not yet loaded. Run the scraper first.",
        )
    return config


def _ilvl_cap(config: SeasonConfig, difficulty: str) -> int:
    return {"mythic": config.mythic_ilvl_cap, "heroic": config.heroic_ilvl_cap, "normal": config.normal_ilvl_cap}[difficulty]


def _report_to_dict(report: LootReport) -> dict:
    return {
        "id": report.id,
        "character_name": report.character_name,
        "realm_slug": report.realm_slug,
        "difficulty": report.difficulty,
        "raidbots_report_id": report.raidbots_report_id,
        "baseline_dps": report.baseline_dps,
        "equipped_items": report.equipped_items,
        "uploaded_by_user_id": report.uploaded_by_user_id,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }


def _item_to_dict(item: LootReportItem) -> dict:
    return {
        "id": item.id,
        "zone_id": item.zone_id,
        "encounter_id": item.encounter_id,
        "item_id": item.item_id,
        "item_ilvl": item.item_ilvl,
        "slot_name": item.slot_name,
        "item_name": item.item_name,
        "boss_name": item.boss_name,
        "raid_name": item.raid_name,
        "upgrade_dps": item.upgrade_dps,
        "upgrade_pct": item.upgrade_pct,
    }


# ---------------------------------------------------------------------------
# POST /guilds/{guild_id}/loot/report
# ---------------------------------------------------------------------------

class UploadReportRequest(BaseModel):
    report_url: str
    difficulty: str       # 'normal' | 'heroic' | 'mythic'
    character_name: str
    realm_slug: str


@router.post("/guilds/{guild_id}/loot/report")
async def upload_loot_report(
    guild_id: int,
    body: UploadReportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.difficulty not in ("normal", "heroic", "mythic"):
        raise HTTPException(status_code=422, detail="difficulty must be 'normal', 'heroic', or 'mythic'.")

    assert_guild_member(guild_id, current_user)

    # Verify the specified character belongs to this user in this guild
    matched_char = (
        db.query(UserCharacter)
        .filter(
            UserCharacter.user_id == current_user.id,
            UserCharacter.guild_id == guild_id,
            UserCharacter.character_name == body.character_name,
            UserCharacter.realm_slug == body.realm_slug,
        )
        .first()
    )
    if not matched_char:
        raise HTTPException(status_code=403, detail="Character not found for this user and guild.")

    config = _get_season_config(db)
    ilvl_cap = _ilvl_cap(config, body.difficulty)

    parsed, items, report_id = await process_report(
        url=body.report_url,
        expected_character=body.character_name,
        expected_realm=body.realm_slug,
        expected_difficulty=body.difficulty,
        current_zone_ids=config.zone_ids,
        ilvl_cap=ilvl_cap,
    )

    # Upsert loot_report
    existing = (
        db.query(LootReport)
        .filter(
            LootReport.guild_id == guild_id,
            LootReport.character_name == matched_char.character_name,
            LootReport.realm_slug == matched_char.realm_slug,
            LootReport.difficulty == body.difficulty,
        )
        .first()
    )

    equipped_items_json = [
        {
            "slot": e.slot,
            "item_name": e.item_name,
            "item_id": e.item_id,
            "ilvl": e.ilvl,
            "enchant_id": e.enchant_id,
            "gem_ids": e.gem_ids,
            "bonus_ids": e.bonus_ids,
            "crafted": e.crafted,
        }
        for e in parsed.equipped_items
    ]

    if existing:
        existing.raidbots_report_id = report_id
        existing.baseline_dps = parsed.baseline_dps
        existing.equipped_items = equipped_items_json
        existing.uploaded_by_user_id = current_user.id
        existing.updated_at = datetime.now(UTC)
        # Delete old items — cascade will handle it via relationship
        for old_item in list(existing.items):
            db.delete(old_item)
        db.flush()
        report = existing
    else:
        report = LootReport(
            guild_id=guild_id,
            character_name=matched_char.character_name,
            realm_slug=matched_char.realm_slug,
            difficulty=body.difficulty,
            raidbots_report_id=report_id,
            baseline_dps=parsed.baseline_dps,
            equipped_items=equipped_items_json,
            uploaded_by_user_id=current_user.id,
        )
        db.add(report)
        db.flush()

    for item in items:
        db.add(LootReportItem(
            report_id=report.id,
            zone_id=item["zone_id"],
            encounter_id=item["encounter_id"],
            item_id=item["item_id"],
            item_ilvl=item["item_ilvl"],
            slot_name=item["slot_name"],
            item_name=item.get("item_name"),
            boss_name=item.get("boss_name"),
            raid_name=item.get("raid_name"),
            upgrade_dps=item["upgrade_dps"],
            upgrade_pct=item["upgrade_pct"],
        ))

    db.commit()
    db.refresh(report)

    return {
        "report": _report_to_dict(report),
        "items": [_item_to_dict(i) for i in report.items],
    }


# ---------------------------------------------------------------------------
# GET /guilds/{guild_id}/loot
# ---------------------------------------------------------------------------

@router.get("/guilds/{guild_id}/loot")
def get_loot_report(
    guild_id: int,
    character_name: str,
    realm_slug: str,
    difficulty: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_guild_member(guild_id, current_user)

    report = (
        db.query(LootReport)
        .filter(
            LootReport.guild_id == guild_id,
            LootReport.character_name == character_name,
            LootReport.realm_slug == realm_slug,
            LootReport.difficulty == difficulty,
        )
        .first()
    )

    if not report:
        return {"report": None, "items": []}

    return {
        "report": _report_to_dict(report),
        "items": [_item_to_dict(i) for i in report.items],
    }
