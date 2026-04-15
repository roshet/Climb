# Match History Backfill — Design Spec
**Date:** 2026-04-15
**Status:** Approved

---

## Overview

When the app starts or a new player completes setup, automatically fetch and analyze the last 30 days of match history in the background. This makes the app immediately useful on first install rather than requiring the user to play a game before any analysis is available.

---

## Architecture

### Modified Files
- `sidecar/main.py` — add `backfill_history()` coroutine and wire up two trigger points
- `sidecar/riot_client.py` — add optional `start_time: int | None = None` parameter to `get_recent_match_ids()`, passed as `startTime` query param to the Riot API. Also increase max `count` to 100 (Riot API maximum) for backfill calls.
- `sidecar/database.py` — add `get_all_match_ids(db) -> set[str]` helper that returns just the primary keys from the matches table, used to efficiently filter already-analyzed games.

No new files. No schema changes.

---

## Trigger Points

Backfill fires in two situations:

1. **App startup** — inside the FastAPI lifespan startup handler, after `get_player()` confirms a player is set up. Handles the case where games were played while the app was closed.
2. **After setup completes** — in the `POST /player` endpoint, after `save_player()` succeeds. Handles new users who just entered their summoner name for the first time.

Both trigger points call the same `backfill_history()` coroutine via `asyncio.create_task()` so the app remains fully usable while backfill runs.

A module-level `_backfill_running: bool = False` flag prevents two concurrent backfills (e.g. startup and setup firing simultaneously).

---

## Backfill Algorithm

```
backfill_history():
  if _backfill_running: return
  set _backfill_running = True
  try:
    fetch match IDs from last 30 days (startTime = now - 30*24*3600)
    load existing match_ids from DB
    new_ids = fetched_ids - existing_ids
    for each match_id in new_ids:
      try:
        fetch match data + timeline
        run full analysis pipeline (analyze_timeline → enrich_moments → save)
        sleep 3 seconds
      except 429:
        sleep 10 seconds
        retry once
      except any other error:
        log and continue to next game
    update player.last_synced_at = now
  finally:
    set _backfill_running = False
```

### Rate Limiting

Riot dev key limits: 100 requests per 2 minutes. Each game costs 2 requests (match + timeline). Sleeping 3 seconds between games gives ~80 requests per 2 minutes — a comfortable margin below the limit.

At 3s per game, 30 days of history (typically 20–50 games) completes in 1–2.5 minutes.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Single game fetch fails (5xx, timeout) | Log error, skip that game, continue |
| Rate limited (429) | Sleep 10s, retry once, then skip if still failing |
| No games in last 30 days | Loop runs zero iterations, completes immediately |
| Backfill already running | Early return via `_backfill_running` guard |
| Player not set up at startup | Early return — no player in DB |

All errors are logged to sidecar stdout only. No UI feedback — backfill is silent.

---

## Data Flow

```
startup / setup complete
  → asyncio.create_task(backfill_history())
    → riot.get_recent_match_ids(puuid, start_time=30_days_ago)
    → filter out match_ids already in DB
    → for each new match_id:
        riot.get_match(match_id)
        riot.get_timeline(match_id)
        analyze_timeline(...)
        enrich_moments(...)
        save_match(db, ...)
        save_pivotal_moments(db, match_id, ...)
        asyncio.sleep(3)
    → save_player last_synced_at = now
```

---

## Out of Scope

- Progress reporting in the UI — backfill is silent
- Configurable backfill window — 30 days is fixed
- Scheduled re-sync — startup trigger handles catching up on missed games
- Backfill for ARAM or other queue types — same queue filter as the existing watcher
