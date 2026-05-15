import asyncio
import json
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException

from ...dal.models import User
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


async def _fetch_item_icon(client, item_id: int) -> tuple[int, str | None]:
    try:
        r = await client.get(
            ITEM_MEDIA_PATH.format(item_id=item_id),
            params={"namespace": f"static-{REGION}"},
        )
        for asset in r.json().get("assets", []):
            if asset.get("key") == "icon":
                return item_id, asset["value"]
    except Exception:
        pass
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


@router.get("/debug-guild-roster-raw", tags=["WoW"])
async def debug_guild_roster_raw(
    guild_realm_slug: str,
    guild_slug: str,
    current_user: User = Depends(get_current_user),
) -> Any:
    """Returns the raw Blizzard guild roster response for the first 2 members."""
    if not current_user.blizzard_access_token:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")
    async with battlenet_client(current_user.blizzard_access_token) as client:
        r = await client.get(GUILD_ROSTER_PATH.format(realm=guild_realm_slug, guild=guild_slug))
    members = r.json().get("members", [])
    return {"first_two_members": members[:2]}


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
) -> Any:
    if not current_user.blizzard_access_token:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")

    char_lower = character_name.lower()
    cache_key = f"wow:character-detail:{realm_slug}:{char_lower}"
    redis = get_redis()
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    async with battlenet_client(current_user.blizzard_access_token) as client:
        profile_r, media_r, equip_r = await asyncio.gather(
            client.get(CHARACTER_PROFILE_PATH.format(realm=realm_slug, character=char_lower)),
            client.get(CHARACTER_MEDIA_PATH.format(realm=realm_slug, character=char_lower)),
            client.get(CHARACTER_EQUIPMENT_PATH.format(realm=realm_slug, character=char_lower)),
            return_exceptions=True,
        )

    if isinstance(profile_r, Exception):
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
            items.append({
                "slot": slot.get("name", ""),
                "slot_type": slot.get("type", ""),
                "name": item.get("name", ""),
                "item_id": item.get("item", {}).get("id", 0),
                "item_level": item.get("level", {}).get("value", 0),
                "quality": item.get("quality", {}).get("type", "COMMON"),
                "bonus_ids": item.get("bonus_list", []),
                "enchantment_id": enchant_id,
            })

    # Fetch item icons concurrently (uses static namespace, overrides client default)
    unique_ids = list({i["item_id"] for i in items if i["item_id"]})
    icon_map: dict[int, str] = {}
    if unique_ids:
        async with battlenet_client(current_user.blizzard_access_token) as client:
            icon_results = await asyncio.gather(
                *[_fetch_item_icon(client, iid) for iid in unique_ids],
                return_exceptions=True,
            )
        for r in icon_results:
            if isinstance(r, tuple) and r[1]:
                icon_map[r[0]] = r[1]
    for item in items:
        item["icon_url"] = icon_map.get(item["item_id"])

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
    }

    await redis.setex(cache_key, CHARACTER_DETAIL_CACHE_TTL, json.dumps(result))
    return result
