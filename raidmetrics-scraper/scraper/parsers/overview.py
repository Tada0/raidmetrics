"""Parse BiS items from the Archon overview page."""
import logging

from . import (
    BisItem, extract_id, extract_json_attr, extract_name,
    extract_usage, find_component,
)

logger = logging.getLogger(__name__)

_COMPONENT = "BuildsBestInSlotGearSection"


def parse_overview(page_data: dict) -> list[BisItem]:
    props = find_component(page_data, _COMPONENT)
    if not props:
        logger.warning("Component '%s' not found in overview page", _COMPONENT)
        return []

    items: list[BisItem] = []
    # gear + weapons + trinkets cover all slots shown in the overview
    for raw in props.get("gear", []) + props.get("weapons", []) + props.get("trinkets", []):
        if raw.get("isPlaceholder"):
            continue
        icon = raw.get("icon", "")
        item_id = extract_id(icon)
        if not item_id:
            continue

        gems_data = extract_json_attr(icon, "gems")
        enchants_data = extract_json_attr(icon, "enchants")

        items.append(BisItem(
            slot="",  # Slot not labelled in overview — determined by gear tables
            item_id=item_id,
            item_name=extract_name(icon),
            is_bis="<BadgeLabel>BiS</BadgeLabel>" in icon,
            usage_percent=extract_usage(raw.get("topLabel") or ""),
            gem_ids=[int(g["id"]) for g in gems_data if "id" in g],
            enchant_id=int(enchants_data[0]["id"]) if enchants_data and "id" in enchants_data[0] else None,
        ))

    return items
