"""Core scrape logic, shared by the CLI entry point and the service."""
import asyncio
import logging
import os

import httpx

from .client import ArchonClient
from .config import CONCURRENT_SPECS, SPECS
from .db import get_session, init_db
from .parsers import ScrapedSpec
from .parsers.enchants import parse_enchants_gems
from .parsers.gear import parse_gear
from .parsers.wowhead_bis import fetch_wowhead_bis
from .models import WowItemIcon
from .storage import create_run, finish_run, prune_old_runs, save_boss_loot, save_spec, update_season_config

_BLIZZARD_CLIENT_ID = os.getenv("BLIZZARD_CLIENT_ID", "")
_BLIZZARD_CLIENT_SECRET = os.getenv("BLIZZARD_CLIENT_SECRET", "")
_BLIZZARD_REGION = os.getenv("BLIZZARD_REGION", "eu")

logger = logging.getLogger(__name__)


async def _scrape_spec(
    archon: ArchonClient,
    wowhead: httpx.AsyncClient,
    spec_slug: str,
    class_slug: str,
    sem: asyncio.Semaphore,
    wowhead_sem: asyncio.Semaphore,
) -> ScrapedSpec | None:
    async with sem:
        logger.info("Scraping %s/%s", spec_slug, class_slug)
        try:
            gear_data, enchants_data, bis_items = await asyncio.gather(
                archon.fetch_page(spec_slug, class_slug, "gear-and-tier-set"),
                archon.fetch_page(spec_slug, class_slug, "enchants-and-gems"),
                fetch_wowhead_bis(spec_slug, class_slug, wowhead, wowhead_sem),
            )
        except Exception as exc:
            logger.error("Failed %s/%s: %s", spec_slug, class_slug, exc)
            return None

        popular_items = parse_gear(gear_data)
        enchants, gems = parse_enchants_gems(enchants_data)

        logger.info(
            "%s/%s — %d WoWhead BiS, %d popular, %d enchants, %d gems",
            spec_slug, class_slug,
            len(bis_items), len(popular_items), len(enchants), len(gems),
        )
        return ScrapedSpec(
            spec_slug=spec_slug,
            class_slug=class_slug,
            popular_items=popular_items,
            popular_enchants=enchants,
            popular_gems=gems,
            wowhead_bis_items=bis_items,
        )


_INSTANCES_URL = "https://www.raidbots.com/static/data/live/instances.json"
_BLIZZARD_TOKEN_URL = "https://oauth.battle.net/token"
_BLIZZARD_JOURNAL_URL = "https://{region}.api.blizzard.com/data/wow/journal-encounter/{encounter_id}"
_BLIZZARD_ITEM_URL = "https://{region}.api.blizzard.com/data/wow/item/{item_id}"

# item_subclass.name for curios (Reagent class, subclass Context Token)
_TOKEN_SUBCLASS_NAME = "Context Token"

# ilvl caps per difficulty for the current tier — update each new season
_ILVL_CAPS = {"mythic": 289, "heroic": 276, "normal": 263}


async def _get_blizzard_app_token(client: httpx.AsyncClient) -> str | None:
    """Fetch a client credentials token from Blizzard OAuth."""
    if not _BLIZZARD_CLIENT_ID or not _BLIZZARD_CLIENT_SECRET:
        logger.warning("BLIZZARD_CLIENT_ID/SECRET not set — skipping boss loot scrape")
        return None
    resp = await client.post(
        _BLIZZARD_TOKEN_URL,
        data={"grant_type": "client_credentials"},
        auth=(_BLIZZARD_CLIENT_ID, _BLIZZARD_CLIENT_SECRET),
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def _fetch_item_details(
    client: httpx.AsyncClient,
    token: str,
    item_id: int,
    sem: asyncio.Semaphore,
) -> dict:
    """Fetch item class, inventory type, and class restrictions from Blizzard item API."""
    async with sem:
        url = _BLIZZARD_ITEM_URL.format(region=_BLIZZARD_REGION, item_id=item_id)
        resp = await client.get(
            url,
            params={"namespace": f"static-{_BLIZZARD_REGION}", "locale": "en_US"},
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        return {}
    data = resp.json()
    preview = data.get("preview_item", {})

    item_subclass_name = data.get("item_subclass", {}).get("name", "")

    # Slot description lives in preview_item.spells[].description ("Use: Synthesize a ... leg item")
    spell_descs = " ".join(s.get("description", "") for s in preview.get("spells", []))

    is_token = (
        item_subclass_name == _TOKEN_SUBCLASS_NAME          # Reagent > Context Token (curios)
        or "synthesize" in spell_descs.lower()              # nullcores
    )

    # Class links live in preview_item.requirements.playable_classes.links
    class_links = (
        preview.get("requirements", {})
        .get("playable_classes", {})
        .get("links", [])
    )
    allowed_class_ids = [c["id"] for c in class_links] if class_links else None

    synthesizes_slot = None
    if is_token:
        searchable = (
            (data.get("description") or "") + " " +
            (preview.get("description") or "") + " " +
            spell_descs
        ).lower()
        for slot_kw, slot_name in (
            ("shoulder", "shoulder"), ("chest", "chest"), ("wrist", "wrist"),
            ("waist", "waist"), ("feet", "feet"), ("neck", "neck"),
            ("back", "back"), ("finger", "finger"), ("trinket", "trinket"),
            ("head", "head"), ("hand", "hands"), ("leg", "legs"),
        ):
            if slot_kw in searchable:
                synthesizes_slot = slot_name
                break

    return {
        "is_equippable": data.get("is_equippable", False),
        "is_token": is_token,
        "synthesizes_slot": synthesizes_slot,
        "allowed_class_ids": allowed_class_ids,
    }


async def _fetch_encounter_loot(
    client: httpx.AsyncClient,
    token: str,
    encounter_id: int,
    zone_id: int,
    boss_name: str,
    sem: asyncio.Semaphore,
) -> list[dict]:
    async with sem:
        url = _BLIZZARD_JOURNAL_URL.format(region=_BLIZZARD_REGION, encounter_id=encounter_id)
        resp = await client.get(
            url,
            params={"namespace": f"static-{_BLIZZARD_REGION}", "locale": "en_US"},
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code != 200:
        logger.warning("Journal API returned %s for encounter %d", resp.status_code, encounter_id)
        return []

    item_entries = [
        (entry.get("item", {}).get("id"), entry.get("item", {}).get("name"))
        for entry in resp.json().get("items", [])
        if entry.get("item", {}).get("id")
    ]

    # Fetch item details for all items in parallel (shared semaphore limits total concurrency)
    detail_tasks = [
        _fetch_item_details(client, token, item_id, sem)
        for item_id, _ in item_entries
    ]
    details = await asyncio.gather(*detail_tasks, return_exceptions=True)

    rows = []
    for (item_id, item_name), detail in zip(item_entries, details):
        if isinstance(detail, Exception):
            detail = {}
        is_token = detail.get("is_token", False)
        is_equippable = detail.get("is_equippable", False)
        if not is_equippable and not is_token:
            continue  # skip mounts, housing items, etc.
        rows.append({
            "encounter_id": encounter_id,
            "zone_id": zone_id,
            "boss_name": boss_name,
            "item_id": item_id,
            "item_name": item_name,
            "is_token": is_token,
            "synthesizes_slot": detail.get("synthesizes_slot"),
            "allowed_class_ids": detail.get("allowed_class_ids"),
        })
    return rows


async def _scrape_season_config(client: httpx.AsyncClient, db) -> None:
    """Fetch instances.json, upsert SeasonConfig, and scrape boss loot tables."""
    resp = await client.get(_INSTANCES_URL)
    resp.raise_for_status()
    instances = resp.json()

    # Current season = raid aggregate (negative id) with the lowest order value
    raid_aggregates = [
        i for i in instances
        if i.get("id", 0) < 0 and i.get("type") == "raid" and "order" in i
    ]
    if not raid_aggregates:
        logger.warning("No raid aggregates found in instances.json")
        return

    current = min(raid_aggregates, key=lambda i: i["order"])
    season_name = current["name"]

    encounter_ids = {e["id"] for e in current.get("encounters", [])}

    # Build encounter → zone_id and encounter → boss_name mappings
    encounter_to_zone: dict[int, int] = {}
    encounter_to_name: dict[int, str] = {}
    zone_ids_set: set[int] = set()
    for inst in instances:
        if inst.get("id", 0) > 0 and inst.get("type") == "raid":
            for enc in inst.get("encounters", []):
                if enc["id"] in encounter_ids:
                    encounter_to_zone[enc["id"]] = inst["id"]
                    encounter_to_name[enc["id"]] = enc.get("name", "")
                    zone_ids_set.add(inst["id"])

    if not zone_ids_set:
        logger.warning("Could not derive zone IDs for %s", season_name)
        return

    zone_ids = sorted(zone_ids_set)
    update_season_config(db, season_name, zone_ids, _ILVL_CAPS)
    logger.info("Season config updated: %s zones=%s", season_name, zone_ids)

    # Scrape boss loot tables from Blizzard Journal API
    token = await _get_blizzard_app_token(client)
    if not token:
        return

    sem = asyncio.Semaphore(3)
    tasks = [
        _fetch_encounter_loot(client, token, enc_id, encounter_to_zone[enc_id], encounter_to_name[enc_id], sem)
        for enc_id in encounter_ids
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_loot: list[dict] = []
    for r in results:
        if isinstance(r, Exception):
            logger.error("Boss loot fetch error: %s", r)
        else:
            all_loot.extend(r)

    if all_loot:
        save_boss_loot(db, all_loot)
        logger.info("Boss loot scraped: %d items across %d encounters", len(all_loot), len(encounter_ids))
        await _cache_item_icons(client, token, [row["item_id"] for row in all_loot], db, sem)


async def _cache_item_icons(
    client: httpx.AsyncClient,
    token: str,
    item_ids: list[int],
    db,
    sem: asyncio.Semaphore,
) -> None:
    """Fetch and store icons for item_ids not yet in wow_item_icons."""
    cached_ids = {
        row.item_id for row in db.query(WowItemIcon.item_id)
        .filter(WowItemIcon.item_id.in_(item_ids))
        .all()
    }
    missing = [iid for iid in item_ids if iid not in cached_ids]
    if not missing:
        return

    async def fetch_one(item_id: int) -> tuple[int, str | None]:
        async with sem:
            url = f"https://{_BLIZZARD_REGION}.api.blizzard.com/data/wow/media/item/{item_id}"
            resp = await client.get(
                url,
                params={"namespace": f"static-{_BLIZZARD_REGION}"},
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code != 200:
            return item_id, None
        for asset in resp.json().get("assets", []):
            if asset.get("key") == "icon":
                return item_id, asset["value"]
        return item_id, None

    results = await asyncio.gather(*[fetch_one(iid) for iid in missing], return_exceptions=True)
    saved = 0
    for r in results:
        if isinstance(r, Exception) or r[1] is None:
            continue
        item_id, icon_url = r
        db.merge(WowItemIcon(item_id=item_id, icon_url=icon_url))
        saved += 1
    if saved:
        db.commit()
    logger.info("Cached %d/%d boss loot icons", saved, len(missing))


async def run_scrape(specs: list[tuple[str, str]] | None = None, dry_run: bool = False) -> bool:
    """Run a full scrape. Returns True if all specs succeeded."""
    if specs is None:
        specs = SPECS

    if not dry_run:
        init_db()

    db = get_session() if not dry_run else None
    run = create_run(db) if db else None

    try:
        failed = 0
        sem = asyncio.Semaphore(CONCURRENT_SPECS)
        wowhead_sem = asyncio.Semaphore(1)  # one WoWhead guide fetch at a time
        async with (
            ArchonClient() as archon,
            httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0 (compatible; raidmetrics-scraper/1.0)"},
                follow_redirects=True,
            ) as wowhead,
        ):
            if db:
                try:
                    await _scrape_season_config(wowhead, db)
                except Exception as exc:
                    logger.error("Season config scrape failed: %s", exc)

            tasks = [
                asyncio.create_task(_scrape_spec(archon, wowhead, spec, cls, sem, wowhead_sem))
                for spec, cls in specs
            ]
            for coro in asyncio.as_completed(tasks):
                result = await coro
                if result is None:
                    failed += 1
                elif db and run:
                    save_spec(db, run, result)

        if db and run:
            finish_run(db, run, success=(failed == 0))
            prune_old_runs(db)

        logger.info(
            "Scrape complete — %d/%d specs OK%s",
            len(specs) - failed, len(specs),
            " (dry run)" if dry_run else "",
        )
        return failed == 0

    except Exception as exc:
        if db and run:
            finish_run(db, run, success=False, error=str(exc))
        raise
    finally:
        if db:
            db.close()
