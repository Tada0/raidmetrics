"""Parse popular gear, crafted items, and embellishments from gear-and-tier-set."""
import logging
import re

from . import (
    PopularItem, extract_id, extract_name, extract_slot_from_header,
    extract_usage, find_component,
)

logger = logging.getLogger(__name__)


def parse_gear(page_data: dict) -> list[PopularItem]:
    return (
        _parse_slot_tables(page_data)
        + _parse_crafted(page_data)
        + _parse_embellishments(page_data)
    )


def _rows_from_table(table: dict) -> list[dict]:
    return table.get("data", []) if isinstance(table, dict) else []


def _slot_from_table(table: dict) -> str:
    cols = table.get("columns", {})
    if not isinstance(cols, dict):
        return ""
    item_col = cols.get("item", {})
    header = item_col.get("header", "") if isinstance(item_col, dict) else ""
    return extract_slot_from_header(header)


def _item_from_row(row: dict, slot: str, is_crafted: bool, is_embellishment: bool, rank: int) -> PopularItem | None:
    item_jsx = row.get("item", "")
    # Embellishments can have two ItemIcon tags — take the first non-blank one
    if is_embellishment:
        # Archon.gg shows embellishment combinations: each row is two embellishments
        # shown together (e.g. "Arcanoweave Lining / Sunset Bloom Embroidery").
        # Use the first GearIcon id as the primary item_id; join all names as the combo.
        all_ids = re.findall(r'id=\{(\d+)\}', item_jsx)
        item_id = int(all_ids[0]) if all_ids else None
        item_id2 = int(all_ids[1]) if len(all_ids) >= 2 else None
        names = re.findall(r'>([^<>&][^<>]*)</(Item|Gear)Icon>', item_jsx)
        item_name = " / ".join(n[0].strip() for n in names) if names else ""
    else:
        item_id = extract_id(item_jsx)
        item_name = extract_name(item_jsx)

    if not item_id:
        return None

    usage = extract_usage(row.get("popularity", ""))
    kwargs = dict(
        slot=slot,
        rank=rank,
        item_id=item_id,
        item_name=item_name,
        usage_percent=usage,
        is_crafted=is_crafted,
        is_embellishment=is_embellishment,
    )
    if is_embellishment:
        kwargs["item_id2"] = item_id2
    return PopularItem(**kwargs)


def _parse_slot_tables(page_data: dict) -> list[PopularItem]:
    props = find_component(page_data, "BuildsGearTablesSection")
    if not props:
        logger.debug("BuildsGearTablesSection not found in gear page")
        return []

    items: list[PopularItem] = []
    for table in props.get("tables", []):
        slot = _slot_from_table(table)
        for rank, row in enumerate(_rows_from_table(table), start=1):
            item = _item_from_row(row, slot, is_crafted=False, is_embellishment=False, rank=rank)
            if item:
                items.append(item)
    return items


def _parse_crafted(page_data: dict) -> list[PopularItem]:
    props = find_component(page_data, "BuildsCraftedGearSection")
    if not props:
        return []

    items: list[PopularItem] = []
    for rank, row in enumerate(_rows_from_table(props.get("table", {})), start=1):
        item = _item_from_row(row, slot="", is_crafted=True, is_embellishment=False, rank=rank)
        if item:
            items.append(item)
    return items


def _parse_embellishments(page_data: dict) -> list[PopularItem]:
    props = find_component(page_data, "BuildsEmbellishmentsSection")
    if not props:
        return []

    seen: set[str] = set()
    items: list[PopularItem] = []
    rank = 1
    for row in _rows_from_table(props.get("table", {})):
        item = _item_from_row(row, slot="", is_crafted=True, is_embellishment=True, rank=rank)
        if item and item.item_name not in seen:
            seen.add(item.item_name)
            items.append(item)
            rank += 1
    return items
