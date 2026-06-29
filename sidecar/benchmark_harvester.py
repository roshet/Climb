# sidecar/benchmark_harvester.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from benchmark_metrics import extract_participant_metrics
from benchmark_tiers import APEX_TIERS, next_tier_up
from build_extractor import extract_participant_build
from database import (
    get_app_state, is_match_harvested, mark_match_harvested,
    record_benchmark_samples, record_build_samples, set_app_state,
)

logger = logging.getLogger(__name__)

SEED_PLAYER_CAP = 30
MATCHES_PER_SEED = 10
MATCH_FETCH_BUDGET = 300
RANKED_SOLO_QUEUE = 420
SEED_DIVISION = "I"
STALE_DAYS = 14
HARVEST_PACING_SECS = 1.2
_RATE_LIMIT_BACKOFF_SECS = 10


def should_harvest(db, now: datetime) -> bool:
    updated = get_app_state(db, "benchmark_updated_at")
    if not updated:
        return True
    return now - datetime.fromisoformat(updated) > timedelta(days=STALE_DAYS)


async def _seed_puuids(riot, target_tier: str) -> list[str]:
    if target_tier in APEX_TIERS:
        return await riot.get_apex_league_puuids(target_tier)
    return await riot.get_tier_division_puuids(target_tier, SEED_DIVISION)


def _accumulate_match(db, target_tier: str, match: dict) -> None:
    info = match["info"]
    patch = info.get("gameVersion", "unknown")
    for p in info["participants"]:
        role = p.get("teamPosition") or ""
        if not role:
            continue
        record_benchmark_samples(db, target_tier, role, patch, extract_participant_metrics(p))
        champion = p.get("championName") or ""
        record_build_samples(db, champion, role, target_tier, patch, extract_participant_build(p))


async def run_harvest(riot, db, player) -> None:
    if await riot.is_in_game():
        logger.info("[benchmark] game in progress; skipping harvest")
        return

    user_tier = await riot.get_solo_rank(player.riot_puuid)
    target_tier = next_tier_up(user_tier)
    set_app_state(db, "benchmark_user_tier", user_tier or "UNRANKED")
    set_app_state(db, "benchmark_target_tier", target_tier)
    logger.info("[benchmark] harvesting tier=%s (user=%s)", target_tier, user_tier)

    seed_puuids = (await _seed_puuids(riot, target_tier))[:SEED_PLAYER_CAP]
    fetches = 0
    for puuid in seed_puuids:
        if fetches >= MATCH_FETCH_BUDGET:
            break
        if await riot.is_in_game():
            logger.info("[benchmark] game started mid-harvest; stopping early")
            break
        try:
            match_ids = await riot.get_recent_match_ids(
                puuid, count=MATCHES_PER_SEED, queue=RANKED_SOLO_QUEUE)
        except Exception as e:
            logger.warning("[benchmark] match-id fetch failed for %s: %s", puuid, e)
            continue
        for mid in match_ids:
            if fetches >= MATCH_FETCH_BUDGET:
                break
            if is_match_harvested(db, mid):
                continue
            try:
                match = await riot.get_match(mid)
                fetches += 1
                await asyncio.sleep(HARVEST_PACING_SECS)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning("[benchmark] rate limited; backing off")
                    await asyncio.sleep(_RATE_LIMIT_BACKOFF_SECS)
                continue
            except Exception as e:
                logger.warning("[benchmark] match fetch failed for %s: %s", mid, e)
                continue
            _accumulate_match(db, target_tier, match)
            mark_match_harvested(db, mid)

    set_app_state(db, "benchmark_updated_at", datetime.now(timezone.utc).isoformat())
    logger.info("[benchmark] harvest complete: %d matches", fetches)
