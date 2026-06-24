# Higher-Elo Benchmarks — Design Spec

**Date:** 2026-06-24
**Status:** Approved (design); pending implementation plan
**Feature family:** Deeper coaching (follows team-fight review + goal/streak tracking)

## Summary

Show the player how their recent performance compares to players one rank tier
above their own, for the five metrics the goal system already tracks
(`deaths`, `cs`, `vision_score`, `gold_earned`, `kda`). The comparison is woven
into the existing **Goals tab**: each metric shows *your recent average* beside
the *target-tier average*, with the gap colored by metric direction.

Reference numbers come from a **fully-automatic, rate-limit-respecting background
harvest** on the user's own Riot API key, modeled on `backfill.py`. The metric
list stays sourced from `goal_metrics.METRICS` — no new cross-language metric
duplication is introduced.

## Goals

- Give the player an aspirational, concrete benchmark ("your deaths: 5.4 — Diamond
  averages 4.1") that can change their next game.
- Reuse what already exists: the 5 match-row goal metrics, the Goals tab, the
  `backfill.py` rate-limit/resume pattern.
- Keep the harvest cheap: **no timeline-v5 calls** in v1 (all five metrics read
  off match detail).

## Non-goals (v1)

- **Timeline-derived metrics** (CS@10, gold@14, deaths-by-15). These require a
  timeline-v5 fetch per match and are explicitly deferred to a later phase, to be
  bundled with the previously-deferred timeline-metrics work.
- Champ-select / overlay surfacing.
- Champion-specific benchmarks (v1 is role-level only).
- A manual "refresh" button or any user control over harvest timing (harvest is
  fully automatic).
- Tracking rank history / rank-up detection beyond reading the current tier.

## Key decisions (from brainstorming)

1. **Feedback type:** benchmarks vs better players (not personal goals, builds, or
   pattern surfacing).
2. **Data source:** live Riot pull on the user's own key (not bundled static data
   or a third-party stats API).
3. **Metric scope:** the 5 existing match-row goal metrics only — no timeline.
4. **Target rank:** adaptive, "one tier above me". Requires looking up the user's
   own solo-queue rank (new league-v4 support) and computing the next rung.
5. **UI surface:** woven into the Goals tab (reuse `GoalsPanel`), not a new tab.
6. **Harvest trigger:** fully automatic — runs in the background like `backfill`,
   refreshes on a cadence. Mitigations below keep it from starving live analysis.
7. **Datapoint attribution:** measure **all 10 participants** in each harvested
   match, bucketed by role — maximal data per match-detail call. The soft rank
   homogeneity of high-elo lobbies (apex lobbies blur upward) is accepted and
   documented.
8. **Unranked fallback:** default target tier = **Platinum**, labeled "play ranked
   to personalize".

## Data model (`database.py`)

New tables, created by `Base.metadata.create_all` (same as `Goal` — no PRAGMA
migration needed):

- **`benchmarks`**
  - `id` (PK)
  - `target_tier` (str, e.g. `"DIAMOND"`, `"MASTER"`)
  - `role` (str, `teamPosition`: `TOP`/`JUNGLE`/`MIDDLE`/`BOTTOM`/`UTILITY`)
  - `metric_key` (str, one of `goal_metrics.METRICS` keys)
  - `sum_value` (float) — running sum of the metric across harvested player-games
  - `sample_count` (int) — number of player-games contributing
  - `patch` (str) — game version the data was harvested under
  - `updated_at` (datetime)
  - Average is derived as `sum_value / sample_count`. Storing sum + count lets
    successive harvest runs accumulate incrementally and survive restarts.
  - Unique on `(target_tier, role, metric_key, patch)`.

- **`benchmark_harvested_matches`**
  - `match_id` (PK)
  - `harvested_at` (datetime)
  - Dedup/resume guard so re-runs skip already-processed matches.

Harvest progress state (last run timestamp, last target tier, last patch) is
stored in the existing `app_state` key/value table.

## Backend

### `riot_client.py` — add league-v4 support

league-v4 is **platform-routed** (`{platform}.api.riotgames.com`, e.g. `na1`),
unlike match-v5/account-v1 which use the regional cluster. Store the platform host
alongside `self.regional`:

- `self.platform = region.lower()` (the constructor already receives `region`,
  e.g. `"NA1"`).

New methods:

- `get_solo_rank(puuid) -> str | None` — `GET /lol/league/v4/entries/by-puuid/{puuid}`,
  return the `tier` of the `RANKED_SOLO_5x5` entry, or `None` if unranked.
- Apex seed lists (used when target tier ∈ {MASTER, GRANDMASTER, CHALLENGER}):
  `GET /lol/league/v4/{challenger|grandmaster|master}leagues/by-queue/RANKED_SOLO_5x5`.
- Sub-apex seed entries (target tier ≤ DIAMOND):
  `GET /lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}?page={n}`.
- Extend the match-id fetch to accept an optional `queue=420` filter (solo-queue
  only) so harvested matches are ranked solo.

Note: league-v4 entries return `puuid` on modern responses; if a given response
only carries `summonerId`, fall back to summoner-v4 to resolve the puuid. The plan
should verify which fields are present and handle both.

### `benchmark_harvester.py` (new module)

Responsibilities:

1. **Resolve target tier.** Look up the user's solo-queue tier via
   `get_solo_rank`; compute the next rung on the ladder
   `IRON < BRONZE < SILVER < GOLD < PLATINUM < EMERALD < DIAMOND < MASTER <
   GRANDMASTER < CHALLENGER`. Cap at `CHALLENGER`. Unranked → `PLATINUM` (labeled).
2. **Seed players** from the target tier (apex league list, or paginated entries),
   up to a configured cap.
3. **Harvest matches.** For each seed player, fetch recent solo-queue match IDs;
   for each not-yet-harvested match, fetch match detail and extract **every
   participant's** five metric values, bucketed by `teamPosition`.
4. **Accumulate** into `benchmarks` (sum + count per (target_tier, role,
   metric_key, patch)); record the match in `benchmark_harvested_matches`.

Guardrails (all configurable constants):

- **Budget cap** per run — e.g. ≤300 match-detail fetches — so a run is bounded.
- **Resumable** — skip match IDs already in `benchmark_harvested_matches`.
- **429-aware** — reuse the backoff/skip pattern `backfill.py` already uses.
- **Yields to live play** — skip/pause when `riot_client.is_in_game()` is true.
- **Refresh policy** — re-harvest only if the stored data is >14 days old or the
  current patch differs from the stored patch; otherwise no-op.

### `main.py`

- Register the harvest as a **lifespan background task** (alongside
  `game_end_watcher`, `LiveGameMonitor`, etc.). It self-gates on the refresh
  policy so it's cheap when data is fresh.
- New endpoint **`GET /benchmarks`** returning:
  ```json
  {
    "user_tier": "PLATINUM",
    "target_tier": "DIAMOND",
    "role": "MIDDLE",
    "status": "ready | harvesting | stale | none",
    "updated_at": "2026-06-24T...",
    "metrics": [
      {
        "metric_key": "deaths",
        "label": "Deaths",
        "comparison": "lte",
        "your_avg": 5.4,
        "tier_avg": 4.1,
        "sample_count": 1830
      }
    ]
  }
  ```
  - The user's role and per-metric averages are computed **on demand** from recent
    `Match` rows (mirrors how goal status / `streak_clean` are recomputed — no
    results table). The user's `role` is the mode of their recent match roles; the
    tier averages are read for that role.
  - `tier_avg`/`sample_count` come from `benchmarks`. A metric whose
    `sample_count` is below a floor is returned with `tier_avg: null` (frontend
    shows "not enough data yet").

## Frontend

- `src/shared/types.ts`: add `Benchmark` and `BenchmarkResponse` types matching the
  endpoint contract.
- `GoalsPanel.tsx`: add a **"Benchmarks vs {target_tier}"** block. For each metric,
  render *your avg* vs *tier avg*, coloring the gap by the metric's `comparison`
  (good/bad depending on GTE vs LTE direction). Handle states: `harvesting`
  (spinner / "building your benchmarks…"), `none` (not yet started), `stale`
  (show data + subtle "updating" hint), and per-metric "not enough data".
- No new tab, no new window. `delJson`/typed client already exist from the goals work.

## Edge cases

- **Unranked user:** default target = Platinum, clearly labeled.
- **Already Challenger:** target tier stays Challenger.
- **Sparse role data:** per-metric `tier_avg: null` until `sample_count` floor met.
- **Rank homogeneity:** apex lobbies contain Master/GM/Challenger mixed; the
  benchmark blurs slightly upward of the named tier. Accepted (still "better than
  you"); documented.
- **Harvest mid-game:** skipped while `is_in_game()`.

## Testing

- **`goal_metrics` reuse** keeps the metric-extraction logic covered by existing
  tests.
- **Harvester unit tests** (mocked `riot_client`): sum/count aggregation math, role
  bucketing, dedup via `benchmark_harvested_matches`, budget cap enforcement,
  tier-ladder "one above" logic (incl. Challenger cap and unranked → Platinum),
  refresh-policy gating (fresh vs stale vs patch-change).
- **`/benchmarks` endpoint test**: import `main` with dummy env + monkeypatched
  `main.db` (same approach as the goals API test — lazy client ctors, bg tasks only
  under lifespan).
- **Frontend render test** for the benchmark block in `GoalsPanel` (states +
  direction coloring), following the existing RTL component-test pattern.

## Out of scope / future phases

- Timeline-derived benchmarks (CS@10, gold@14) — next phase, paired with the
  deferred timeline-metrics work.
- Champion-scoped benchmarks; champ-select surfacing; manual refresh control;
  adaptive rank tracking over time.
