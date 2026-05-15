import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from httpx import HTTPError, TransportError
from sqlalchemy.orm import Session

from ...dal.db import get_db
from ...dal.models import User
from ..auth import get_current_user

BLIZZARD_REGION = os.getenv("BLIZZARD_REGION", "eu")
WOW_PROFILE_URL = f"https://{BLIZZARD_REGION}.api.blizzard.com/profile/user/wow"
WOW_NAMESPACE = f"profile-{BLIZZARD_REGION}"

router = APIRouter()


@router.get("/characters", tags=["WoW"])
async def get_characters(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if not current_user.blizzard_access_token:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                WOW_PROFILE_URL,
                params={"namespace": WOW_NAMESPACE, "locale": "en_US"},
                headers={"Authorization": f"Bearer {current_user.blizzard_access_token}"},
            )
    except (HTTPError, TransportError):
        raise HTTPException(status_code=502, detail="Blizzard WoW API unavailable")

    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")

    r.raise_for_status()

    wow_accounts = r.json().get("wow_accounts", [])
    characters = [
        {
            "name": char["name"],
            "realm": char["realm"]["name"],
            "class": char["playable_class"]["name"],
            "race": char["playable_race"]["name"],
            "level": char["level"],
            "faction": char["faction"]["name"],
        }
        for account in wow_accounts
        for char in account.get("characters", [])
    ]
    characters.sort(key=lambda c: c["level"], reverse=True)
    return {"characters": characters}
