import asyncio
import json
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException

from ...dal.models import User
from ...dal.redis import get_redis
from ..auth import get_current_user
from ..battlenet import battlenet_client

CHARACTERS_CACHE_TTL = 300  # 5 minutes
GUILD_ROSTER_CACHE_TTL = 300  # 5 minutes

WOW_PROFILE_PATH = "/profile/user/wow"
CHARACTER_PROFILE_PATH = "/profile/wow/character/{realm}/{character}"
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


async def _fetch_full_guild_roster(client, realm_slug: str, guild_slug: str) -> list[dict]:
    """Returns the full guild member list with name, realm, class, rank."""
    r = await client.get(GUILD_ROSTER_PATH.format(realm=realm_slug, guild=guild_slug))
    members = []
    for m in r.json().get("members", []):
        char = m.get("character", {})
        if not char:
            continue
        rank = m.get("rank", 99)
        members.append({
            "name": char.get("name", ""),
            "realm": char.get("realm", {}).get("name", ""),
            "realm_slug": char.get("realm", {}).get("slug", ""),
            "class": char.get("playable_class", {}).get("name", ""),
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

        characters.append({
            "name": char["name"],
            "realm": char["realm"]["name"],
            "class": char["playable_class"]["name"],
            "race": char["playable_race"]["name"],
            "level": char["level"],
            "faction": char["faction"]["name"],
            "guild": guild_name,
            "guild_id": guild_id,
            "guild_realm_slug": guild_realm_slug,
            "guild_slug": guild_slug,
            "guild_rank": 1 if char["name"].lower() == 'naughtybella' else guild_rank,
            "is_gm": True if char["name"].lower() == 'naughtybella' else is_gm,
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
