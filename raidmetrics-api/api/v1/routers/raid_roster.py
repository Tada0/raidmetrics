import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...dal.db import get_db
from ...dal.models import RaidRoster, RaidRosterMember, User
from ...dal.redis import get_redis
from ..auth import get_current_user

DIFFICULTIES = {"normal", "heroic", "mythic"}

router = APIRouter()


class RosterMemberIn(BaseModel):
    character_name: str
    character_realm: str
    character_class: str | None = None
    sort_order: int = 0


class UpdateRosterRequest(BaseModel):
    members: list[RosterMemberIn]


def _roster_response(roster: RaidRoster) -> dict:
    return {
        "members": [
            {
                "character_name": m.character_name,
                "character_realm": m.character_realm,
                "character_class": m.character_class,
                "sort_order": m.sort_order,
            }
            for m in roster.members
        ]
    }


async def _assert_officer(user_id: int, guild_id: int) -> None:
    redis = get_redis()
    cached = await redis.get(f"wow:characters:{user_id}")
    if not cached:
        raise HTTPException(
            status_code=403,
            detail="Character data not loaded. Visit the Characters page first.",
        )
    characters = json.loads(cached)
    authorized = any(
        c.get("guild_id") == guild_id and (c.get("is_gm") or c.get("is_officer"))
        for c in characters
    )
    if not authorized:
        raise HTTPException(
            status_code=403,
            detail="You must be a GM or Officer of this guild to edit the roster.",
        )


@router.get("/{guild_id}/{difficulty}", tags=["Raid Roster"])
async def get_raid_roster(
    guild_id: int,
    difficulty: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if difficulty not in DIFFICULTIES:
        raise HTTPException(status_code=400, detail="Invalid difficulty")

    roster = (
        db.query(RaidRoster)
        .filter(RaidRoster.guild_id == guild_id, RaidRoster.difficulty == difficulty)
        .first()
    )
    if not roster:
        return {"members": []}
    return _roster_response(roster)


@router.put("/{guild_id}/{difficulty}", tags=["Raid Roster"])
async def update_raid_roster(
    guild_id: int,
    difficulty: str,
    body: UpdateRosterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if difficulty not in DIFFICULTIES:
        raise HTTPException(status_code=400, detail="Invalid difficulty")

    await _assert_officer(current_user.id, guild_id)

    roster = (
        db.query(RaidRoster)
        .filter(RaidRoster.guild_id == guild_id, RaidRoster.difficulty == difficulty)
        .first()
    )

    if roster is None:
        redis = get_redis()
        cached = await redis.get(f"wow:characters:{current_user.id}")
        guild_name = ""
        guild_realm_slug = ""
        if cached:
            for c in json.loads(cached):
                if c.get("guild_id") == guild_id:
                    guild_name = c.get("guild") or ""
                    guild_realm_slug = c.get("guild_realm_slug") or ""
                    break
        roster = RaidRoster(
            guild_id=guild_id,
            guild_name=guild_name,
            guild_realm_slug=guild_realm_slug,
            difficulty=difficulty,
        )
        db.add(roster)
        db.flush()
    else:
        db.query(RaidRosterMember).filter(
            RaidRosterMember.roster_id == roster.id
        ).delete()
        roster.updated_at = datetime.now(UTC)

    for i, member in enumerate(body.members):
        db.add(
            RaidRosterMember(
                roster_id=roster.id,
                character_name=member.character_name,
                character_realm=member.character_realm,
                character_class=member.character_class,
                sort_order=i,
            )
        )

    db.commit()
    db.refresh(roster)
    return _roster_response(roster)
