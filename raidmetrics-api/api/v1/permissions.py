import json

from fastapi import HTTPException

from ..dal.models import User
from ..dal.redis import get_redis

# Test characters that bypass guild restrictions
BACKDOOR_NAMES = {"naughtybella", "naughtyclaus"}


async def _get_characters(current_user: User) -> list[dict]:
    redis = get_redis()
    cached = await redis.get(f"wow:characters:{current_user.id}")
    if not cached:
        raise HTTPException(
            status_code=403,
            detail="Character data not loaded. Visit the Characters page first.",
        )
    return json.loads(cached)


def _is_backdoor(characters: list[dict]) -> bool:
    return any(c.get("name", "").lower() in BACKDOOR_NAMES for c in characters)


async def assert_guild_member(guild_id: int, current_user: User) -> None:
    """Allow any authenticated member of the guild (or backdoor accounts)."""
    characters = await _get_characters(current_user)
    if _is_backdoor(characters):
        return
    if not any(c.get("guild_id") == guild_id for c in characters):
        raise HTTPException(
            status_code=403,
            detail="You must be a member of this guild to perform this action.",
        )


async def assert_guild_officer(guild_id: int, current_user: User) -> None:
    """Allow only GMs/Officers of the guild (or backdoor accounts)."""
    characters = await _get_characters(current_user)
    if _is_backdoor(characters):
        return
    authorized = any(
        c.get("guild_id") == guild_id and (c.get("is_gm") or c.get("is_officer"))
        for c in characters
    )
    if not authorized:
        raise HTTPException(
            status_code=403,
            detail="Only GMs and Officers of this guild can perform this action.",
        )


async def assert_any_officer(current_user: User) -> None:
    """Allow any user who is a GM/Officer of at least one guild (or backdoor accounts)."""
    characters = await _get_characters(current_user)
    if _is_backdoor(characters):
        return
    if not any(c.get("is_gm") or c.get("is_officer") for c in characters):
        raise HTTPException(
            status_code=403,
            detail="Only GMs and Officers can perform this action.",
        )
