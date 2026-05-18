# Loot Distribution Feature Design

## What it does

A GM/officer selects an item that dropped from a boss during a raid. The system shows each raider's upgrade value for that item, helping the GM decide who should receive it.

## Data sources

- **`boss_loot_items`** — every item that can drop from each boss, scraped from the Blizzard Journal API. Includes token/nullcore items with their class restrictions and the slot they synthesize.
- **`loot_report_items`** — each raider's Droptimizer results. Contains actual synthesized item IDs (not the nullcore token ID), keyed by `encounter_id` and `slot_name`.

## The token problem

This season has two token types:
- **Nullcores** — drop from regular bosses, synthesize a class-specific set piece for a fixed slot (e.g., "this boss always drops a legs nullcore"). There are multiple nullcore variants per boss, one per class group (e.g., Warrior/Paladin/DK get one variant, Hunter/Shaman/... get another).
- **Curios** — drop from the last boss (e.g. "Chiming Void Curio"). Traded at an NPC for any class set piece slot of the player's choice. `allowed_class_ids = null` (all classes eligible) and `synthesizes_slot = null` (slot is player-selected). For loot distribution, show all raiders ranked by their best upgrade from that encounter.

Raidbots Droptimizer (with "Include Catalyst Items" enabled) already expands tokens: it returns the **actual synthesized item** (e.g., warrior legs item_id), not the nullcore item_id. So `loot_report_items` never contains nullcore item_ids — it contains the real items.

## Matching logic

### Regular item drops
Match directly by `item_id` across all raiders' `loot_report_items`.

### Token drops (nullcores / curios)
Cannot match by `item_id` (nullcore_id ≠ synthesized_item_id).

Match by:
1. `encounter_id` — all synthesized items from a boss's nullcore share the same `encounter_id` as the nullcore itself in Droptimizer data.
2. `slot_name` — each boss's nullcore always synthesizes the same slot (e.g., `legs`). Stored in `boss_loot_items.synthesizes_slot`.
3. `raider class` — each nullcore variant is class-restricted. Filter by raiders whose class is in `boss_loot_items.allowed_class_ids`.

**Example:**
- "Voidforged Fanatical Nullcore" drops → `encounter_id=2739`, `synthesizes_slot=legs`, `allowed_class_ids=[1,2,6]` (Warrior/Paladin/DK)
- Query: `loot_report_items WHERE encounter_id=2739 AND slot_name='legs'`, then filter to raiders whose class is in `[1,2,6]`
- Hunter is excluded (not in allowed classes), even if Hunter has a legs upgrade from that encounter via a different nullcore variant

## DB schema (`boss_loot_items`)

```
encounter_id        INTEGER     — Blizzard encounter ID
zone_id             INTEGER     — raid zone
boss_name           TEXT
item_id             INTEGER     — the actual item that drops (e.g. nullcore item_id)
item_name           TEXT
is_token            BOOLEAN     — true for nullcores/curios
synthesizes_slot    TEXT        — e.g. 'legs', 'trinket'; null for non-tokens
allowed_class_ids   JSONB       — [1,2,6] for Warrior/Paladin/DK; null = unrestricted
```

## Data collection (scraper)

During `_scrape_season_config`, for each item returned by the Journal API:
1. Fetch `/data/wow/item/{item_id}` (static namespace, app token)
2. Read `requirements.playable_classes` → store as `allowed_class_ids`
3. Detect token via item class/subclass or inventory_type
4. For tokens: determine `synthesizes_slot` (see open question below)

### Open question: synthesizes_slot source

The Blizzard item API doesn't cleanly expose what slot a token creates. Options:
- Parse item description ("synthesize a soulbound set **leg** item") — fragile string matching
- Hardcode per known token item_ids for the season — simple, update each patch
- Derive at query time from existing `loot_report_items` for that `encounter_id` — requires at least one submitted report

## UI sketch

```
[Boss: Vaelgor & Ezzorak]  [Dropped: Voidforged Fanatical Nullcore (Legs · Warrior/Paladin/DK)]

Raider          Class       Item                            Upgrade
──────────────────────────────────────────────────────────────────────
Naughtybella    Warrior     Voidforged Corrupted Legguards  +4.2%
Tankmaster      Paladin     Voidforged Hallowed Legplates   +1.8%
Frostdk         Death Knight Voidforged Corrupted Legguards +0.9%

[No data: raiders who haven't submitted a Heroic Droptimizer for this difficulty]
```

Clicking "Award" records the loot assignment (future feature: loot history).
