# Team-Fight Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect decisive team fights from the stored match timeline and surface them as `teamfight_won` / `teamfight_lost` pivotal moments in the existing popup + chat coaching flow.

**Architecture:** A new `sidecar/teamfight_analyzer.py` clusters `CHAMPION_KILL` events into fights, scores each fight's outcome and the player's involvement (reusing the team-id helpers from `timeline_analyzer.py`), and emits `PivotalMomentData`. `analyze_timeline` is restructured to append these for every role. The moments ride the existing enrichment → persistence → UI pipeline; the only frontend change is adding `teamfight_won` to the shared `POSITIVE_TYPES` set so it styles green.

**Tech Stack:** Python 3.11 / pytest (backend); React + TypeScript / Vitest (frontend). Run pytest from inside `sidecar/`.

**Spec:** `docs/superpowers/specs/2026-06-16-team-fight-review-design.md`

---

### Task 1: Team-fight detection module

**Files:**
- Create: `sidecar/teamfight_analyzer.py`
- Test: `sidecar/tests/test_teamfight_analyzer.py`

The player is participant `1` (team 100) in every test below; the enemy team is `6`–`10`. `PivotalMomentData` is defined in `timeline_analyzer.py` with fields `timestamp_secs, moment_type, description, counterfactual, gold_impact`.

- [ ] **Step 1: Write the failing tests**

Create `sidecar/tests/test_teamfight_analyzer.py`:

```python
from teamfight_analyzer import analyze_teamfights


def _kill(ts_secs, killer, victim, assists=None):
    return {
        "type": "CHAMPION_KILL",
        "timestamp": ts_secs * 1000,
        "killerId": killer,
        "victimId": victim,
        "assistingParticipantIds": assists or [],
        "position": {"x": 0, "y": 0},
    }


def _monster(ts_secs, killer, monster):
    return {
        "type": "ELITE_MONSTER_KILL",
        "timestamp": ts_secs * 1000,
        "killerId": killer,
        "monsterType": monster,
    }


def _timeline(events):
    return {"info": {"frames": [{"events": events}]}}


def test_won_fight_emits_one_won_moment():
    # 3 enemies die within 20s, player (1) lands one of the kills -> 3-for-0 win
    tl = _timeline([_kill(600, 1, 6), _kill(605, 2, 7), _kill(610, 3, 8)])
    moments = analyze_teamfights(tl, participant_id=1)
    assert len(moments) == 1
    assert moments[0].moment_type == "teamfight_won"
    assert moments[0].timestamp_secs == 600
    assert moments[0].gold_impact == 900  # abs(3-0) * 300


def test_lost_fight_emits_one_lost_moment():
    # 3 allies die (1,2,3) within 20s -> 0-for-3 loss
    tl = _timeline([_kill(600, 6, 1), _kill(605, 7, 2), _kill(610, 8, 3)])
    moments = analyze_teamfights(tl, participant_id=1)
    assert len(moments) == 1
    assert moments[0].moment_type == "teamfight_lost"


def test_even_trade_is_skipped():
    # 2 enemy + 2 ally deaths -> 2-for-2, no moment
    tl = _timeline([_kill(600, 1, 6), _kill(603, 6, 1), _kill(606, 2, 7), _kill(609, 7, 2)])
    assert analyze_teamfights(tl, participant_id=1) == []


def test_skirmish_below_threshold_is_skipped():
    # only 2 kills -> not a team fight
    tl = _timeline([_kill(600, 1, 6), _kill(605, 2, 7)])
    assert analyze_teamfights(tl, participant_id=1) == []


def test_kills_far_apart_are_separate_clusters():
    # two 3-kill fights >20s apart -> two moments
    tl = _timeline([
        _kill(600, 1, 6), _kill(605, 2, 7), _kill(610, 3, 8),
        _kill(700, 1, 9), _kill(705, 2, 10), _kill(710, 3, 6),
    ])
    moments = analyze_teamfights(tl, participant_id=1)
    assert len(moments) == 2


def test_player_involvement_reported():
    tl = _timeline([_kill(600, 1, 6), _kill(605, 2, 7, assists=[1]), _kill(610, 8, 1)])
    # player got 1 kill, 1 assist, and died -> still a 2-for-1 win
    desc = analyze_teamfights(tl, participant_id=1)[0].description
    assert "kill" in desc and "died" in desc


def test_player_not_involved_reported():
    tl = _timeline([_kill(600, 2, 6), _kill(605, 3, 7), _kill(610, 4, 8)])
    desc = analyze_teamfights(tl, participant_id=1)[0].description
    assert "weren't involved" in desc


def test_objective_in_window_annotated():
    tl = _timeline([
        _kill(600, 1, 6), _kill(605, 2, 7), _kill(610, 3, 8),
        _monster(608, 2, "DRAGON"),
    ])
    moment = analyze_teamfights(tl, participant_id=1)[0]
    assert "near Dragon" in moment.description
    assert moment.gold_impact == 900 + 350  # kill swing + dragon gold
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd sidecar && python -m pytest tests/test_teamfight_analyzer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'teamfight_analyzer'`.

- [ ] **Step 3: Write the implementation**

Create `sidecar/teamfight_analyzer.py`:

```python
from timeline_analyzer import PivotalMomentData, TEAM_100_IDS, TEAM_200_IDS

KILL_GROUP_GAP_SECS = 20   # kills within this gap join the same fight
MIN_FIGHT_KILLS = 3        # a cluster needs at least this many kills to be a "team fight"
KILL_GOLD = 300            # approximate gold value of a champion kill

OBJECTIVE_GOLD = {"BARON_NASHOR": 900, "DRAGON": 350, "RIFTHERALD": 400}
OBJECTIVE_LABEL = {"BARON_NASHOR": "Baron", "DRAGON": "Dragon", "RIFTHERALD": "Herald"}


def _player_team_ids(participant_id: int) -> set[int]:
    return TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS


def _collect(timeline: dict):
    kills, objectives = [], []
    for frame in timeline.get("info", {}).get("frames", []):
        for event in frame.get("events", []):
            etype = event.get("type")
            if etype == "CHAMPION_KILL":
                kills.append(event)
            elif etype == "ELITE_MONSTER_KILL":
                objectives.append(event)
    kills.sort(key=lambda e: e.get("timestamp", 0))
    return kills, objectives


def _cluster(kills: list[dict]) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for kill in kills:
        ts = kill.get("timestamp", 0)
        if clusters and ts - clusters[-1][-1].get("timestamp", 0) <= KILL_GROUP_GAP_SECS * 1000:
            clusters[-1].append(kill)
        else:
            clusters.append([kill])
    return clusters


def _involvement(cluster: list[dict], participant_id: int) -> str:
    kills = assists = 0
    died = False
    for kill in cluster:
        if kill.get("killerId") == participant_id and kill.get("victimId") != participant_id:
            kills += 1
        if participant_id in kill.get("assistingParticipantIds", []):
            assists += 1
        if kill.get("victimId") == participant_id:
            died = True
    parts = []
    if kills:
        parts.append(f"got {kills} kill{'s' if kills > 1 else ''}")
    if assists:
        parts.append(f"got {assists} assist{'s' if assists > 1 else ''}")
    if died:
        parts.append("died")
    if not parts:
        return "you weren't involved"
    return "you " + " and ".join(parts)


def _objective_in_window(objectives: list[dict], start_ms: int, end_ms: int) -> str | None:
    """Return the monsterType (e.g. 'DRAGON') of a contested objective in the window, or None."""
    for obj in objectives:
        ts = obj.get("timestamp", 0)
        if start_ms <= ts <= end_ms and obj.get("monsterType") in OBJECTIVE_GOLD:
            return obj.get("monsterType")
    return None


def analyze_teamfights(timeline: dict, participant_id: int) -> list[PivotalMomentData]:
    kills, objectives = _collect(timeline)
    player_team = _player_team_ids(participant_id)
    moments: list[PivotalMomentData] = []

    for cluster in _cluster(kills):
        if len(cluster) < MIN_FIGHT_KILLS:
            continue
        your_kills = sum(1 for k in cluster if k.get("victimId", 0) not in player_team)
        their_kills = sum(1 for k in cluster if k.get("victimId", 0) in player_team)
        if your_kills == their_kills:
            continue  # skip even trades

        start_ms = cluster[0].get("timestamp", 0)
        end_ms = cluster[-1].get("timestamp", 0)
        ts = start_ms // 1000
        mins, secs = divmod(ts, 60)
        time_str = f"{mins}:{secs:02d}"

        monster = _objective_in_window(objectives, start_ms, end_ms)
        near = f" near {OBJECTIVE_LABEL[monster]}" if monster else ""
        involvement = _involvement(cluster, participant_id)

        won = your_kills > their_kills
        if won:
            moment_type = "teamfight_won"
            outcome = f"Your team won a {your_kills}-for-{their_kills} fight"
        else:
            moment_type = "teamfight_lost"
            outcome = f"Your team lost a fight ({your_kills} for {their_kills})"

        gold = abs(your_kills - their_kills) * KILL_GOLD
        if monster:
            gold += OBJECTIVE_GOLD[monster]

        moments.append(PivotalMomentData(
            timestamp_secs=ts,
            moment_type=moment_type,
            description=f"{outcome}{near} at {time_str} — {involvement}.",
            counterfactual="",
            gold_impact=gold,
        ))

    return moments
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd sidecar && python -m pytest tests/test_teamfight_analyzer.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add sidecar/teamfight_analyzer.py sidecar/tests/test_teamfight_analyzer.py
git commit -m "feat: add team-fight detection analyzer"
```

---

### Task 2: Wire team-fight moments into `analyze_timeline`

**Files:**
- Modify: `sidecar/timeline_analyzer.py:219-256` (the `analyze_timeline` function)
- Test: `sidecar/tests/test_timeline_analyzer.py`

`analyze_timeline` currently returns early for `JUNGLE` and laner roles. Restructure so role-specific moments and team-fight moments are both collected, combined, and re-sorted.

- [ ] **Step 1: Write the failing test**

Add to `sidecar/tests/test_timeline_analyzer.py`:

```python
def test_analyze_timeline_includes_teamfight_moments():
    from timeline_analyzer import analyze_timeline
    # 3 enemy deaths in a cluster -> one teamfight_won moment, merged into output
    timeline = {"info": {"frames": [{"events": [
        {"type": "CHAMPION_KILL", "timestamp": 600000, "killerId": 1, "victimId": 6,
         "assistingParticipantIds": [], "position": {"x": 0, "y": 0}},
        {"type": "CHAMPION_KILL", "timestamp": 605000, "killerId": 2, "victimId": 7,
         "assistingParticipantIds": [], "position": {"x": 0, "y": 0}},
        {"type": "CHAMPION_KILL", "timestamp": 610000, "killerId": 3, "victimId": 8,
         "assistingParticipantIds": [], "position": {"x": 0, "y": 0}},
    ]}]}}
    moments = analyze_timeline(timeline, participant_id=1, role="UNKNOWN")
    assert any(m.moment_type == "teamfight_won" for m in moments)
    # output stays sorted by timestamp
    assert [m.timestamp_secs for m in moments] == sorted(m.timestamp_secs for m in moments)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sidecar && python -m pytest tests/test_timeline_analyzer.py::test_analyze_timeline_includes_teamfight_moments -v`
Expected: FAIL — no `teamfight_won` moment in the output.

- [ ] **Step 3: Restructure `analyze_timeline`**

Replace the body of `analyze_timeline` (currently `timeline_analyzer.py:219-256`) with:

```python
def analyze_timeline(
    timeline: dict,
    participant_id: int,
    enemy_jungler_id: int | None = None,
    role: str = "UNKNOWN",
    champion: str = "Unknown",
    lane_opponent_id: int | None = None,
) -> list[PivotalMomentData]:
    if role == "JUNGLE":
        from jungle_analyzer import analyze_jungle
        moments = analyze_jungle(timeline, participant_id, enemy_jungler_id)
    elif role in ("TOP", "MIDDLE", "BOTTOM", "UTILITY"):
        from laner_analyzer import analyze_laner
        moments = analyze_laner(timeline, participant_id, lane_opponent_id, role, enemy_jungler_id)
    else:
        moments = []
        frames = timeline.get("info", {}).get("frames", [])
        for frame in frames:
            for event in frame.get("events", []):
                event_type = event.get("type")
                moment = None
                if event_type == "CHAMPION_KILL":
                    death = _classify_death(event, participant_id, enemy_jungler_id)
                    solo = _score_solo_kill(event, participant_id)
                    moment = death or solo
                elif event_type == "ELITE_MONSTER_KILL":
                    missed = score_objective_missed(event, participant_id)
                    secured = score_objective_secured(event, participant_id)
                    moment = missed or secured
                elif event_type == "BUILDING_KILL":
                    moment = _score_tower(event, participant_id)
                if moment:
                    moments.append(moment)

    from teamfight_analyzer import analyze_teamfights
    moments = list(moments) + analyze_teamfights(timeline, participant_id)
    moments.sort(key=lambda m: m.timestamp_secs)
    return moments
```

- [ ] **Step 4: Run the full timeline test file to verify it passes**

Run: `cd sidecar && python -m pytest tests/test_timeline_analyzer.py -v`
Expected: PASS (including the existing tests — the generic-path behavior is unchanged, just re-sorted).

- [ ] **Step 5: Commit**

```bash
git add sidecar/timeline_analyzer.py sidecar/tests/test_timeline_analyzer.py
git commit -m "feat: merge team-fight moments into analyze_timeline for all roles"
```

---

### Task 3: Static coaching fallback for team-fight moments

**Files:**
- Modify: `sidecar/counterfactual.py` (the `enrich_moments` function, before the final `elif not moment.counterfactual:` branch at `counterfactual.py:185`)
- Test: `sidecar/tests/test_counterfactual.py`

The LLM path (`claude_client.generate_coaching_notes`) is type-agnostic and needs no change; this only improves the offline fallback.

- [ ] **Step 1: Write the failing test**

Add to `sidecar/tests/test_counterfactual.py`:

```python
def test_teamfight_moments_get_specific_coaching():
    from counterfactual import enrich_moments
    from timeline_analyzer import PivotalMomentData
    won = PivotalMomentData(620, "teamfight_won", "Your team won a 3-for-0 fight at 10:20 — you got 1 kill.", "", 900)
    lost = PivotalMomentData(640, "teamfight_lost", "Your team lost a fight (0 for 3) at 10:40 — you died.", "", 900)
    enrich_moments([won, lost])
    assert "objective" in won.counterfactual.lower()
    assert "fight" in lost.counterfactual.lower()
    assert won.counterfactual != lost.counterfactual
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sidecar && python -m pytest tests/test_counterfactual.py::test_teamfight_moments_get_specific_coaching -v`
Expected: FAIL — both fall through to the generic `~Ng impact` fallback, so the assertions fail.

- [ ] **Step 3: Add the branches**

In `sidecar/counterfactual.py`, inside `enrich_moments`, add these two branches immediately **before** the final `elif not moment.counterfactual:` branch (currently at `counterfactual.py:185`):

```python
        elif moment.moment_type == "teamfight_won":
            moment.counterfactual = (
                "Your team won this fight — turning a numbers advantage into objectives is how "
                "fight wins become game wins. After going up bodies, immediately take the nearest "
                "Dragon, Baron, or tower while the enemy is dead and can't contest."
            )
        elif moment.moment_type == "teamfight_lost":
            moment.counterfactual = (
                "Your team lost this fight. Before committing to a 5v5, check that your team is "
                "grouped, key abilities and summoners are up, and there's a reason to fight (an "
                "objective or a pick). Forcing fights on even or unfavorable terms hands the enemy "
                "tempo and objectives."
            )
```

- [ ] **Step 4: Run the full counterfactual test file to verify it passes**

Run: `cd sidecar && python -m pytest tests/test_counterfactual.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sidecar/counterfactual.py sidecar/tests/test_counterfactual.py
git commit -m "feat: add static coaching fallback for team-fight moments"
```

---

### Task 4: Style `teamfight_won` as a positive moment (frontend)

**Files:**
- Modify: `src/popup/constants.ts`

`MomentCard` (popup) and `GameDetail` (chat) both render any `moment_type` generically and share `POSITIVE_TYPES`; adding `teamfight_won` makes it render green. `teamfight_lost` stays in the default yellow/negative styling.

- [ ] **Step 1: Add the type to `POSITIVE_TYPES`**

Edit `src/popup/constants.ts` to:

```typescript
export const POSITIVE_TYPES = new Set([
  'solo_kill', 'objective_secured', 'gank_assist', 'baron_secured', 'dragon_stack',
  'roam_kill', 'roam_assist', 'ward_kill', 'teamfight_won',
])
```

- [ ] **Step 2: Run the frontend gate**

Run: `npm run typecheck && npm run lint && npm test`
Expected: typecheck clean; lint 0 errors (only the known `react-refresh` warnings); all Vitest tests pass (rendering is generic, so no test changes needed).

- [ ] **Step 3: Commit**

```bash
git add src/popup/constants.ts
git commit -m "feat: style teamfight_won as a positive moment"
```

---

### Task 5: Full verification gate

**Files:** none (verification only)

- [ ] **Step 1: Backend gate**

Run: `cd sidecar && python -m pytest`
Expected: all tests pass.

- [ ] **Step 2: Frontend gate**

Run: `npm run typecheck && npm run lint && npm test`
Expected: clean (0 lint errors, all tests pass).

- [ ] **Step 3 (optional, recommended): End-to-end smoke**

With a configured `sidecar/.env`, run `cd sidecar && python trigger_analysis.py` against a recent match that contained a team fight, and confirm the printed moments include a `teamfight_won` / `teamfight_lost` entry with a coaching note. (This exercises the real `analyze_timeline` → `generate_coaching_notes` → persistence path.)

- [ ] **Step 4: Push and confirm CI green**

Push `master` and confirm the GitHub Actions CI run (`.github/workflows/ci.yml`) is green before considering the feature done.

---

## Notes for the implementer

- Run all pytest commands from **inside `sidecar/`** (`pytest.ini` sets `pythonpath=.`).
- `teamfight_analyzer.py` imports `PivotalMomentData` and `TEAM_100_IDS` from `timeline_analyzer` at module level; `timeline_analyzer` imports `analyze_teamfights` **lazily inside the function** (Task 2) to avoid a circular import — keep it that way (it mirrors how `jungle_analyzer` / `laner_analyzer` are imported).
- `moment_type` is typed as `string` in `src/shared/types.ts`; there is no union to extend.
- Thresholds (`KILL_GROUP_GAP_SECS`, `MIN_FIGHT_KILLS`) are module constants — easy to tune later if fights are over- or under-detected on real data.
