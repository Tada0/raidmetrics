"""Parse popular enchants and gems from the enchants-and-gems page."""
import logging

from . import (
    PopularEnchant, PopularGem, extract_id, extract_name,
    extract_slot_from_header, extract_usage, find_component,
)

logger = logging.getLogger(__name__)


def parse_enchants_gems(page_data: dict) -> tuple[list[PopularEnchant], list[PopularGem]]:
    return _parse_enchants(page_data), _parse_gems(page_data)


def _slot_from_table(table: dict) -> str:
    cols = table.get("columns", {})
    if not isinstance(cols, dict):
        return ""
    item_col = cols.get("item", {})
    header = item_col.get("header", "") if isinstance(item_col, dict) else ""
    return extract_slot_from_header(header)


def _parse_enchants(page_data: dict) -> list[PopularEnchant]:
    props = find_component(page_data, "BuildsEnchantTablesSection")
    if not props:
        logger.debug("BuildsEnchantTablesSection not found")
        return []

    enchants: list[PopularEnchant] = []
    for table in props.get("tables", []):
        slot = _slot_from_table(table)
        for rank, row in enumerate(table.get("data", []), start=1):
            item_jsx = row.get("item", "")
            enchant_id = extract_id(item_jsx)
            if not enchant_id:
                continue
            enchants.append(PopularEnchant(
                slot=slot,
                rank=rank,
                enchant_id=enchant_id,
                enchant_name=extract_name(item_jsx),
                usage_percent=extract_usage(row.get("popularity", "")),
            ))

    return enchants


def _parse_gems(page_data: dict) -> list[PopularGem]:
    gems: list[PopularGem] = []

    for quality, component in [("epic", "BuildsPrimaryGemsSection"), ("rare", "BuildsSecondaryGemsSection")]:
        props = find_component(page_data, component)
        if not props:
            continue
        table = props.get("table", {})
        for rank, row in enumerate(table.get("data", []), start=1):
            item_jsx = row.get("item", "")
            item_id = extract_id(item_jsx)
            if not item_id:
                continue
            gems.append(PopularGem(
                gem_quality=quality,
                rank=rank,
                item_id=item_id,
                gem_name=extract_name(item_jsx),
                usage_percent=extract_usage(row.get("popularity", "")),
            ))

    return gems
