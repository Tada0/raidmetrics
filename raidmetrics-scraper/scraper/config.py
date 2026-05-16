ARCHON_BASE = "https://www.archon.gg"

PAGES = ["overview", "gear-and-tier-set", "enchants-and-gems"]

# (spec_slug, class_slug) — 40 specs across all WoW classes
SPECS: list[tuple[str, str]] = [
    # Death Knight
    ("blood", "death-knight"),
    ("frost", "death-knight"),
    ("unholy", "death-knight"),
    # Demon Hunter
    ("havoc", "demon-hunter"),
    ("devourer", "demon-hunter"),
    ("vengeance", "demon-hunter"),
    # Druid
    ("balance", "druid"),
    ("feral", "druid"),
    ("guardian", "druid"),
    ("restoration", "druid"),
    # Evoker
    ("augmentation", "evoker"),
    ("devastation", "evoker"),
    ("preservation", "evoker"),
    # Hunter
    ("beast-mastery", "hunter"),
    ("marksmanship", "hunter"),
    ("survival", "hunter"),
    # Mage
    ("arcane", "mage"),
    ("fire", "mage"),
    ("frost", "mage"),
    # Monk
    ("brewmaster", "monk"),
    ("mistweaver", "monk"),
    ("windwalker", "monk"),
    # Paladin
    ("holy", "paladin"),
    ("protection", "paladin"),
    ("retribution", "paladin"),
    # Priest
    ("discipline", "priest"),
    ("holy", "priest"),
    ("shadow", "priest"),
    # Rogue
    ("assassination", "rogue"),
    ("outlaw", "rogue"),
    ("subtlety", "rogue"),
    # Shaman
    ("elemental", "shaman"),
    ("enhancement", "shaman"),
    ("restoration", "shaman"),
    # Warlock
    ("affliction", "warlock"),
    ("demonology", "warlock"),
    ("destruction", "warlock"),
    # Warrior
    ("arms", "warrior"),
    ("fury", "warrior"),
    ("protection", "warrior"),
]

# Max concurrent spec scrapes (each fetches 3 pages in parallel)
CONCURRENT_SPECS = 2
