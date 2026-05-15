from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ...dal.db import get_db
from ...dal.models import RefreshToken
from ..auth import (REFRESH_TOKEN_EXPIRES_DAYS, clear_refresh_cookie,
                    create_access_token, generate_refresh_token, hash_token,
                    set_refresh_cookie)
from .battlenet_auth import TokenResponse

router = APIRouter()


@router.post("/refresh", response_model=TokenResponse, tags=["Session"])
def refresh_token(
    request: Request,
    response: Response,
    refresh_token: str = Cookie(None),
    db: Session = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    hashed = hash_token(refresh_token)
    token_row = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == hashed,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > datetime.now(UTC),
        )
        .with_for_update()
        .first()
    )
    if not token_row:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    raw_new_refresh = generate_refresh_token()
    new_hashed = hash_token(raw_new_refresh)
    expires_at = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRES_DAYS)

    with db.begin_nested():
        token_row.revoked = True
        new_token_row = RefreshToken(
            user_id=token_row.user_id,
            token_hash=new_hashed,
            expires_at=expires_at,
            user_agent=request.headers.get("User-Agent"),
            ip=request.client.host if request.client else None,
        )
        db.add(new_token_row)
        db.flush()
        token_row.replaced_by = new_token_row.id

    db.commit()
    db.refresh(new_token_row)

    access_token, access_exp = create_access_token(token_row.user_id)

    max_age = REFRESH_TOKEN_EXPIRES_DAYS * 24 * 60 * 60
    set_refresh_cookie(response, raw_new_refresh, max_age)

    return TokenResponse(
        access_token=access_token, token_type="bearer", expires_at=access_exp
    )


@router.post("/logout", tags=["Session"])
def logout(
    response: Response,
    refresh_token: str = Cookie(None),
    db: Session = Depends(get_db),
):
    if refresh_token:
        hashed = hash_token(refresh_token)
        token_row = db.query(RefreshToken).filter(RefreshToken.token_hash == hashed).first()
        if token_row:
            token_row.revoked = True
            db.commit()

    clear_refresh_cookie(response)
    return {"msg": "Logged out"}
