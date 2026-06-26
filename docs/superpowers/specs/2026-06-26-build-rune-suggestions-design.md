# High-Elo Build / Rune Suggestions — Design Spec

**Date:** 2026-06-26
**Status:** Approved

## Problem

Climb coaches League players. Three "deeper coaching" features have shipped (team-fight review,
goal/streak tracking, higher-elo benchmarks). The next named candidate — build/rune suggestions —
was assumed to require an external optimal-build data source (op.gg / u.gg style), which is fragile
and ToS-risky.

## Insight

We already built the right engine: the high-elo benchmark harvester. It fetches high-elo ranked
matches on the user's own Riot key, and the match-v5 participant JSON it already holds carries each
player's final items (`item0..6`), full rune page (`perks`), and summoner spells
(`summoner1Id/2Id`) **for free** — no extra Riot calls, no timeline, no third-party scraping. We
piggyback build aggregation onto the harvester's existing per-participant loop and surface the most
popular build during champ select.

## Product decisions (confirmed)

- **Show:** core item build + full rune page + summoner spells, for the locked champion in champ select.
- **Ranking:** most *popular* (frequency) among high-elo players — no win-rate (noisy on small
  samples). Sample-gated at 30, mirroring `BENCHMARK_SAMPLE_FLOOR`.
- **Display:** item/rune/spell names + icons resolved via the LCU (the League client is running
  during champ select).
- **Segmentation:** aggregate per `(champion, role, target_tier)`. `target_tier` reuses the
  benchmark harvester's "one tier above me" value. At champ select, the user's role comes from the
  LCU session `assignedPosition`, falling back to the champion's most-sampled role.

## Architecture

Layering mirrors benchmarks: `database.py` returns **raw aggregates** (pure, sqlite-testable);
`main.py` / `build_view.py` does the "dressing" (LCU name/icon resolution, item filtering,
sample-gating), exactly as `get_benchmarks_view` computes averages over raw `get_benchmarks` sums.

Data flow: harvest → `BuildSample` popularity counts → per-request aggregation in `/champ-select` →
LCU id→name+icon resolution → icons proxied through the sidecar → React render.

### Key design points

- **Coherent rune page:** store and rank the *whole-page signature*, never independent rune
  popularity (which would yield an illegal frankenpage). Validate selection counts before encoding;
  `None` on malformed; return the single most-popular complete page.
- **Store-raw, filter-at-read for items:** harvest stays Riot-only / offline (no item metadata
  needed); at read time filter to completed items via LCU `items.json` meta —
  `priceTotal >= 1100 AND to == [] AND categories has no Consumable/Trinket`. Naturally keeps
  upgraded boots, drops basic boots / components / pots / trinkets, no tier logic. Exclude `item6`
  (trinket slot) and dedupe items per participant at extraction.
- **Icon boundary (the one real risk):** the renderer talks plain `http://localhost:8765`; LCU
  assets are `https://127.0.0.1:{port}` behind a self-signed cert + HTTP basic auth, so an `<img>`
  in the renderer cannot load them directly. Solution: a sidecar `/lcu-image?path=...` proxy
  (SSRF-guarded to `/lol-game-data/assets`, lowercases the path, attaches basic auth,
  `verify=False`). Backend emits a relative `icon_url`; renderer wraps with `sidecarUrl()`. Chosen
  over Data Dragon CDN because LCU `iconPath` is already patch-correct and local — no version /
  filename mapping, offline-safe while the client is up.
- **Dedup is free:** builds and metrics are recorded in the same `_accumulate_match` pass, so the
  existing `BenchmarkHarvestedMatch` ledger processes each match exactly once for both.

## Schema

New `BuildSample` table, auto-created by `Base.metadata.create_all` (no PRAGMA migration — new table):
`(id, champion, role, target_tier, patch, kind, element_id, count, updated_at)`, one logical row per
`(champion, role, target_tier, patch, kind, element_id)` enforced by query-or-create (mirrors
`Benchmark` / `record_benchmark_samples`). `element_id` by `kind`:

- `kind="item"` → `str(item_id)` (raw, every items0..5; filtered at read)
- `kind="rune_page"` → `"{primaryStyle}|{keystone},{p1},{p2},{p3}|{subStyle}|{s1},{s2}|{off},{flex},{def}"`
- `kind="spells"` → order-normalized `"{min},{max}"`

`n_samples` = spell-pair count (one per participant) = games sampled, used for the sample gate.

## Surfaces

- **Backend:** `database.py` (model + `record_build_samples` + `get_build_suggestions` +
  `most_sampled_role`), new `build_extractor.py` (extraction + signature encode/decode), new
  `build_view.py` (`is_core_item`, `_icon_url`, `_assemble_suggested_build`), `lcu_client.py`
  (asset caches + `get_asset_bytes`), `benchmark_harvester.py` (one call in `_accumulate_match`),
  `main.py` (async `/champ-select` enrichment + `/lcu-image` proxy), `champ_select_monitor.py`
  (capture `assignedPosition`).
- **Frontend:** `src/shared/types.ts` (`SuggestedBuild` + nested types, `suggested_build?` on
  `ChampData`), `src/champ-select/App.tsx` (render block after the matchups block, icons via
  `sidecarUrl(icon_url)`, `insufficient` empty-state, keep `pointer-events-none`).

## Out of scope (YAGNI)

- Build *order* / skill order (needs timeline-v5 — deliberately avoided, like the harvester).
- Matchup-conditioned builds (would fragment sample size; the monitor doesn't capture live enemy).
- Win-rate ranking.
