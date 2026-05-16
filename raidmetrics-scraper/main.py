"""
Raidmetrics Archon scraper.

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

from scraper.client import ArchonClient
from scraper.config import CONCURRENT_SPECS, SPECS
from scraper.db import get_session, init_db
from scraper.parsers import ScrapedSpec
from scraper.parsers.enchants import parse_enchants_gems
from scraper.parsers.gear import parse_gear
from scraper.parsers.overview import parse_overview
from scraper.storage import create_run, finish_run, prune_old_runs, save_spec

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def _scrape_spec(
    client: ArchonClient,
    spec_slug: str,
    class_slug: str,
    sem: asyncio.Semaphore,
) -> ScrapedSpec | None:
    async with sem:
        logger.info("Scraping %s/%s", spec_slug, class_slug)
        try:
            overview_data, gear_data, enchants_data = await asyncio.gather(
                client.fetch_page(spec_slug, class_slug, "overview"),
                client.fetch_page(spec_slug, class_slug, "gear-and-tier-set"),
                client.fetch_page(spec_slug, class_slug, "enchants-and-gems"),
            )
        except Exception as exc:
            logger.error("Failed %s/%s: %s", spec_slug, class_slug, exc)
            return None

        bis_items = parse_overview(overview_data)
        popular_items = parse_gear(gear_data)
        enchants, gems = parse_enchants_gems(enchants_data)

        logger.info(
            "%s/%s — %d BiS, %d popular items, %d enchants, %d gems",
            spec_slug, class_slug,
            len(bis_items), len(popular_items), len(enchants), len(gems),
        )
        return ScrapedSpec(
            spec_slug=spec_slug,
            class_slug=class_slug,
            bis_items=bis_items,
            popular_items=popular_items,
            popular_enchants=enchants,
            popular_gems=gems,
        )


async def scrape(specs: list[tuple[str, str]], dry_run: bool) -> bool:
    sem = asyncio.Semaphore(CONCURRENT_SPECS)
    async with ArchonClient() as client:
        results = await asyncio.gather(
            *[_scrape_spec(client, spec, cls, sem) for spec, cls in specs]
        )

    scraped = [r for r in results if r is not None]
    failed = len(specs) - len(scraped)

    if not dry_run:
        db = get_session()
        run = create_run(db)
        try:
            for spec in scraped:
                save_spec(db, run, spec)
            finish_run(db, run, success=(failed == 0))
            prune_old_runs(db)
        except Exception as exc:
            finish_run(db, run, success=False, error=str(exc))
            raise
        finally:
            db.close()

    logger.info(
        "Done — %d/%d specs OK%s",
        len(scraped), len(specs),
        " (dry run, nothing saved)" if dry_run else "",
    )
    if failed:
        logger.warning("%d spec(s) failed", failed)

    return failed == 0


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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape but don't write to DB",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.dry_run:
        init_db()

    specs = args.specs or SPECS
    success = asyncio.run(scrape(specs, dry_run=args.dry_run))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
