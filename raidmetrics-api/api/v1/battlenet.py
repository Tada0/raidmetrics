"""Shared client for calling Blizzard APIs with a user access token."""
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import HTTPException
from httpx import HTTPError, TransportError

REGION = os.getenv("BLIZZARD_REGION", "eu")
NAMESPACE = f"profile-{REGION}"
BASE_URL = f"https://{REGION}.api.blizzard.com"


async def _on_response(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="battlenet_token_expired")


@asynccontextmanager
async def battlenet_client(token: str, timeout: float = 10.0):
    """Yields an httpx.AsyncClient pre-configured for Blizzard API calls.

    Automatically raises:
      - HTTPException 401 "battlenet_token_expired" on any 401 response
      - HTTPException 502 on network/transport errors
    """
    try:
        async with httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
            params={"namespace": NAMESPACE, "locale": "en_US"},
            event_hooks={"response": [_on_response]},
        ) as client:
            yield client
    except (HTTPError, TransportError):
        raise HTTPException(status_code=502, detail="Blizzard API unavailable")
