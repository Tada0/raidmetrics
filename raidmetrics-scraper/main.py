"""
Raidmetrics Archon scraper — CLI entry point.

Usage:
    python main.py                            # scrape all specs
    python main.py --specs frost/mage        # scrape specific spec(s)
    python main.py --dry-run                  # scrape but don't write to DB
    python main.py --verbose                  # debug logging
"""

import argparse
import asyncio
import logging
import sys

from scraper.config import SPECS
from scraper.runner import run_scrape

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _parse_spec_arg(value: str) -> tuple[str, str]:
    parts = value.split("/", 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f"Expected SPEC/CLASS, got '{value}'")
    return parts[0], parts[1]


def main():
    parser = argparse.ArgumentParser(description="Scrape Archon.gg WoW build data")
    parser.add_argument(
        "--specs",
        nargs="+",
        metavar="SPEC/CLASS",
        type=_parse_spec_arg,
        help="Limit to specific specs, e.g. --specs frost/mage havoc/demon-hunter",
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    specs = args.specs or SPECS
    success = asyncio.run(run_scrape(specs, dry_run=args.dry_run))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
