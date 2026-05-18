"""Fetch, parse and validate Raidbots Droptimizer reports."""
import csv
import io
import logging
import re
from dataclasses import dataclass, field

import httpx
from fastapi import HTTPException

from ..battlenet import battlenet_client

logger = logging.getLogger(__name__)

_RAIDBOTS_BASE = "https://www.raidbots.com/simbot/report"
_REPORT_ID_RE = re.compile(r"raidbots\.com/simbot/report/([A-Za-z0-9_-]+)")
_BLIZZARD_EQUIPMENT_PATH = "/profile/wow/character/{realm}/{character}/equipment"


# ---------------------------------------------------------------------------
# Public result types
# ---------------------------------------------------------------------------

@dataclass
class EquippedItem:
    slot: str
    item_name: str
    item_id: int
    ilvl: int
    enchant_id: int | None
    gem_ids: list[int]
    bonus_ids: list[int]
    crafted: bool


@dataclass
class ParsedReport:
    character_name: str
    realm_slug: str           # lowercased server name from SimC profile
    region: str
    difficulty: str           # 'normal' | 'heroic' | 'mythic'
    zone_ids: set[int]
    profileset_ilvl: int
    desired_targets: int
    max_time: int
    upgrade_all_equipped: bool
    catalyst_included: bool
    baseline_dps: float
    equipped_items: list[EquippedItem]
    items: list[dict]         # raw upgrade rows from CSV


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _extract_report_id(url: str) -> str:
    m = _REPORT_ID_RE.search(url)
    if not m:
        raise HTTPException(status_code=422, detail="Invalid Raidbots report URL.")
    return m.group(1)


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


async def fetch_report(url: str) -> tuple[str, str]:
    """Return (input_txt, data_csv) fetched in parallel."""
    report_id = _extract_report_id(url)
    input_url = f"{_RAIDBOTS_BASE}/{report_id}/input.txt"
    csv_url = f"{_RAIDBOTS_BASE}/{report_id}/data.csv"

    async with httpx.AsyncClient(timeout=30, headers=_HEADERS, follow_redirects=True) as client:
        input_resp, csv_resp = await _gather(
            client.get(input_url),
            client.get(csv_url),
        )

    logger.info("Raidbots fetch: input=%s csv=%s", input_resp.status_code, csv_resp.status_code)

    if input_resp.status_code != 200:
        raise HTTPException(status_code=422, detail="Could not fetch report input. Is the URL correct?")
    if csv_resp.status_code != 200:
        raise HTTPException(status_code=422, detail="Could not fetch report data. Is the URL correct?")

    return input_resp.text, csv_resp.text


async def _gather(*coros):
    import asyncio
    return await asyncio.gather(*coros)


# ---------------------------------------------------------------------------
# Parse input.txt
# ---------------------------------------------------------------------------

_CLASS_LINE_RE = re.compile(r'^[a-z_]+=\s*"([^"]+)"', re.IGNORECASE)
_PROFILESET_RE = re.compile(
    r'^profileset\."(\d+)/(\d+)/raid-(mythic|heroic|normal)/(\d+)/(\d+)/'
)
_COMMENT_ITEM_RE = re.compile(
    r'^#\s+(.+?)\s+(\d+)\s+-\s+(.+?)\s+-\s+(.+)$'
)
_SLOT_LINE_RE = re.compile(
    r'^([a-z_0-9]+)=,id=(\d+)'
    r'(?:,enchant_id=(\d+))?'
    r'(?:,gem_id=([\d/]+))?'
    r'(?:.*bonus_id=([\d/]+))?'
    r'(?:.*crafting_quality=(\d+))?'
)
_ITEM_COMMENT_RE = re.compile(r'^#\s+(.+?)\s+\((\d+)\)')


def _parse_input(txt: str) -> dict:
    lines = txt.splitlines()

    result = {
        "character_name": None,
        "realm_slug": None,
        "region": None,
        "desired_targets": None,
        "max_time": None,
        "zone_ids": set(),
        "difficulty": None,
        "profileset_ilvl": None,
        "upgrade_all_equipped": False,
        "has_external_buffs": False,
        "equipped_items": [],
        # For profileset comment lookup: maps profileset key prefix → (item_name, raid_name, boss_name)
        "_profileset_comments": {},
    }

    # --- single-pass state machine ---
    in_equipped = False          # inside the base equipped-items block
    in_upgraded = False          # inside "# Upgraded Equipped Items"
    upgraded_item_ids: set[int] = set()
    pending_comment: tuple | None = None  # (item_name, ilvl, raid_name, boss_name)
    pending_item_comment: tuple | None = None  # (item_name, ilvl) for slot lines

    for line in lines:
        stripped = line.strip()

        # Character name (first `class="name"` line, e.g. deathknight="Naughtybella")
        if result["character_name"] is None and not stripped.startswith("#"):
            m = _CLASS_LINE_RE.match(stripped)
            if m:
                result["character_name"] = m.group(1)

        # server / region / desired_targets / max_time
        for key, attr in (
            ("server=", "realm_slug"),
            ("region=", "region"),
        ):
            if stripped.startswith(key) and not stripped.startswith("#"):
                result[attr] = stripped[len(key):]

        if stripped.startswith("desired_targets=") and not stripped.startswith("#"):
            result["desired_targets"] = int(stripped.split("=")[1])
        if stripped.startswith("max_time=") and not stripped.startswith("#"):
            result["max_time"] = int(stripped.split("=")[1])
        if stripped.startswith("external_buffs.pool=") and not stripped.startswith("#"):
            result["has_external_buffs"] = True

        # Section markers
        if stripped == "### Gear from Bags":
            in_equipped = False
            pending_item_comment = None
            continue

        if stripped == "# Upgraded Equipped Items":
            in_upgraded = True
            in_equipped = False
            continue

        # Once we hit `name=<character>` after "Upgraded Equipped Items" the section ends
        if in_upgraded and stripped.startswith("name=") and not stripped.startswith("#"):
            in_upgraded = False
            continue

        # Track upgraded item IDs
        if in_upgraded and not stripped.startswith("#") and stripped:
            m = _SLOT_LINE_RE.match(stripped)
            if m:
                upgraded_item_ids.add(int(m.group(2)))

        # Profileset comment: `# Item Name (289) - Raid - Boss`
        m = _COMMENT_ITEM_RE.match(stripped)
        if m:
            pending_comment = (m.group(1), m.group(2), m.group(3), m.group(4))

        # Profileset line
        m = _PROFILESET_RE.match(stripped)
        if m:
            zone_id, enc_id, diff, item_id, ilvl = (
                int(m.group(1)), int(m.group(2)), m.group(3),
                int(m.group(4)), int(m.group(5)),
            )
            result["zone_ids"].add(zone_id)
            if result["difficulty"] is None:
                result["difficulty"] = diff
            if result["profileset_ilvl"] is None or ilvl > result["profileset_ilvl"]:
                result["profileset_ilvl"] = ilvl

            if pending_comment:
                key = (zone_id, enc_id, item_id)
                if key not in result["_profileset_comments"]:
                    result["_profileset_comments"][key] = pending_comment
            pending_comment = None
            continue

        # Equipped gear section: starts after the character name block,
        # we detect slot lines before "### Gear from Bags"
        if not stripped.startswith("#") and not stripped.startswith("name=") and stripped:
            # Item comment line just before a slot line
            m2 = _ITEM_COMMENT_RE.match(stripped if stripped.startswith("#") else "#")
            # handled below

            m = _SLOT_LINE_RE.match(stripped)
            if m and result["character_name"] and not in_upgraded:
                slot = m.group(1)
                item_id = int(m.group(2))
                enchant_id = int(m.group(3)) if m.group(3) else None
                gem_ids = [int(g) for g in m.group(4).split("/")] if m.group(4) else []
                bonus_ids = [int(b) for b in m.group(5).split("/")] if m.group(5) else []
                crafted = m.group(6) is not None

                item_name = ""
                ilvl = 0
                if pending_item_comment:
                    item_name, ilvl = pending_item_comment
                    pending_item_comment = None

                result["equipped_items"].append(EquippedItem(
                    slot=slot,
                    item_name=item_name,
                    item_id=item_id,
                    ilvl=ilvl,
                    enchant_id=enchant_id,
                    gem_ids=gem_ids,
                    bonus_ids=bonus_ids,
                    crafted=crafted,
                ))
                in_equipped = True

        # Item comment before a slot line: `# Item Name (289)`
        if stripped.startswith("#") and not in_upgraded:
            m = _ITEM_COMMENT_RE.match(stripped)
            if m and "/" not in stripped and "-" not in stripped[2:]:
                pending_item_comment = (m.group(1), int(m.group(2)))

    # Upgrade All Equipped: any non-crafted equipped item below profileset_ilvl
    # that also appears in upgraded_item_ids → was upgraded → option ON.
    # If no items needed upgrading (all at cap), we accept it too.
    cap = result["profileset_ilvl"] or 0
    needs_upgrade = [
        e for e in result["equipped_items"]
        if not e.crafted and e.ilvl < cap
    ]
    if needs_upgrade:
        result["upgrade_all_equipped"] = any(
            e.item_id in upgraded_item_ids for e in needs_upgrade
        )
    else:
        # All gear already at or above cap — option doesn't matter
        result["upgrade_all_equipped"] = True

    return result


# ---------------------------------------------------------------------------
# Parse data.csv
# ---------------------------------------------------------------------------

_CSV_NAME_RE = re.compile(
    r'^(\d+)/(\d+)/raid-(mythic|heroic|normal)/(\d+)/(\d+)/(\d*)/([^/]+)///$'
)


def _parse_csv(csv_text: str, profileset_comments: dict) -> tuple[float, list[dict], bool]:
    """Return (baseline_dps, items, catalyst_included)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)

    if not rows:
        raise HTTPException(status_code=422, detail="Report data is empty.")

    baseline_dps: float | None = None
    # keyed by (zone_id, encounter_id, item_id) — keeps only the best slot variant
    best_items: dict[tuple, dict] = {}

    _CATALYST_MIN_ROWS = 35

    for row in rows:
        name = row.get("name", "").strip()
        dps_mean = float(row.get("dps_mean", 0))

        if baseline_dps is None:
            # First row is always the baseline character
            baseline_dps = dps_mean
            continue

        m = _CSV_NAME_RE.match(name)
        if not m:
            continue

        zone_id = int(m.group(1))
        enc_id = int(m.group(2))
        item_id = int(m.group(4))
        item_ilvl = int(m.group(5))
        slot_name = m.group(7)

        upgrade_dps = dps_mean - baseline_dps
        upgrade_pct = (upgrade_dps / baseline_dps) * 100

        if upgrade_pct <= 0:
            continue

        key = (zone_id, enc_id, item_id)
        existing = best_items.get(key)
        if existing and existing["upgrade_pct"] >= round(upgrade_pct, 4):
            continue

        comment = profileset_comments.get(key, ())
        item_name = comment[0] if comment else None
        raid_name = comment[2] if comment else None
        boss_name = comment[3] if comment else None

        best_items[key] = {
            "zone_id": zone_id,
            "encounter_id": enc_id,
            "item_id": item_id,
            "item_ilvl": item_ilvl,
            "slot_name": slot_name,
            "item_name": item_name,
            "boss_name": boss_name,
            "raid_name": raid_name,
            "upgrade_dps": round(upgrade_dps, 2),
            "upgrade_pct": round(upgrade_pct, 4),
        }

    catalyst_included = len(rows) - 1 >= _CATALYST_MIN_ROWS  # -1 for baseline row

    return baseline_dps or 0.0, list(best_items.values()), catalyst_included


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def validate_report(
    parsed: dict,
    expected_character: str,
    expected_realm: str,
    expected_difficulty: str,
    current_zone_ids: list[int],
    ilvl_cap: int,
    catalyst_included: bool,
    total_csv_rows: int,
) -> None:
    errors = []

    char = (parsed["character_name"] or "").lower()
    realm = (parsed["realm_slug"] or "").lower()
    exp_char = expected_character.lower()
    exp_realm = expected_realm.lower()

    if char != exp_char or realm != exp_realm:
        errors.append(
            f"Report is for {parsed['character_name']}-{parsed['realm_slug']}, "
            f"expected {expected_character}-{expected_realm}."
        )

    if parsed["difficulty"] != expected_difficulty:
        errors.append(
            f"Report difficulty is '{parsed['difficulty']}', expected '{expected_difficulty}'."
        )

    missing_zones = set(current_zone_ids) - parsed["zone_ids"]
    if missing_zones:
        errors.append(
            "Report must be run with 'Season 1 Raids' selected (missing raid zones)."
        )

    if parsed["desired_targets"] != 1:
        errors.append("Report must be run with 1 boss (Patchwerk, single target).")

    if parsed["max_time"] != 300:
        errors.append("Report must use 5 minute fight length (300 seconds).")

    if parsed["profileset_ilvl"] != ilvl_cap:
        errors.append(
            f"Report upgrade cap must be {ilvl_cap} ilvl for {expected_difficulty}. "
            f"Found {parsed['profileset_ilvl']}."
        )

    if not parsed["upgrade_all_equipped"]:
        errors.append("Report must be run with 'Upgrade All Equipped Gear to the Same Level' enabled.")

    if parsed["has_external_buffs"]:
        errors.append("Report must have external buffs disabled (e.g. Power Infusion).")

    if not catalyst_included:
        errors.append("Report must be run with 'Include Catalyst Items' enabled.")

    if errors:
        raise HTTPException(status_code=422, detail=errors)


# ---------------------------------------------------------------------------
# Gear comparison against Blizzard live data
# ---------------------------------------------------------------------------

_SIMC_TO_BLIZZARD_SLOT: dict[str, str] = {
    "head": "HEAD",
    "neck": "NECK",
    "shoulder": "SHOULDER",
    "back": "BACK",
    "chest": "CHEST",
    "wrist": "WRIST",
    "hands": "HANDS",
    "waist": "WAIST",
    "legs": "LEGS",
    "feet": "FEET",
    "finger1": "FINGER_1",
    "finger2": "FINGER_2",
    "trinket1": "TRINKET_1",
    "trinket2": "TRINKET_2",
    "main_hand": "MAIN_HAND",
    "off_hand": "OFF_HAND",
}


async def _fetch_blizzard_gear(character_name: str, realm_slug: str, access_token: str) -> dict[str, dict]:
    """Return {BLIZZARD_SLOT_TYPE: {item_id, bonus_ids, enchant_id, gem_ids}} from Blizzard API."""
    path = _BLIZZARD_EQUIPMENT_PATH.format(realm=realm_slug.lower(), character=character_name.lower())
    async with battlenet_client(access_token) as client:
        resp = await client.get(path)

    gear: dict[str, dict] = {}
    for item in resp.json().get("equipped_items", []):
        slot_type = item.get("slot", {}).get("type", "")
        if not slot_type:
            continue
        enchant_id = next(
            (e["enchantment_id"] for e in item.get("enchantments", [])
             if e.get("enchantment_slot", {}).get("type") == "PERMANENT"),
            None,
        )
        sockets = item.get("sockets", [])
        gem_ids = sorted(s["item"]["id"] for s in sockets if s.get("item", {}).get("id"))
        gear[slot_type] = {
            "item_id": item.get("item", {}).get("id", 0),
            "bonus_ids": set(item.get("bonus_list", [])),
            "enchant_id": enchant_id,
            "gem_ids": gem_ids,
        }
    return gear


async def validate_gear_matches_blizzard(
    equipped_items: list[EquippedItem],
    character_name: str,
    realm_slug: str,
    access_token: str,
) -> None:
    """Raise HTTPException 422 if any simulated slot doesn't match live Blizzard gear."""
    live_gear = await _fetch_blizzard_gear(character_name, realm_slug, access_token)

    errors = []
    for item in equipped_items:
        blizzard_slot = _SIMC_TO_BLIZZARD_SLOT.get(item.slot)
        if blizzard_slot is None:
            continue

        live = live_gear.get(blizzard_slot)
        if live is None:
            errors.append(f"Slot {item.slot}: item not found on your character.")
            continue

        if item.item_id != live["item_id"]:
            errors.append(
                f"Slot {item.slot}: item doesn't match your current gear "
                f"(sim item ID {item.item_id}, live item ID {live['item_id']}). "
                "Please re-run the simulation with your current gear."
            )
            continue

        if set(item.bonus_ids) != live["bonus_ids"]:
            errors.append(
                f"Slot {item.slot} ({item.item_name}): item stats/ilvl have changed since the simulation was run. "
                "Please re-run the simulation with your current gear."
            )

        if item.enchant_id != live["enchant_id"]:
            errors.append(
                f"Slot {item.slot} ({item.item_name}): enchant has changed since the simulation was run. "
                "Please re-run the simulation with your current gear."
            )

        if sorted(item.gem_ids) != live["gem_ids"]:
            errors.append(
                f"Slot {item.slot} ({item.item_name}): gems have changed since the simulation was run. "
                "Please re-run the simulation with your current gear."
            )

    if errors:
        raise HTTPException(status_code=422, detail=errors)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def process_report(
    url: str,
    expected_character: str,
    expected_realm: str,
    expected_difficulty: str,
    current_zone_ids: list[int],
    ilvl_cap: int,
    blizzard_access_token: str,
) -> tuple[ParsedReport, list[dict]]:
    """Fetch, parse and validate. Returns (ParsedReport, items)."""
    input_txt, csv_txt = await fetch_report(url)
    report_id = _extract_report_id(url)

    parsed_input = _parse_input(input_txt)
    baseline_dps, items, catalyst_included = _parse_csv(csv_txt, parsed_input["_profileset_comments"])

    total_csv_rows = len(list(csv.reader(io.StringIO(csv_txt)))) - 1  # -1 header

    validate_report(
        parsed_input,
        expected_character,
        expected_realm,
        expected_difficulty,
        current_zone_ids,
        ilvl_cap,
        catalyst_included,
        total_csv_rows,
    )

    await validate_gear_matches_blizzard(
        equipped_items=parsed_input["equipped_items"],
        character_name=expected_character,
        realm_slug=expected_realm,
        access_token=blizzard_access_token,
    )

    report = ParsedReport(
        character_name=parsed_input["character_name"],
        realm_slug=parsed_input["realm_slug"],
        region=parsed_input["region"],
        difficulty=expected_difficulty,
        zone_ids=parsed_input["zone_ids"],
        profileset_ilvl=parsed_input["profileset_ilvl"],
        desired_targets=parsed_input["desired_targets"],
        max_time=parsed_input["max_time"],
        upgrade_all_equipped=parsed_input["upgrade_all_equipped"],
        catalyst_included=catalyst_included,
        baseline_dps=baseline_dps,
        equipped_items=parsed_input["equipped_items"],
        items=items,
    )

    return report, items, report_id
