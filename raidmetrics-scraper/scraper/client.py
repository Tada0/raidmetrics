import asyncio
import json
import logging
import re

import httpx

from .config import ARCHON_BASE

logger = logging.getLogger(__name__)

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


class ArchonClient:
    """Async HTTP client for Archon.gg Next.js JSON endpoints."""

    def __init__(self):
        self._build_id: str | None = None
        self._build_id_lock: asyncio.Lock | None = None
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ArchonClient":
        self._build_id_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            base_url=ARCHON_BASE,
            headers={"User-Agent": "Mozilla/5.0 (compatible; raidmetrics-scraper/1.0)"},
            follow_redirects=True,
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def _resolve_build_id(self) -> str:
        async with self._build_id_lock:
            if self._build_id:
                return self._build_id
            logger.info("Fetching Archon build ID")
            r = await self._client.get("/")
            r.raise_for_status()
            m = _NEXT_DATA_RE.search(r.text)
            if not m:
                raise RuntimeError("__NEXT_DATA__ script tag not found on Archon homepage")
            self._build_id = json.loads(m.group(1))["buildId"]
            logger.info("Build ID: %s", self._build_id)
            return self._build_id

    async def fetch_page(
        self,
        spec_slug: str,
        class_slug: str,
        page: str,
        zone_type: str = "raid",
        difficulty: str = "mythic",
        encounter: str = "all-bosses",
    ) -> dict:
        build_id = await self._resolve_build_id()
        path = (
            f"/_next/data/{build_id}/wow/builds/{spec_slug}/{class_slug}"
            f"/{zone_type}/{page}/{difficulty}/{encounter}.json"
        )
        params = {
            "gameSlug": "wow",
            "specSlug": spec_slug,
            "classSlug": class_slug,
            "zoneTypeSlug": zone_type,
            "categorySlug": page,
            "difficultySlug": difficulty,
            "encounterSlug": encounter,
        }
        logger.debug("GET %s", path)
        r = await self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()
