import json
import re
from dataclasses import dataclass, field


@dataclass
class PopularItem:
    slot: str
    rank: int
    item_id: int
    item_name: str
    usage_percent: float | None
    is_crafted: bool = False
    is_embellishment: bool = False


@dataclass
class PopularEnchant:
    slot: str
    rank: int
    enchant_id: int
    enchant_name: str
    usage_percent: float | None


@dataclass
class PopularGem:
    gem_quality: str  # "epic" | "rare"
    rank: int
    item_id: int
    gem_name: str
    usage_percent: float | None


@dataclass
class WowheadBisItem:
    slot: str
    item_id: int
    item_name: str


@dataclass
class ScrapedSpec:
    spec_slug: str
    class_slug: str
    popular_items: list[PopularItem] = field(default_factory=list)
    popular_enchants: list[PopularEnchant] = field(default_factory=list)
    popular_gems: list[PopularGem] = field(default_factory=list)
    wowhead_bis_items: list[WowheadBisItem] = field(default_factory=list)


# ── Section helpers ──────────────────────────────────────────────────────────

def get_sections(page_data: dict) -> list[dict]:
    return page_data.get("pageProps", {}).get("page", {}).get("sections", [])


def find_component(page_data: dict, component: str) -> dict | None:
    """Return the props dict for the first section with the given component name."""
    for s in get_sections(page_data):
        if s.get("component") == component:
            return s.get("props", {})
    return None


# ── JSX parsing helpers ──────────────────────────────────────────────────────

_ID_RE = re.compile(r'id=\{(\d+)\}')
_USAGE_RE = re.compile(r'([\d.]+)%')
_SLOT_HEADER_RE = re.compile(r'>([^<>]+)</ImageIcon>')


def extract_id(jsx: str) -> int | None:
    m = _ID_RE.search(jsx)
    return int(m.group(1)) if m else None


def extract_name(jsx: str) -> str:
    """Extract item name from ItemIcon or GearIcon JSX strings."""
    # GearIcon with BiS badge: &nbsp;Name</span></GearIcon>
    m = re.search(r'&nbsp;([^<]+)</span>', jsx)
    if m:
        return m.group(1).strip()
    # GearIcon without badge or ItemIcon: >Name</XxxIcon>
    m = re.search(r'>([^<>]+)</(Item|Gear)Icon>', jsx)
    if m:
        return m.group(1).strip()
    return ""


def extract_usage(s: str) -> float | None:
    """Extract a percentage value from either a plain string or JSX."""
    m = _USAGE_RE.search(s)
    return float(m.group(1)) if m else None


def extract_slot_from_header(header_jsx: str) -> str:
    """Extract slot label from a column header JSX string like <ImageIcon>Main-Hand</ImageIcon>."""
    m = _SLOT_HEADER_RE.search(header_jsx)
    return m.group(1).strip() if m else ""


def extract_json_attr(jsx: str, attr: str) -> list:
    """Extract attr={[...]} JSON from a JSX attribute string."""
    m = re.search(rf'{attr}=\{{(\[.*?\])}}', jsx, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return []
