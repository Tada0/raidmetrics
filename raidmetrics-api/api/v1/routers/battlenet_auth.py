from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from typing import Literal
import uuid
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from httpx import AsyncClient, HTTPError, TransportError
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...dal.db import get_db
from ...dal.models import RefreshToken, User
from ..auth import (REFRESH_TOKEN_EXPIRES_DAYS, create_access_token,
                    generate_refresh_token, hash_token, set_refresh_cookie)


BLIZZARD_CLIENT_ID = os.getenv("BLIZZARD_CLIENT_ID", "")
BLIZZARD_CLIENT_SECRET = os.getenv("BLIZZARD_CLIENT_SECRET", "")
BLIZZARD_REDIRECT_URI = os.getenv("BLIZZARD_REDIRECT_URI")
BLIZZARD_TOKEN_URL = "https://oauth.battle.net/token"
BLIZZARD_USERINFO_URL = "https://oauth.battle.net/userinfo"


class BattlenetLoginRedirectUrlResponse(BaseModel):
    state: str
    url: str


class BattlenetCallbackRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_at: datetime


router = APIRouter()


@router.get("/login_redirect_url", response_model=BattlenetLoginRedirectUrlResponse, tags=["Battlenet"])
async def login_redirect_url():
    state = uuid.uuid4().hex

    query = urlencode({
        "response_type": "code",
        "scope": "wow.profile",
        "state": state,
        "redirect_uri": BLIZZARD_REDIRECT_URI,
        "client_id": BLIZZARD_CLIENT_ID,
    })

    return BattlenetLoginRedirectUrlResponse(
        state=state,
        url=f"https://oauth.battle.net/authorize?{query}"
    )


@router.post("/callback", response_model=TokenResponse, tags=["Battlenet"])
async def callback(
    payload: BattlenetCallbackRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        async with AsyncClient() as client:
            token_r = await client.post(
                BLIZZARD_TOKEN_URL,
                auth=(BLIZZARD_CLIENT_ID, BLIZZARD_CLIENT_SECRET),
                data={
                    "grant_type": "authorization_code",
                    "code": payload.code,
                    "redirect_uri": BLIZZARD_REDIRECT_URI,
                },
            )
            token_r.raise_for_status()
            blizzard_token = token_r.json()["access_token"]

            userinfo_r = await client.get(
                BLIZZARD_USERINFO_URL,
                headers={"Authorization": f"Bearer {blizzard_token}"},
            )
            userinfo_r.raise_for_status()
            userinfo = userinfo_r.json()
    except (HTTPError, TransportError):
        raise HTTPException(status_code=502, detail="Battlenet auth service unavailable")

    blizzard_sub = str(userinfo["sub"])
    battletag = userinfo.get("battletag")

    user = db.query(User).filter(User.blizzard_sub == blizzard_sub).first()
    if not user:
        user = User(blizzard_sub=blizzard_sub, name=battletag, blizzard_access_token=blizzard_token)
        db.add(user)
    else:
        user.blizzard_access_token = blizzard_token
    db.commit()
    db.refresh(user)

    access_token, access_exp = create_access_token(user.id)

    raw_refresh = generate_refresh_token()
    hashed = hash_token(raw_refresh)
    expires_at = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRES_DAYS)
    token_row = RefreshToken(
        user_id=user.id,
        token_hash=hashed,
        expires_at=expires_at,
        user_agent=request.headers.get("User-Agent"),
        ip=request.client.host if request.client else None,
    )
    db.add(token_row)
    db.commit()

    max_age = REFRESH_TOKEN_EXPIRES_DAYS * 24 * 60 * 60
    set_refresh_cookie(response, raw_refresh, max_age)

    return TokenResponse(
        access_token=access_token, token_type="bearer", expires_at=access_exp
    )
