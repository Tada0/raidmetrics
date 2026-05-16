"""Scrape WoWhead BiS gear guides for each spec."""
import asyncio
import json
import logging
import re

import httpx

from . import WowheadBisItem

logger = logging.getLogger(__name__)

WOWHEAD_BASE = "https://www.wowhead.com"
NETHER_BASE = "https://nether.wowhead.com"

_TABLE_HEADER_RE = re.compile(
    r'\[td background=\w+\]\[b\](?:Item )?Slot\[/b\]\[/td\]'
)
_TR_RE = re.compile(r'\[tr\](.*?)\[/tr\]', re.DOTALL)
# Allow optional attributes on [td] (e.g. rowspan=2) and optional [b] bold wrapping
_FIRST_TD_RE = re.compile(r'\[td(?:\s[^\]]+)?\](?:\[b\])?\s*([A-Za-z0-9 \-()]{2,40}?)\s*(?:\[/b\])?\[/td\]')
_ROWSPAN_RE = re.compile(r'\[td\s+rowspan=(\d+)\]')
_ITEM_IN_ROW_RE = re.compile(r'\[item=(\d+)')
_GATHERER_RE = re.compile(
    r'WH\.Gatherer\.addData\(3, 1, (\{.*?\})\);',
    re.DOTALL,
)

_SLOT_NORMALIZE: dict[str, str] = {
    'helm': 'head',
    'cloak': 'back',
    'cape': 'back',
    'bracers': 'wrist',
    'gloves': 'hands',
    'belt': 'waist',
    'boots': 'feet',
    'finger': 'ring',
    'weapon': 'main-hand',
    'weapon (2h)': 'two-hand',
    'weapon (1h)': 'main-hand',
    '1h weapon': 'main-hand',
    '2h weapon': 'two-hand',
    'mainhand': 'main-hand',
    'main hand': 'main-hand',
    'one-hand': 'main-hand',
    'one hand': 'main-hand',
    'offhand': 'off-hand',
    'off hand': 'off-hand',
    'shield': 'off-hand',
}

# Canonical slot names that need no further mapping
_CANONICAL_SLOTS = {
    'head', 'neck', 'shoulder', 'shoulders', 'back',
    'chest', 'wrist', 'wrists', 'hands', 'waist', 'legs', 'feet',
    'ring', 'trinket',
    'main-hand', 'off-hand', 'two-hand', 'ranged',
}

_SLOT_STRIP_RE = re.compile(r'\s*\([^)]*\)|\s+\d+\s*$')


def _to_canonical_slot(raw: str) -> str | None:
    """Map a raw WoWhead slot label to a canonical slot name, or None if unrecognized.

    Handles qualifiers like 'Trinket (Damage)', numbered variants like 'Ring 1',
    and plurals like 'Weapons (1h)'.
    """
    s = raw.strip().lower()
    # Fast path: exact match
    if s in _SLOT_NORMALIZE:
        return _SLOT_NORMALIZE[s]
    if s in _CANONICAL_SLOTS:
        return s
    # Strip parenthetical qualifier and trailing number, then retry
    s_clean = _SLOT_STRIP_RE.sub('', s).strip()
    if s_clean != s:
        if s_clean in _SLOT_NORMALIZE:
            return _SLOT_NORMALIZE[s_clean]
        if s_clean in _CANONICAL_SLOTS:
            return s_clean
    # Try singular form (weapons → weapon, rings → ring, trinkets → trinket)
    if s_clean.endswith('s'):
        s_singular = s_clean[:-1]
        if s_singular in _SLOT_NORMALIZE:
            return _SLOT_NORMALIZE[s_singular]
        if s_singular in _CANONICAL_SLOTS:
            return s_singular
    # Try just the first word (handles "Ring Set", "Trinket (Category)", etc.)
    first_word = s_clean.split()[0] if ' ' in s_clean else None
    if first_word:
        if first_word in _SLOT_NORMALIZE:
            return _SLOT_NORMALIZE[first_word]
        if first_word in _CANONICAL_SLOTS:
            return first_word
    return None


def _wowhead_url(spec_slug: str, class_slug: str) -> str:
    return f"{WOWHEAD_BASE}/guide/classes/{class_slug}/{spec_slug}/bis-gear"


def _parse_gatherer_names(html: str) -> dict[int, str]:
    m = _GATHERER_RE.search(html)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
        return {int(k): v["name_enus"] for k, v in data.items() if v.get("name_enus")}
    except Exception:
        return {}


def _parse_bis_rows(html: str) -> list[tuple[str, int]]:
    """Return [(canonical_slot, item_id)] from the primary BiS table.

    Ring and trinket slots allow multiple items (all listed BiS options).
    All other slots take the first occurrence only.
    """
    content = html.replace("\\/", "/").replace("\\r\\n", "\n").replace("\\n", "\n")

    # Try to find the BiS table by its column header; fall back to full-page scan
    header_m = _TABLE_HEADER_RE.search(content)
    if header_m:
        section = content[header_m.start():]
        end = section.find("[/table]")
        if end > 0:
            section = section[:end]
    else:
        section = content

    seen_single: set[str] = set()           # one item per non-ring/trinket slot
    seen_multi: set[tuple[str, int]] = set()  # dedup ring/trinket by (slot, item_id)
    results: list[tuple[str, int]] = []
    pending_canonical: str | None = None    # slot inherited from a rowspan [td]
    pending_remaining: int = 0

    for tr_m in _TR_RE.finditer(section):
        row = tr_m.group(1)
        slot_m = _FIRST_TD_RE.search(row)
        if slot_m:
            canonical = _to_canonical_slot(slot_m.group(1))
            if canonical is None:
                logger.debug("Unknown slot %r skipped", slot_m.group(1).strip())
                pending_remaining = 0
                continue
            # Check whether this [td] spans multiple rows
            rowspan_m = _ROWSPAN_RE.match(row[slot_m.start():])
            if rowspan_m:
                pending_canonical = canonical
                pending_remaining = int(rowspan_m.group(1)) - 1
            else:
                pending_remaining = 0
        elif pending_remaining > 0:
            # Continuation row: no slot cell, inherit from the rowspan above
            canonical = pending_canonical
            pending_remaining -= 1
        else:
            continue

        item_m = _ITEM_IN_ROW_RE.search(row)
        if not item_m:
            continue
        item_id = int(item_m.group(1))

        if canonical in ("ring", "trinket"):
            key = (canonical, item_id)
            if key in seen_multi:
                continue
            seen_multi.add(key)
        else:
            if canonical in seen_single:
                continue
            seen_single.add(canonical)

        results.append((canonical, item_id))

    return results


async def _fetch_item_name(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, item_id: int
) -> tuple[int, str]:
    async with sem:
        try:
            r = await client.get(f"{NETHER_BASE}/tooltip/item/{item_id}", timeout=10.0)
            r.raise_for_status()
            return item_id, r.json().get("name", "")
        except Exception as e:
            logger.warning("Failed to fetch name for item %d: %s", item_id, e)
            return item_id, ""


async def fetch_wowhead_bis(
    spec_slug: str,
    class_slug: str,
    client: httpx.AsyncClient,
    guide_sem: asyncio.Semaphore,
) -> list[WowheadBisItem]:
    url = _wowhead_url(spec_slug, class_slug)
    async with guide_sem:
        try:
            r = await client.get(url, timeout=20.0)
            if r.status_code == 404:
                logger.debug("No WoWhead BiS guide for %s/%s", spec_slug, class_slug)
                return []
            r.raise_for_status()
        except Exception as e:
            logger.warning("Failed to fetch WoWhead BiS for %s/%s: %s", spec_slug, class_slug, e)
            return []
        finally:
            # Throttle guide fetches to avoid CloudFront rate limiting
            await asyncio.sleep(1.5)

    html = r.text
    rows = _parse_bis_rows(html)
    if not rows:
        logger.debug("No BiS rows parsed for %s/%s", spec_slug, class_slug)
        return []

    names = _parse_gatherer_names(html)

    missing = list({item_id for _, item_id in rows} - names.keys())
    if missing:
        sem = asyncio.Semaphore(5)
        fetched = await asyncio.gather(*[
            _fetch_item_name(client, sem, iid) for iid in missing
        ])
        for iid, name in fetched:
            if name:
                names[iid] = name

    items = []
    for slot, item_id in rows:
        items.append(WowheadBisItem(
            slot=slot,
            rank=1,
            item_id=item_id,
            item_name=names.get(item_id, ""),
        ))

    logger.info(
        "WoWhead BiS %s/%s — %d items: %s",
        spec_slug, class_slug, len(items),
        [f"{i.slot}={i.item_id}" for i in items],
    )
    return items
