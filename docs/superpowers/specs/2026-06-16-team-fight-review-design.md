# Team-Fight Review — Design

**Date:** 2026-06-16
**Status:** Approved (brainstorming) — ready for implementation plan

## Context

Climb already produces per-game "pivotal moments" (deaths, objectives, towers, CS/gold
diffs, roams, vision) via role-aware analyzers, enriches them with Gemini coaching notes
(static fallback in `counterfactual.py`), persists them to `pivotal_moments`, and surfaces
them in the post-game popup and the chat window's game detail. What's missing is any
**team-fight-level** view: the analyzers see individual kills but never group them into the
fights that usually decide mid/late games.

This is the first "deeper coaching" product-expansion feature. It was chosen because it
extends the existing analysis engine and uses **only data already stored** (the full
timeline-v5 JSON in `matches.raw_timeline`), so it needs no new external data sources and
slots into the existing moment pipeline with almost no plumbing.

The intended outcome: after a game, the player sees each decisive team fight as a coachable
moment — when/where it happened, whether their team won or lost it, whether they personally
contributed (kill/assist/death) or were absent, and whether an objective was at stake.

## Scope

**In scope:** detect decisive team fights from the stored timeline; emit them as new
`PivotalMomentData` moments (`teamfight_won` / `teamfight_lost`) that flow through the
existing enrichment → persistence → popup/chat pipeline.

**Coaching focus (chosen):** outcome + the player's involvement. Each moment states the
fight outcome (kills traded), the player's involvement (got a kill/assist, died, or not
involved), and objective context.

**Out of scope (intentional non-goals):**
- Positioning / "out of position" analysis — frame positions are sampled only every 60s,
  too coarse to be reliable.
- Deduping against existing per-death moments — the player's individual death still appears
  as its own moment; the team-fight moment is a deliberately higher-altitude summary on top.
- Even-trade fights are skipped to reduce noise.
- No DB schema change, no new endpoints, no new UI components.

## Detection — `sidecar/teamfight_analyzer.py` (new)

`analyze_teamfights(timeline: dict, participant_id: int) -> list[PivotalMomentData]`

1. Collect all `CHAMPION_KILL` events across timeline frames, sorted by timestamp.
2. **Cluster** kills: a kill joins the current cluster if it occurs within **~20s** of the
   previous kill in that cluster; otherwise it starts a new cluster. (Threshold is a module
   constant, easily tunable.)
3. A cluster is a **team fight** if it has **≥3 total kills** (filters picks/skirmishes
   already covered by existing `death` / `solo_kill` moments). Constant, tunable.
4. For each team fight, compute:
   - **Kills by team:** count victims on the player's team vs the enemy team (team membership
     via the existing `TEAM_100_IDS` / `TEAM_200_IDS` helpers in `timeline_analyzer.py`).
   - **Outcome:** `teamfight_won` if the player's team got more kills than it lost,
     `teamfight_lost` if fewer. **Even trades are skipped** (no moment emitted).
   - **Player involvement:** scan the cluster's kills for `participant_id` as
     `killerId` / `victimId` / `assistingParticipantIds` → "you got N kill(s)", "you died",
     "you got an assist", or "you weren't involved".
   - **Objective context:** any `ELITE_MONSTER_KILL` whose timestamp falls within the
     cluster's time span → annotate "near Dragon / Baron / Herald".

## Data model — reuse `PivotalMomentData` (no schema change)

Each emitted fight is a `PivotalMomentData`:
- `moment_type`: `teamfight_won` or `teamfight_lost`.
- `timestamp_secs`: the cluster's start (or first kill) timestamp.
- `description`: human-readable summary, e.g.
  *"Your team won a 3-for-1 fight near Dragon at 22:15 — you got a kill."* /
  *"Your team lost a fight at 24:30 (1 for 3) and you died."*
- `counterfactual`: filled in by enrichment (see below).
- `gold_impact`: net kill-gold swing **magnitude** (≈ `abs(your_kills - enemy_kills) * 300`
  plus objective gold if contested), stored **positive** — consistent with every existing
  moment type (the won/lost distinction is carried by `moment_type`, not the sign).

## Wiring — `sidecar/timeline_analyzer.py`

`analyze_timeline` currently dispatches and **returns early** for `JUNGLE` (→ `analyze_jungle`)
and laner roles (→ `analyze_laner`), with a generic path otherwise. Restructure so that,
regardless of role, the role-specific moments and the team-fight moments are **both**
collected, concatenated, and re-sorted by `timestamp_secs` before returning. Team fights are
role-agnostic, so they appear for laners, junglers, and the generic path alike.

## Coaching text

- **LLM path** (`claude_client.generate_coaching_notes`): no change — it is type-agnostic,
  feeding `moment_type` + `description` + a ±90s context window to Gemini for a 3-sentence note.
- **Static fallback** (`counterfactual.enrich_moments`): add `teamfight_won` and
  `teamfight_lost` branches so offline coaching reads well instead of hitting the generic
  gold-impact fallback.

## Frontend — one line

Add `teamfight_won` to `POSITIVE_TYPES` in `src/popup/constants.ts` so it renders green;
`teamfight_lost` stays in the default (yellow/negative) styling. `MomentCard` (popup) and
`GameDetail` (chat) already render any `moment_type` generically (`formatType` uppercases it)
and both consume the shared `POSITIVE_TYPES`, so no component changes are needed. `moment_type`
is typed as `string` in `src/shared/types.ts`, so no type union to extend.

## Touch points summary

Backend:
- `sidecar/teamfight_analyzer.py` — **new** detection module.
- `sidecar/timeline_analyzer.py` — restructure `analyze_timeline` to append team-fight moments
  for all roles.
- `sidecar/counterfactual.py` — add `teamfight_won` / `teamfight_lost` fallback branches.

Frontend:
- `src/popup/constants.ts` — add `teamfight_won` to `POSITIVE_TYPES`.

## Testing

`sidecar/tests/test_teamfight_analyzer.py` (new) with synthetic timelines:
- a clear won fight (e.g., 3-for-1) → one `teamfight_won` moment;
- a clear lost fight (e.g., 1-for-3) → one `teamfight_lost` moment;
- an even trade (2-for-2) → no moment;
- a 2-kill skirmish → no moment (below the ≥3 threshold);
- a fight with an `ELITE_MONSTER_KILL` in-window → objective annotated in the description;
- a fight where the player is neither killer/victim/assister → "not involved" wording;
- player involvement variants (kill, assist, death) reflected in the description.

Plus a small assertion in the existing timeline-analyzer tests that team-fight moments appear
in the combined, time-sorted output for a non-generic role.

Verification gate: `cd sidecar && python -m pytest` for the backend; `npm run typecheck`,
`npm run lint`, `npm test` for the one frontend constant change. CI must be green after push.
