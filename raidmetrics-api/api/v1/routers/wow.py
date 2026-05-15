import asyncio
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException

from ...dal.models import User
from ..auth import get_current_user
from ..battlenet import battlenet_client

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


@router.get("/characters", tags=["WoW"])
async def get_characters(
    current_user: User = Depends(get_current_user),
) -> Any:
    if not current_user.blizzard_access_token:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")

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

        if guild:
            gid = guild["id"]
            guild_name = guilds.get(gid, (None, None, guild.get("name")))[2]
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
            "guild_rank": guild_rank,
            "is_gm": is_gm,
            "is_officer": is_officer,
        })

    characters.sort(key=lambda c: c["level"], reverse=True)
    return {"characters": characters}
