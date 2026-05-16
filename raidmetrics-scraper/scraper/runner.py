"""Core scrape logic, shared by the CLI entry point and the service."""
import asyncio
import logging

from .client import ArchonClient
from .config import CONCURRENT_SPECS, SPECS
from .db import get_session, init_db
from .parsers import ScrapedSpec
from .parsers.enchants import parse_enchants_gems
from .parsers.gear import parse_gear
from .storage import create_run, finish_run, prune_old_runs, save_spec

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
            gear_data, enchants_data = await asyncio.gather(
                client.fetch_page(spec_slug, class_slug, "gear-and-tier-set"),
                client.fetch_page(spec_slug, class_slug, "enchants-and-gems"),
            )
        except Exception as exc:
            logger.error("Failed %s/%s: %s", spec_slug, class_slug, exc)
            return None

        popular_items = parse_gear(gear_data)
        enchants, gems = parse_enchants_gems(enchants_data)

        bis_count = sum(1 for i in popular_items if i.is_bis)
        logger.info(
            "%s/%s — %d BiS, %d popular, %d enchants, %d gems",
            spec_slug, class_slug,
            bis_count, len(popular_items), len(enchants), len(gems),
        )
        return ScrapedSpec(
            spec_slug=spec_slug,
            class_slug=class_slug,
            popular_items=popular_items,
            popular_enchants=enchants,
            popular_gems=gems,
        )


async def run_scrape(specs: list[tuple[str, str]] | None = None, dry_run: bool = False) -> bool:
    """Run a full scrape. Returns True if all specs succeeded."""
    if specs is None:
        specs = SPECS

    if not dry_run:
        init_db()

    db = get_session() if not dry_run else None
    run = create_run(db) if db else None

    try:
        failed = 0
        sem = asyncio.Semaphore(CONCURRENT_SPECS)
        async with ArchonClient() as client:
            tasks = [
                asyncio.create_task(_scrape_spec(client, spec, cls, sem))
                for spec, cls in specs
            ]
            for coro in asyncio.as_completed(tasks):
                result = await coro
                if result is None:
                    failed += 1
                elif db and run:
                    save_spec(db, run, result)

        if db and run:
            finish_run(db, run, success=(failed == 0))
            prune_old_runs(db)

        logger.info(
            "Scrape complete — %d/%d specs OK%s",
            len(specs) - failed, len(specs),
            " (dry run)" if dry_run else "",
        )
        return failed == 0

    except Exception as exc:
        if db and run:
            finish_run(db, run, success=False, error=str(exc))
        raise
    finally:
        if db:
            db.close()
