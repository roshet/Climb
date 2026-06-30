# Timeline-Derived Goal Metrics — Design Spec

**Date:** 2026-06-30
**Status:** Approved

## Problem

The goal/streak feature only offers end-of-game metrics read off flat `Match` columns (deaths, cs,
vision_score, gold_earned, kda). The most actionable laning-fundamentals coaching metrics are
**per-minute**: CS@10, gold@10, gold@14. We already fetch and store the full match timeline
(`Match.raw_timeline` JSON), so these are computable from data we already have — no new Riot calls.

## Scope (confirmed)

**Goals only.** Add CS@10 / gold@10 / gold@14 as selectable goal metrics with the same streak/history
UI. High-elo **benchmark** tier-averages for these are deliberately deferred — they would require the
harvester to fetch timeline-v5 per high-elo match (300→600 Riot calls/run, ~6→12 min runtime, 2× the
429 risk). The design leaves a clean forward path (a `benchmarkable` flag) to add them later.

## Design

**Precompute at save time into flat nullable `Match` columns.** `goal_metrics.METRICS` calls
`metric.value(obj)` reading flat attributes (`m.cs`, `m.gold_earned`). Computing the per-minute values
once at save time and storing them as columns makes the new metrics just
`lambda m: _opt(getattr(m, "cs_at_10", None))` — zero change to the abstraction's shape, and no
frontend change (the goals dropdown is catalog-driven via `/goals/metrics`). The player's
`puuid`→1-based `participant_index` is already resolved at both save sites, so the timeline lookup is
free there.

**"Not applicable" matches.** A per-minute value is `None` when the timeline is missing (matches saved
before this feature) or the game ended before minute N (remakes / early FF). The current streak logic
assumes every match yields a bool, so timeline metrics return `None` and `compute_goal_status` **skips**
None entries (streak/history/last_game_met/games_evaluated computed only over applicable matches), not
treating them as a miss. The existing 5 metrics never return None and are unaffected.

**Benchmark consumers filter to benchmarkable.** Both `get_benchmarks_view` and the harvester's
`extract_participant_metrics` iterate `METRICS`; unchanged they'd surface the new metrics with empty
tier-averages (view) or raise `AttributeError` on the participant SimpleNamespace (adapter). A
`benchmarkable: bool` field on `GoalMetric` (default `True`; `False` for the 3 timeline metrics) gates
both, keeping `/benchmarks` to the original 5 while `/goals/metrics` offers all 8.

## Schema

3 new nullable `Integer` columns on `Match`: `cs_at_10`, `gold_at_10`, `gold_at_14`. Declared as
`mapped_column(Integer, nullable=True)` on the model AND added to existing DBs via the
`PRAGMA table_info(matches)` ALTER pattern in `init_db()` (mirrors `lane_opponent_champion`). CS =
participant frame `minionsKilled + jungleMinionsKilled`; gold = `totalGold`.

## Out of scope (YAGNI)

- Retroactive backfill of pre-feature matches — the match-v5 `puuid`→`participant_index` mapping isn't
  stored, so old matches can't be cheaply recomputed; columns stay `None` and goals fill over ~20 games.
- Benchmark tier-averages for timeline metrics (deferred; gated behind the `benchmarkable` flag + a
  future harvester timeline fetch).
- More metrics (CS@14, XP/level) — start with the three confirmed.
