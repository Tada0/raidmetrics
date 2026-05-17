import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ...dal.models import User
from ..auth import get_current_user
from ..permissions import assert_any_officer

SCRAPER_URL = os.getenv("SCRAPER_URL", "http://scraper:8001")

router = APIRouter()


async def _scraper_get(path: str) -> Any:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{SCRAPER_URL}{path}")
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="scraper_unavailable")


async def _scraper_post(path: str) -> Any:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{SCRAPER_URL}{path}")
            if r.status_code == 409:
                raise HTTPException(status_code=409, detail="scrape_already_running")
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="scraper_unavailable")


@router.get("/status", tags=["Scraper"])
async def scrape_status(current_user: User = Depends(get_current_user)) -> Any:
    return await _scraper_get("/status")


@router.post("/trigger", tags=["Scraper"])
async def trigger_scrape(current_user: User = Depends(get_current_user)) -> Any:
    assert_any_officer(current_user)
    return await _scraper_post("/trigger")
