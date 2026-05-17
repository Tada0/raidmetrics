from fastapi import HTTPException

from ..dal.db import SessionLocal
from ..dal.models import User, UserCharacter

BACKDOOR_NAMES = {"naughtybella", "naughtyclaus"}


def _get_characters(current_user: User) -> list[UserCharacter]:
    db = SessionLocal()
    try:
        return db.query(UserCharacter).filter(UserCharacter.user_id == current_user.id).all()
    finally:
        db.close()


def _is_backdoor(characters: list[UserCharacter]) -> bool:
    return any(c.character_name.lower() in BACKDOOR_NAMES for c in characters)


def assert_guild_member(guild_id: int, current_user: User) -> None:
    """Allow any authenticated member of the guild (or backdoor accounts)."""
    characters = _get_characters(current_user)
    if _is_backdoor(characters):
        return
    if not any(c.guild_id == guild_id for c in characters):
        raise HTTPException(
            status_code=403,
            detail="You must be a member of this guild to perform this action.",
        )


def assert_guild_officer(guild_id: int, current_user: User) -> None:
    """Allow only GMs/Officers of the guild (or backdoor accounts)."""
    characters = _get_characters(current_user)
    if _is_backdoor(characters):
        return
    authorized = any(
        c.guild_id == guild_id and (c.is_gm or c.is_officer)
        for c in characters
    )
    if not authorized:
        raise HTTPException(
            status_code=403,
            detail="Only GMs and Officers of this guild can perform this action.",
        )


def assert_any_officer(current_user: User) -> None:
    """Allow any user who is a GM/Officer of at least one guild (or backdoor accounts)."""
    characters = _get_characters(current_user)
    if _is_backdoor(characters):
        return
    if not any(c.is_gm or c.is_officer for c in characters):
        raise HTTPException(
            status_code=403,
            detail="Only GMs and Officers can perform this action.",
        )
