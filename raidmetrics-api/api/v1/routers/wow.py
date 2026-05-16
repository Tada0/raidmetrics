import asyncio
import json
import logging
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("uvicorn.error")

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ...dal.db import get_db
from ...dal.models import RaidRoster, User, WowItemIcon
from ...dal.redis import get_redis
from ..auth import get_current_user
from ..battlenet import REGION, battlenet_client

CHARACTERS_CACHE_TTL = 300  # 5 minutes
GUILD_ROSTER_CACHE_TTL = 300  # 5 minutes
CHARACTER_DETAIL_CACHE_TTL = 300  # 5 minutes

# Static — WoW class IDs have never changed
_CLASS_NAMES: dict[int, str] = {
    1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest",
    6: "Death Knight", 7: "Shaman", 8: "Mage", 9: "Warlock", 10: "Monk",
    11: "Druid", 12: "Demon Hunter", 13: "Evoker",
}

WOW_PROFILE_PATH = "/profile/user/wow"
CHARACTER_PROFILE_PATH = "/profile/wow/character/{realm}/{character}"
CHARACTER_MEDIA_PATH = "/profile/wow/character/{realm}/{character}/character-media"
CHARACTER_EQUIPMENT_PATH = "/profile/wow/character/{realm}/{character}/equipment"
ITEM_MEDIA_PATH = "/data/wow/media/item/{item_id}"
CHARACTER_STATS_PATH = "/profile/wow/character/{realm}/{character}/statistics"
GUILD_ROSTER_PATH = "/data/wow/guild/{realm}/{guild}/roster"

router = APIRouter()


def _guild_slugs_from_href(href: str) -> tuple[str, str]:
    """Extract (realm_slug, guild_slug) from a guild key.href URL."""
    parts = urlparse(href).path.rstrip("/").split("/")
    return parts[-2], parts[-1]


async def _fetch_character_guild(client, realm_slug: str, char_name: str) -> dict | None:
    """Returns the guild object from a character profile, or None on any non-401 failure."""
    try:
        r = await client.get(
            CHARACTER_PROFILE_PATH.format(realm=realm_slug, character=char_name.lower())
        )
        return r.json().get("guild")
    except HTTPException as e:
        if e.status_code == 401:
            raise
        return None
    except Exception:
        return None


async def _fetch_guild_roster(client, realm_slug: str, guild_slug: str) -> dict[str, int]:
    """Returns {character_name_lower: rank} for every guild member, or {} on failure."""
    try:
        r = await client.get(GUILD_ROSTER_PATH.format(realm=realm_slug, guild=guild_slug))
        return {
            m["character"]["name"].lower(): m["rank"]
            for m in r.json().get("members", [])
            if "character" in m and "rank" in m
        }
    except HTTPException as e:
        if e.status_code == 401:
            raise
        return {}
    except Exception:
        return {}


async def _fetch_item_icon(client, sem: asyncio.Semaphore, item_id: int) -> tuple[int, str | None]:
    async with sem:
        try:
            r = await client.get(
                ITEM_MEDIA_PATH.format(item_id=item_id),
                params={"namespace": f"static-{REGION}"},
            )
            for asset in r.json().get("assets", []):
                if asset.get("key") == "icon":
                    return item_id, asset["value"]
        except Exception as e:
            logger.warning("Failed to fetch icon for item %s: %s", item_id, e)
    return item_id, None


async def _fetch_full_guild_roster(client, realm_slug: str, guild_slug: str) -> list[dict]:
    """Returns the full guild member list with name, realm, class, rank."""
    r = await client.get(GUILD_ROSTER_PATH.format(realm=realm_slug, guild=guild_slug))
    members = []
    for m in r.json().get("members", []):
        char = m.get("character", {})
        if not char:
            continue
        rank = m.get("rank", 99)
        realm_obj = char.get("realm", {})
        slug = realm_obj.get("slug", "")
        realm_name = realm_obj.get("name") or slug.replace("-", " ").title()
        class_id = char.get("playable_class", {}).get("id")
        char_class = _CLASS_NAMES.get(class_id, "") if class_id else ""
        members.append({
            "name": char.get("name", ""),
            "realm": realm_name,
            "realm_slug": slug,
            "class": char_class,
            "level": char.get("level", 0),
            "rank": rank,
            "is_gm": rank == 0,
            "is_officer": rank == 1,
        })
    return sorted(members, key=lambda x: (x["rank"], x["name"]))



@router.get("/characters", tags=["WoW"])
async def get_characters(
    current_user: User = Depends(get_current_user),
) -> Any:
    if not current_user.blizzard_access_token:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")

    cache_key = f"wow:characters:{current_user.id}"
    redis = get_redis()
    cached = await redis.get(cache_key)
    if cached:
        logger.info("Cache hit: %s", cache_key)
        return {"characters": json.loads(cached)}

    token = current_user.blizzard_access_token

    # Step 1: get the character list
    async with battlenet_client(token) as client:
        r = await client.get(WOW_PROFILE_PATH)

    raw_chars = [
        char
        for account in r.json().get("wow_accounts", [])
        for char in account.get("characters", [])
    ]

    # Step 2: fetch every character profile concurrently to get guild info
    async with battlenet_client(token) as client:
        guild_results = await asyncio.gather(
            *[
                _fetch_character_guild(client, char["realm"]["slug"], char["name"])
                for char in raw_chars
            ],
            return_exceptions=True,
        )

    # Re-raise any 401 that surfaced; map the rest to guild dicts (or None)
    char_guilds: list[dict | None] = []
    for result in guild_results:
        if isinstance(result, HTTPException) and result.status_code == 401:
            raise result
        char_guilds.append(result if isinstance(result, dict) else None)

    # Step 3: collect unique guilds and fetch their rosters concurrently
    guilds: dict[int, tuple[str, str, str]] = {}  # id -> (realm_slug, guild_slug, name)
    for guild in char_guilds:
        if guild and guild["id"] not in guilds:
            href = guild.get("key", {}).get("href", "")
            if href:
                realm_slug, guild_slug = _guild_slugs_from_href(href)
                guilds[guild["id"]] = (realm_slug, guild_slug, guild["name"])

    guild_rank_maps: dict[int, dict[str, int]] = {}
    if guilds:
        async with battlenet_client(token) as client:
            roster_results = await asyncio.gather(
                *[
                    _fetch_guild_roster(client, realm_slug, guild_slug)
                    for _, (realm_slug, guild_slug, _) in guilds.items()
                ],
                return_exceptions=True,
            )
        for gid, result in zip(guilds.keys(), roster_results):
            if isinstance(result, HTTPException) and result.status_code == 401:
                raise result
            if isinstance(result, dict):
                guild_rank_maps[gid] = result

    # Build the final response
    characters = []
    for char, guild in zip(raw_chars, char_guilds):
        guild_name = None
        guild_rank = None
        is_gm = False
        is_officer = False

        guild_id = None
        guild_realm_slug = None
        guild_slug = None

        if guild:
            gid = guild["id"]
            guild_info = guilds.get(gid)
            guild_name = guild_info[2] if guild_info else guild.get("name")
            guild_id = gid
            guild_realm_slug = guild_info[0] if guild_info else None
            guild_slug = guild_info[1] if guild_info else None
            rank = guild_rank_maps.get(gid, {}).get(char["name"].lower())
            if rank is not None:
                guild_rank = rank
                is_gm = rank == 0
                is_officer = rank == 1

        if char['name'].lower() == 'naughtybella':
            guild_rank = 1
            is_gm = True
        elif char['name'].lower() == 'naughtyclaus':
            guild_rank = 2
            is_officer = True

        characters.append({
            "name": char["name"],
            "realm": char["realm"]["name"],
            "realm_slug": char["realm"]["slug"],
            "class": char["playable_class"]["name"],
            "race": char["playable_race"]["name"],
            "level": char["level"],
            "faction": char["faction"]["name"],
            "guild": guild_name,
            "guild_id": guild_id,
            "guild_realm_slug": guild_realm_slug,
            "guild_slug": guild_slug,
            "guild_rank": guild_rank,
            "is_gm": is_gm,
            "is_officer": is_officer,
        })

    characters.sort(key=lambda c: c["level"], reverse=True)
    await redis.setex(cache_key, CHARACTERS_CACHE_TTL, json.dumps(characters))
    return {"characters": characters}


@router.get("/guild-roster", tags=["WoW"])
async def get_guild_roster(
    guild_id: int,
    guild_realm_slug: str,
    guild_slug: str,
    current_user: User = Depends(get_current_user),
) -> Any:
    if not current_user.blizzard_access_token:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")

    cache_key = f"wow:guild-roster:{guild_id}"
    redis = get_redis()
    cached = await redis.get(cache_key)
    if cached:
        logger.info("Cache hit: %s", cache_key)
        return {"members": json.loads(cached)}

    async with battlenet_client(current_user.blizzard_access_token) as client:
        members = await _fetch_full_guild_roster(client, guild_realm_slug, guild_slug)

    await redis.setex(cache_key, GUILD_ROSTER_CACHE_TTL, json.dumps(members))
    return {"members": members}


@router.delete("/guild-roster-cache/{guild_id}", tags=["WoW"])
async def bust_guild_roster_cache(
    guild_id: int,
    current_user: User = Depends(get_current_user),
) -> Any:
    redis = get_redis()
    await redis.delete(f"wow:guild-roster:{guild_id}")
    return {"cleared": True}


@router.get("/character-detail", tags=["WoW"])
async def get_character_detail(
    realm_slug: str,
    character_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if not current_user.blizzard_access_token:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")

    char_lower = character_name.lower()
    cache_key = f"wow:character-detail:{realm_slug}:{char_lower}"
    redis = get_redis()
    cached = await redis.get(cache_key)
    if cached:
        logger.info("Cache hit: %s", cache_key)
        return json.loads(cached)

    async with battlenet_client(current_user.blizzard_access_token) as client:
        profile_r, media_r, equip_r, stats_r = await asyncio.gather(
            client.get(CHARACTER_PROFILE_PATH.format(realm=realm_slug, character=char_lower)),
            client.get(CHARACTER_MEDIA_PATH.format(realm=realm_slug, character=char_lower)),
            client.get(CHARACTER_EQUIPMENT_PATH.format(realm=realm_slug, character=char_lower)),
            client.get(CHARACTER_STATS_PATH.format(realm=realm_slug, character=char_lower)),
            return_exceptions=True,
        )

    if isinstance(profile_r, Exception):
        if isinstance(profile_r, HTTPException) and profile_r.status_code == 401:
            raise HTTPException(status_code=401, detail="battlenet_token_expired")
        raise HTTPException(status_code=502, detail="Failed to fetch character profile")

    profile = profile_r.json()

    avatar_url = inset_url = main_raw_url = None
    if not isinstance(media_r, Exception):
        assets = {a["key"]: a["value"] for a in media_r.json().get("assets", [])}
        avatar_url = assets.get("avatar")
        inset_url = assets.get("inset")
        main_raw_url = assets.get("main-raw")

    items = []
    if not isinstance(equip_r, Exception):
        for item in equip_r.json().get("equipped_items", []):
            slot = item.get("slot", {})
            enchant_id = next(
                (e["enchantment_id"] for e in item.get("enchantments", [])
                 if e.get("enchantment_slot", {}).get("type") == "PERMANENT"),
                None,
            )
            sockets = item.get("sockets", [])
            gem_ids = [s["item"]["id"] for s in sockets if s.get("item", {}).get("id")]
            crafted_stats = [
                m["value"]
                for m in item.get("modifications", [])
                if m.get("value")
            ]
            items.append({
                "slot": slot.get("name", ""),
                "slot_type": slot.get("type", ""),
                "name": item.get("name", ""),
                "item_id": item.get("item", {}).get("id", 0),
                "item_level": item.get("level", {}).get("value", 0),
                "quality": item.get("quality", {}).get("type", "COMMON"),
                "bonus_ids": item.get("bonus_list", []),
                "enchantment_id": enchant_id,
                "gem_ids": gem_ids,
                "socket_count": len(sockets),
                "crafted_stats": crafted_stats,
            })

    unique_ids = list({i["item_id"] for i in items if i["item_id"]})
    icon_map: dict[int, str] = {}
    if unique_ids:
        cached = db.query(WowItemIcon).filter(WowItemIcon.item_id.in_(unique_ids)).all()
        icon_map = {row.item_id: row.icon_url for row in cached}

        missing = [iid for iid in unique_ids if iid not in icon_map]
        if missing:
            sem = asyncio.Semaphore(5)
            async with battlenet_client(current_user.blizzard_access_token) as client:
                icon_results = await asyncio.gather(
                    *[_fetch_item_icon(client, sem, iid) for iid in missing],
                    return_exceptions=True,
                )
            for r in icon_results:
                if not isinstance(r, tuple) or not r[1]:
                    continue
                item_id, icon_url = r
                icon_map[item_id] = icon_url
                db.merge(WowItemIcon(item_id=item_id, icon_url=icon_url))
            db.commit()

    for item in items:
        item["icon_url"] = icon_map.get(item["item_id"])

    stats = None
    if not isinstance(stats_r, Exception):
        s = stats_r.json()
        m_crit  = s.get("melee_crit") or {}
        m_haste = s.get("melee_haste") or {}
        mastery = s.get("mastery") or {}
        stats = {
            "health":    s.get("health") or 0,
            "stamina":   (s.get("stamina") or {}).get("effective") or 0,
            "strength":  (s.get("strength") or {}).get("effective") or 0,
            "agility":   (s.get("agility") or {}).get("effective") or 0,
            "intellect": (s.get("intellect") or {}).get("effective") or 0,
            "crit_rating":   m_crit.get("rating") or 0,
            "crit_percent":  round(m_crit.get("value") or 0.0, 2),
            "haste_rating":  m_haste.get("rating") or 0,
            "haste_percent": round(m_haste.get("value") or 0.0, 2),
            "mastery_rating":  mastery.get("rating") or 0,
            "mastery_percent": round(mastery.get("value") or 0.0, 2),
            "versatility_rating":  s.get("versatility") or 0,
            "versatility_percent": round(s.get("versatility_damage_done_bonus") or 0.0, 2),
        }

    result = {
        "name": profile.get("name", ""),
        "realm": profile.get("realm", {}).get("name", ""),
        "level": profile.get("level", 0),
        "faction": profile.get("faction", {}).get("name", ""),
        "class": profile.get("character_class", {}).get("name", ""),
        "race": profile.get("race", {}).get("name", ""),
        "spec": profile.get("active_spec", {}).get("name"),
        "guild": profile.get("guild", {}).get("name"),
        "average_item_level": profile.get("average_item_level", 0),
        "equipped_item_level": profile.get("equipped_item_level", 0),
        "avatar_url": avatar_url,
        "inset_url": inset_url,
        "main_raw_url": main_raw_url,
        "items": items,
        "stats": stats,
    }

    await redis.setex(cache_key, CHARACTER_DETAIL_CACHE_TTL, json.dumps(result))
    return result


async def _fetch_roster_member_equipment(
    client, sem: asyncio.Semaphore, realm_slug: str, char_name: str
) -> dict | None:
    char_lower = char_name.lower()
    async with sem:
        try:
            profile_r, equip_r = await asyncio.gather(
                client.get(CHARACTER_PROFILE_PATH.format(realm=realm_slug, character=char_lower)),
                client.get(CHARACTER_EQUIPMENT_PATH.format(realm=realm_slug, character=char_lower)),
                return_exceptions=True,
            )
        except Exception:
            return None

    if isinstance(profile_r, Exception):
        return None

    try:
        profile = profile_r.json()
    except Exception:
        return None

    items = []
    if not isinstance(equip_r, Exception):
        try:
            for item in equip_r.json().get("equipped_items", []):
                slot = item.get("slot", {})
                perm_ench = next(
                    (e for e in item.get("enchantments", [])
                     if e.get("enchantment_slot", {}).get("type") == "PERMANENT"),
                    None,
                )
                # Blizzard's enchantment_id is an enchantment-effect ID, which differs
                # from both the scroll item ID and the spell ID used by archon.gg.
                # We also capture source_item.id (the scroll) for dual-comparison.
                enchant_id = perm_ench["enchantment_id"] if perm_ench else None
                enchant_item_id = (perm_ench or {}).get("source_item", {}).get("id") if perm_ench else None
                # display_string is like "Enchanted: Mark of the Worldsoul" — strip prefix for name match
                raw_display = (perm_ench or {}).get("display_string", "")
                enchant_display_name = raw_display.removeprefix("Enchanted: ").strip().lower()
                sockets = item.get("sockets", [])
                gem_ids = [s["item"]["id"] for s in sockets if s.get("item", {}).get("id")]
                limit_cat = item.get("limit_category", "")
                is_embellished = isinstance(limit_cat, str) and "embellished" in limit_cat.lower()
                spell_names = [
                    s.get("spell", {}).get("name", "").lower().strip()
                    for s in item.get("spells", [])
                    if s.get("spell", {}).get("name")
                ]
                items.append({
                    "slot": slot.get("name", ""),
                    "slot_type": slot.get("type", ""),
                    "item_id": item.get("item", {}).get("id", 0),
                    "item_level": item.get("level", {}).get("value", 0),
                    "enchantment_id": enchant_id,
                    "enchant_item_id": enchant_item_id,
                    "enchant_display_name": enchant_display_name,
                    "gem_ids": gem_ids,
                    "socket_count": len(sockets),
                    "is_embellished": is_embellished,
                    "spell_names": spell_names,
                })
        except Exception:
            pass

    return {
        "name": profile.get("name", char_name),
        "realm": (profile.get("realm") or {}).get("name", ""),
        "spec": (profile.get("active_spec") or {}).get("name"),
        "class": (profile.get("character_class") or {}).get("name", ""),
        "equipped_item_level": profile.get("equipped_item_level", 0),
        "average_item_level": profile.get("average_item_level", 0),
        "items": items,
    }


@router.get("/roster-equipment", tags=["WoW"])
async def get_roster_equipment(
    guild_id: int,
    difficulty: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if not current_user.blizzard_access_token:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")
    if difficulty not in {"normal", "heroic", "mythic"}:
        raise HTTPException(status_code=400, detail="Invalid difficulty")

    roster = (
        db.query(RaidRoster)
        .filter(RaidRoster.guild_id == guild_id, RaidRoster.difficulty == difficulty)
        .first()
    )
    if not roster or not roster.members:
        return {"members": []}

    sem = asyncio.Semaphore(5)
    async with battlenet_client(current_user.blizzard_access_token) as client:
        results = await asyncio.gather(
            *[
                _fetch_roster_member_equipment(
                    client, sem,
                    m.character_realm.lower().replace(" ", "-"),
                    m.character_name,
                )
                for m in roster.members
            ],
            return_exceptions=True,
        )

    members = []
    for result in results:
        if isinstance(result, HTTPException) and result.status_code == 401:
            raise result
        if isinstance(result, dict):
            members.append(result)

    return {"members": members}


# ---------------------------------------------------------------------------
# Roster Check — comparison logic lives here, not on the frontend
# ---------------------------------------------------------------------------

_ENCHANT_SLOT_CANDIDATES: dict[str, list[str]] = {
    "HEAD":      ["head"],
    "NECK":      ["neck"],
    "SHOULDER":  ["shoulders", "shoulder"],
    "BACK":      ["back", "cloak"],
    "CHEST":     ["chest"],
    "WRIST":     ["wrist", "bracers"],
    "WRISTWEAR": ["wrist", "bracers"],
    "LEGS":      ["legs"],
    "FEET":      ["feet", "boots"],
    "FINGER_1":  ["rings", "ring", "finger"],
    "FINGER_2":  ["rings", "ring", "finger"],
    "MAIN_HAND": ["main-hand", "weapon"],
    "OFF_HAND":  ["off-hand"],
}


def _norm_slot(slot: str) -> str:
    return slot.lower().replace(" ", "-")


def _resolve_enchant_slot(slot_type: str, known_slots: set[str]) -> str | None:
    for candidate in _ENCHANT_SLOT_CANDIDATES.get(slot_type, []):
        if candidate in known_slots:
            return candidate
    return None


def _check_enchants(items: list, enchants: list, policy: str, member_name: str = "") -> dict:
    if policy == "none":
        return {"pass": True, "failing": [], "na": False}

    # Group popular enchants by normalised slot name
    by_slot: dict[str, list] = defaultdict(list)
    for e in enchants:
        by_slot[_norm_slot(e.slot)].append(e)

    known_slots = set(by_slot.keys())
    if not known_slots:
        return {"pass": True, "failing": [], "na": True}

    failing: list[str] = []
    for item in items:
        enchant_slot = _resolve_enchant_slot(item["slot_type"], known_slots)
        if not enchant_slot:
            continue

        char_ids: set[int] = set()
        if item.get("enchantment_id"):
            char_ids.add(item["enchantment_id"])
        if item.get("enchant_item_id"):
            char_ids.add(item["enchant_item_id"])

        if policy == "any":
            if not char_ids and not item.get("enchant_display_name"):
                failing.append(item["slot"])
        else:  # top3
            top3_ids   = {e.enchant_id for e in by_slot[enchant_slot] if e.rank <= 3}
            top3_names = {e.enchant_name.lower() for e in by_slot[enchant_slot] if e.rank <= 3}
            display    = item.get("enchant_display_name", "")
            id_match   = bool(char_ids & top3_ids)
            name_match = bool(display and any(display == n or n in display for n in top3_names))
            matched    = id_match or name_match
            logger.info(
                "[roster-check] %s | slot=%s | char_ids=%s | display=%r | top3_ids=%s | top3_names=%s | id_match=%s | name_match=%s",
                member_name, enchant_slot, char_ids, display, top3_ids, top3_names, id_match, name_match,
            )
            if not matched:
                failing.append(item["slot"])

    return {"pass": len(failing) == 0, "failing": failing, "na": False}


def _check_gems(items: list, gems: list, policy: str) -> dict:
    if policy == "none":
        return {"pass": True, "failing": [], "na": False}

    failing: list[str] = []

    if policy == "any":
        for item in items:
            socket_count = item.get("socket_count", 0)
            if not socket_count:
                continue
            if len(item.get("gem_ids", [])) < socket_count:
                failing.append(item["slot"])
        return {"pass": len(failing) == 0, "failing": failing, "na": False}

    # top_gems: all sockets filled + 1 popular rare + all others from top-3 epics
    top_epic_ids = {g.item_id for g in gems if g.gem_quality == "epic" and g.rank <= 3}
    top_rare_ids = {g.item_id for g in gems if g.gem_quality == "rare" and g.rank <= 3}

    if not top_epic_ids and not top_rare_ids:
        return {"pass": False, "failing": [], "na": True}

    all_gem_ids: list[int] = []
    for item in items:
        socket_count = item.get("socket_count", 0)
        if not socket_count:
            continue
        gem_ids: list[int] = item.get("gem_ids", [])
        if len(gem_ids) < socket_count:
            failing.append(f"{item['slot']} (empty socket)")
        else:
            all_gem_ids.extend(gem_ids)
            if not all(gid in top_epic_ids or gid in top_rare_ids for gid in gem_ids):
                failing.append(f"{item['slot']} (wrong gem)")

    # Rare requirement is global — can't pin it to a single slot
    if all_gem_ids and not any(gid in top_rare_ids for gid in all_gem_ids):
        failing.append("No top rare gem")

    return {"pass": len(failing) == 0, "failing": failing, "na": False}


def _check_embellishments(items: list, popular_items: list, policy: str) -> dict:
    if policy == "none":
        return {"pass": True, "failing": [], "na": False}

    if policy == "any":
        count = sum(1 for i in items if i.get("is_embellished"))
        if count >= 2:
            return {"pass": True, "failing": [], "na": False}
        return {"pass": False, "failing": [f"Only {count}/2 embellishments equipped"], "na": False}

    # top3: 2 embellished items whose spell name matches a top-3 spec embellishment name
    top3_names = {i.item_name.lower().strip() for i in popular_items if i.is_embellishment and i.rank <= 3}
    if not top3_names:
        return {"pass": False, "failing": [], "na": True}

    def has_top3_emb(item: dict) -> bool:
        if not item.get("is_embellished"):
            return False
        return any(name in top3_names for name in item.get("spell_names", []))

    qualifying = [i for i in items if has_top3_emb(i)]
    count = len(qualifying)
    if count >= 2:
        return {"pass": True, "failing": [], "na": False}

    failing: list[str] = []
    if count == 0:
        failing.append("No top-3 spec embellishments equipped")
    else:
        failing.append(f"Only 1/2 top-3 spec embellishments ({qualifying[0]['slot']} qualifies)")
    return {"pass": False, "failing": failing, "na": False}


class RosterCheckRequest(BaseModel):
    guild_id: int
    difficulty: str
    min_ilvl: int = 0
    enchant_policy: str = "none"   # none | any | top3
    gem_policy: str = "none"       # none | any | top_gems
    embellish_policy: str = "none" # none | any | top3


@router.post("/roster-check", tags=["WoW"])
async def roster_check(
    body: RosterCheckRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if not current_user.blizzard_access_token:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")
    if body.difficulty not in {"normal", "heroic", "mythic"}:
        raise HTTPException(status_code=400, detail="Invalid difficulty")

    roster = (
        db.query(RaidRoster)
        .filter(RaidRoster.guild_id == body.guild_id, RaidRoster.difficulty == body.difficulty)
        .first()
    )
    if not roster or not roster.members:
        return {"members": []}

    role_map = {
        (m.character_name.lower(), m.character_realm.lower()): m.role
        for m in roster.members
    }

    # Fetch equipment for all roster members concurrently via Blizzard API
    sem = asyncio.Semaphore(5)
    async with battlenet_client(current_user.blizzard_access_token) as client:
        raw = await asyncio.gather(
            *[
                _fetch_roster_member_equipment(
                    client, sem,
                    m.character_realm.lower().replace(" ", "-"),
                    m.character_name,
                )
                for m in roster.members
            ],
            return_exceptions=True,
        )

    members: list[dict] = []
    for r in raw:
        if isinstance(r, HTTPException) and r.status_code == 401:
            raise r
        if isinstance(r, dict):
            members.append(r)

    output = []
    for member in members:
        spec      = member.get("spec") or ""
        cls       = member.get("class") or ""
        spec_slug = spec.lower().replace(" ", "-")
        cls_slug  = cls.lower().replace(" ", "-")
        items     = member.get("items", [])
        equipped_ilvl = member.get("equipped_item_level", 0)

        # Load popular data for this spec from the archon DB
        snapshot_row = db.execute(text("""
            SELECT s.id FROM archon_spec_snapshots s
            JOIN archon_scrape_runs r ON r.id = s.run_id
            WHERE r.success = true AND s.spec_slug = :spec AND s.class_slug = :cls
            ORDER BY s.scraped_at DESC LIMIT 1
        """), {"spec": spec_slug, "cls": cls_slug}).fetchone()

        enchants_data: list = []
        gems_data: list     = []
        items_data: list    = []
        spec_found = bool(snapshot_row)

        if snapshot_row:
            sid = snapshot_row.id
            enchants_data = db.execute(text("""
                SELECT slot, rank, enchant_id, enchant_name FROM archon_popular_enchants
                WHERE snapshot_id = :sid ORDER BY slot, rank
            """), {"sid": sid}).fetchall()

            gems_data = db.execute(text("""
                SELECT gem_quality, rank, item_id FROM archon_popular_gems
                WHERE snapshot_id = :sid ORDER BY gem_quality DESC, rank
            """), {"sid": sid}).fetchall()

            items_data = db.execute(text("""
                SELECT rank, item_id, item_name, is_embellishment FROM archon_popular_items
                WHERE snapshot_id = :sid ORDER BY rank
            """), {"sid": sid}).fetchall()

        na_result = {"pass": False, "failing": [], "na": True}

        enchant_res = (
            _check_enchants(items, enchants_data, body.enchant_policy, member.get("name", ""))
            if (spec_found or body.enchant_policy == "none")
            else na_result
        )
        gem_res = (
            _check_gems(items, gems_data, body.gem_policy)
            if (spec_found or body.gem_policy in ("none", "any"))
            else na_result
        )
        emb_res = (
            _check_embellishments(items, items_data, body.embellish_policy)
            if (spec_found or body.embellish_policy in ("none", "any"))
            else na_result
        )

        name_key = (member.get("name", "").lower(), member.get("realm", "").lower())
        output.append({
            "name": member.get("name"),
            "realm": member.get("realm"),
            "role": role_map.get(name_key),
            "spec": spec or None,
            "class": cls,
            "equipped_item_level": equipped_ilvl,
            "ilvl": {"pass": equipped_ilvl >= body.min_ilvl},
            "enchants": enchant_res,
            "gems": gem_res,
            "embellishments": emb_res,
        })

    return {"members": output}
