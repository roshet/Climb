# Timeline-Derived Goal Metrics (CS@10, gold@10, gold@14)

## Context

Climb coaches League players. Four "deeper coaching" features have shipped (team-fight review,
goal/streak tracking, higher-elo benchmarks, build/rune suggestions). The goal/streak feature only
offers **end-of-game** metrics read off flat `Match` columns (deaths, cs, vision_score, gold_earned,
kda). The most actionable laning-fundamentals metrics are **per-minute**: CS@10, gold@10, gold@14.
We already fetch and store the full match timeline (`Match.raw_timeline` JSON), so these are
computable from data we already have — no new Riot calls.

**Scope (confirmed): goals only.** Add CS@10 / gold@10 / gold@14 as selectable goal metrics with the
same streak/history UI. High-elo **benchmark** tier-averages for these are deliberately deferred — they
would require the harvester to fetch timeline-v5 per high-elo match (300→600 Riot calls/run, ~6→12 min,
2× the 429 risk). The design leaves a clean forward path (a `benchmarkable` flag) to add them later.

## Approach

**Precompute at save time into flat nullable `Match` columns.** The goal-metric abstraction
(`goal_metrics.METRICS`) calls `metric.value(obj)` and reads flat attributes (`m.cs`, `m.gold_earned`).
If we compute the per-minute values once at save time and store them as columns, the new metrics are
just `lambda m: _opt(getattr(m, "cs_at_10", None))` — **zero change to the abstraction's shape or the
frontend** (the goals dropdown is already catalog-driven via `/goals/metrics`). Participant resolution
(`puuid` → 1-based `participant_index`) already happens at both save sites, so the timeline lookup is
free there.

**Key new behavior — "not applicable" matches.** A per-minute value is `None` when the timeline is
missing (matches saved before this feature) or the game ended before minute N (remakes/early FF).
The current streak logic assumes every match yields a bool. So timeline metrics return `None`, and
`compute_goal_status` **skips** None entries (streak/history/last_game_met computed only over matches
where the metric applies) rather than treating them as a miss. The existing 5 metrics never return
None, so they are unaffected.

**Benchmark consumers must filter to benchmarkable metrics.** Both `get_benchmarks_view` and the
harvester's `extract_participant_metrics` iterate `METRICS`; left unchanged they would surface the new
metrics with empty tier-averages (view) or `AttributeError` on the participant SimpleNamespace
(adapter). A `benchmarkable: bool` field on `GoalMetric` (default `True`; `False` for the 3 timeline
metrics) gates both, keeping `/benchmarks` to the original 5 while `/goals/metrics` offers all 8.

**Out of scope:** retroactive backfill of existing matches. `raw_timeline` is stored but the match-v5
participant `puuid`→`participant_index` mapping is not, so old matches can't be cheaply recomputed; the
columns stay `None` for them and goals fill over the next ~20 games. (Re-fetch-from-Riot backfill is a
possible later add.)

## Schema

3 new nullable `Integer` columns on `Match` (`sidecar/database.py`): `cs_at_10`, `gold_at_10`,
`gold_at_14`. Declared as `mapped_column(Integer, nullable=True)` on the model AND added to existing
DBs via the `PRAGMA table_info(matches)` ALTER pattern in `init_db()` (mirrors `lane_opponent_champion`,
~lines 105-115) — one `ALTER TABLE matches ADD COLUMN ... INTEGER` per missing column. CS = participant
frame `minionsKilled + jungleMinionsKilled`; gold = `totalGold`.

## Tasks (TDD, subagent-driven; mirror prior features)

### Task 1 — `sidecar/timeline_metrics.py` (pure module)
`cs_at_minute(timeline, participant_id, minute) -> int | None`, `gold_at_minute(...) -> int | None`,
and `extract_timeline_metrics(timeline, participant_id) -> dict[str, int | None]` returning
`{"cs_at_10", "gold_at_10", "gold_at_14"}`. Find the first frame with `timestamp >= minute*60_000`
in `timeline["info"]["frames"]`; read `participantFrames[str(participant_id)]`. Reuse the
frame-at-timestamp pattern from `laner_analyzer._cs_differential_at_14`/`_gold_differential_at_14`
(don't import the private helpers — write focused ones). Defensive: missing/empty timeline, no frame
reaching minute N, missing participant key → `None`.
**Tests** (`tests/test_timeline_metrics.py`): value at 10/14 from a built frame list; CS includes
jungle minions; `None` when game shorter than N; `None` for empty `{}` / missing `info.frames` /
missing participant; string-key access.

### Task 2 — Schema + save wiring
Add the 3 nullable columns to the `Match` model + the `init_db()` PRAGMA ALTER (`sidecar/database.py`).
Populate them at BOTH save sites where `timeline_data` and `participant_index` are already in scope:
`backfill.analyze_and_save_match` (`backfill.py:60` save_match dict) and `trigger_analysis` (`:49`),
by spreading `extract_timeline_metrics(timeline_data, participant_index)` into the dict. (`save_match`
is `Match(**data)`, so the model must declare the columns — it now does.)
**Tests** (`tests/test_timeline_save.py` or extend existing): saving a match dict with the 3 keys
populates the columns; `None` values persist as NULL; `init_db` adds the columns to a pre-existing
`matches` table missing them (PRAGMA path).

### Task 3 — Metric registry extension (`sidecar/goal_metrics.py` + `goal_tracker.py`)
- Add `benchmarkable: bool = True` to the `GoalMetric` dataclass; widen `value` return to `float | None`.
- Register `cs_at_10` (GTE, label "CS@10"), `gold_at_10` (GTE, "Gold@10"), `gold_at_14` (GTE,
  "Gold@14"), all `is_float=False`, `benchmarkable=False`, value = `lambda m: _opt(getattr(m, "<col>",
  None))` where `_opt` returns `None` if the attr is `None` else `float(...)`.
- `goal_met` and `evaluate_metric` return `None` when `metric.value(...)` is `None`.
- `compute_goal_status` (`goal_tracker.py`): filter out `None` results before computing
  streak/history/last_game_met/games_evaluated (count only applicable matches).
**Tests**: `goal_met` → None when column None; `compute_goal_status` skips None matches (streak spans
only applicable games, history excludes them); `metric_catalog()` includes the 3 new metrics; existing
5-metric behavior unchanged.

### Task 4 — Benchmark consumers filter to benchmarkable
`get_benchmarks_view` (`main.py`) and `extract_participant_metrics` (`benchmark_metrics.py`) iterate
only `metric.benchmarkable` metrics.
**Tests**: `/benchmarks` payload excludes timeline metrics (only the 5 benchmarkable);
`extract_participant_metrics` returns only the 5 keys (no AttributeError); `/goals/metrics` still
returns all 8.

### Task 5 — Frontend surface + full gate
No frontend code change expected — the catalog-driven goals dropdown and goal cards render the new
metrics generically. Extend `src/chat/GoalsPanel.test.tsx`'s `/goals/metrics` mock to include a
timeline metric (e.g. `cs_at_10` → "CS@10") and assert the option renders. Run the full frontend gate.

## Verification
- Backend: `cd sidecar && python -m pytest` green after each task and at the end.
- Frontend: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` (last task).
- Manual (optional): set a goal on CS@10 in the Goals tab; confirm it shows a streak computed from
  recent games (and that games without timeline data are skipped, not counted as misses).
- CI (`.github/workflows/ci.yml`) enforces backend pytest + frontend typecheck/lint/test/build on push.

## Process
Spec + plan docs under `docs/superpowers/` → short-lived `timeline-goal-metrics` branch →
subagent-driven (5 tasks, per-task spec+quality review) → holistic final review → FF merge → push →
verify CI → update `climb-roadmap` memory.
