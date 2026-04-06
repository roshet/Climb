# Analysis Quality Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace generic death descriptions with context-aware subtypes (tower dive, ganked, outnumbered, 1v1 loss), add positive moments (solo kills, secured objectives), and color-code popup cards green/yellow.

**Architecture:** Three files change — `sidecar/timeline_analyzer.py` gains death classification logic + positive detectors, `sidecar/counterfactual.py` gains subtype-aware coaching text, `src/popup/MomentCard.tsx` switches styling based on `momentType`. `sidecar/main.py` and `sidecar/trigger_analysis.py` gain jungler ID resolution. All changes are backward-compatible — existing tests pass with the new optional parameter.

**Tech Stack:** Python 3.11, pytest-asyncio, React 18, TypeScript, Tailwind v4

---

## Task 1: Death Classification in `timeline_analyzer.py`

**Files:**
- Modify: `sidecar/timeline_analyzer.py`
- Modify: `sidecar/tests/test_timeline_analyzer.py`

- [ ] **Step 1: Write failing tests for death subtypes**

Add to `sidecar/tests/test_timeline_analyzer.py`:

```python
def test_death_tower_dive():
    # Blue turret at (981, 10441) — death within 1000 units
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 6, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 1200, "y": 10300}}  # ~340 units from (981, 10441)
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "tower dived" in deaths[0].description

def test_death_ganked_before_14min():
    # Enemy jungler (participant 10, has smite) kills player at 5:00
    timeline = {"info": {"frames": [
        make_frame(300000, [
            {"type": "CHAMPION_KILL", "timestamp": 300000,
             "killerId": 10, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [7],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID, enemy_jungler_id=10)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "ganked" in deaths[0].description

def test_death_not_ganked_after_14min():
    # Same event but at 15:00 → outnumbered, not ganked
    timeline = {"info": {"frames": [
        make_frame(900000, [
            {"type": "CHAMPION_KILL", "timestamp": 900000,
             "killerId": 10, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [7],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID, enemy_jungler_id=10)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "ganked" not in deaths[0].description
    assert "v1" in deaths[0].description

def test_death_outnumbered():
    # 2 enemies involved (no jungler context)
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 7, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [8],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "v1" in deaths[0].description

def test_death_1v1_loss():
    # Exactly one enemy, no assists
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": 7, "victimId": PARTICIPANT_ID,
             "assistingParticipantIds": [],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    deaths = [m for m in moments if m.moment_type == "death"]
    assert len(deaths) == 1
    assert "1v1" in deaths[0].description
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_timeline_analyzer.py::test_death_tower_dive tests/test_timeline_analyzer.py::test_death_ganked_before_14min tests/test_timeline_analyzer.py::test_death_not_ganked_after_14min tests/test_timeline_analyzer.py::test_death_outnumbered tests/test_timeline_analyzer.py::test_death_1v1_loss -v
```

Expected: all 5 FAIL (description still contains "died at")

- [ ] **Step 3: Implement death classification in `timeline_analyzer.py`**

Replace the entire file with:

```python
from dataclasses import dataclass
import math

# Team 100 = participants 1-5, Team 200 = participants 6-10
TEAM_100_IDS = set(range(1, 6))
TEAM_200_IDS = set(range(6, 11))

# Gold values for objectives (approximate LoL values)
GOLD_VALUES = {
    "DRAGON": 350,
    "BARON_NASHOR": 900,
    "RIFTHERALD": 400,
    "TOWER_OUTER": 150,
    "TOWER_INNER": 250,
    "TOWER_BASE": 350,
    "INHIBITOR": 400,
    "DEATH": 300,
}

# Approximate Summoner's Rift turret positions (x, y)
BLUE_TURRETS = [
    (981, 10441), (1512, 6699), (1169, 4287),   # Top lane
    (5846, 6396), (5048, 4812), (3651, 3696),    # Mid lane
    (10504, 1029), (6919, 1483), (4281, 1241),   # Bot lane
    (1748, 2270), (2177, 1807), (1364, 1485),    # Base
]

RED_TURRETS = [
    (13866, 4357), (13327, 8143), (13604, 10474),  # Top lane
    (8955, 8510), (9767, 10175), (11134, 11207),   # Mid lane
    (4318, 13875), (8955, 13411), (10961, 13654),  # Bot lane
    (12611, 13084), (13052, 12612), (13846, 13372), # Base
]

TOWER_DIVE_RADIUS = 1000
LANING_PHASE_SECS = 840  # 14:00


@dataclass
class PivotalMomentData:
    timestamp_secs: int
    moment_type: str
    description: str
    counterfactual: str
    gold_impact: int


def _player_team(participant_id: int) -> set:
    return TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS


def _enemy_team(participant_id: int) -> set:
    return TEAM_200_IDS if participant_id in TEAM_100_IDS else TEAM_100_IDS


def _friendly_turrets(participant_id: int) -> list[tuple[int, int]]:
    return BLUE_TURRETS if participant_id in TEAM_100_IDS else RED_TURRETS


def _near_friendly_turret(position: dict, participant_id: int) -> bool:
    px, py = position.get("x", 0), position.get("y", 0)
    for tx, ty in _friendly_turrets(participant_id):
        if math.sqrt((px - tx) ** 2 + (py - ty) ** 2) < TOWER_DIVE_RADIUS:
            return True
    return False


def _classify_death(
    event: dict,
    participant_id: int,
    enemy_jungler_id: int | None,
) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None

    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    time_str = f"{mins}:{secs:02d}"
    position = event.get("position", {"x": 0, "y": 0})
    killer_id = event.get("killerId", 0)
    assisters = event.get("assistingParticipantIds", [])
    total_enemies = len(set([killer_id] + list(assisters)) - {0})

    # Priority 1: tower dive
    if _near_friendly_turret(position, participant_id):
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="death",
            description=f"You were tower dived at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    # Priority 2: ganked (laning phase only, jungler involved)
    if (
        ts < LANING_PHASE_SECS
        and enemy_jungler_id is not None
        and (killer_id == enemy_jungler_id or enemy_jungler_id in assisters)
    ):
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="death",
            description=f"You were ganked at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    # Priority 3: outnumbered
    if total_enemies >= 2:
        return PivotalMomentData(
            timestamp_secs=ts,
            moment_type="death",
            description=f"You were caught {total_enemies}v1 at {time_str}.",
            counterfactual="",
            gold_impact=GOLD_VALUES["DEATH"],
        )

    # Priority 4: 1v1 loss
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="death",
        description=f"You lost a 1v1 at {time_str}.",
        counterfactual="",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _score_objective_missed(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "ELITE_MONSTER_KILL":
        return None
    enemy_team = _enemy_team(participant_id)
    killer_id = event.get("killerId", 0)
    if killer_id not in enemy_team:
        return None
    monster = event.get("monsterType", "UNKNOWN")
    gold = GOLD_VALUES.get(monster, 300)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="objective_missed",
        description=f"Enemy team secured {monster.replace('_', ' ').title()} at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=gold,
    )


def _score_objective_secured(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "ELITE_MONSTER_KILL":
        return None
    player_team = _player_team(participant_id)
    killer_id = event.get("killerId", 0)
    if killer_id not in player_team:
        return None
    monster = event.get("monsterType", "UNKNOWN")
    gold = GOLD_VALUES.get(monster, 300)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="objective_secured",
        description=f"Your team secured {monster.replace('_', ' ').title()} at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=gold,
    )


def _score_solo_kill(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("killerId") != participant_id:
        return None
    assisters = event.get("assistingParticipantIds", [])
    if assisters:
        return None
    victim_id = event.get("victimId", 0)
    if victim_id == participant_id or victim_id == 0:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="solo_kill",
        description=f"You got a solo kill at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=300,
    )


def _score_tower(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "BUILDING_KILL":
        return None
    enemy_team = _enemy_team(participant_id)
    killer_id = event.get("killerId", 0)
    if killer_id not in enemy_team:
        return None
    tower_type = event.get("towerType", "OUTER_TURRET")
    gold = GOLD_VALUES.get(f"TOWER_{tower_type.replace('_TURRET', '')}", 150)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    lane = event.get("laneType", "").replace("_LANE", "").title()
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="tower_lost",
        description=f"Enemy took your {lane} {tower_type.replace('_', ' ').lower()} at {mins}:{secs:02d}.",
        counterfactual="",
        gold_impact=gold,
    )


def analyze_timeline(
    timeline: dict,
    participant_id: int,
    enemy_jungler_id: int | None = None,
) -> list[PivotalMomentData]:
    moments: list[PivotalMomentData] = []
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
                missed = _score_objective_missed(event, participant_id)
                secured = _score_objective_secured(event, participant_id)
                moment = missed or secured
            elif event_type == "BUILDING_KILL":
                moment = _score_tower(event, participant_id)
            if moment:
                moments.append(moment)

    moments.sort(key=lambda m: m.gold_impact, reverse=True)
    return moments[:5]
```

- [ ] **Step 4: Run the new tests**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_timeline_analyzer.py::test_death_tower_dive tests/test_timeline_analyzer.py::test_death_ganked_before_14min tests/test_timeline_analyzer.py::test_death_not_ganked_after_14min tests/test_timeline_analyzer.py::test_death_outnumbered tests/test_timeline_analyzer.py::test_death_1v1_loss -v
```

Expected: all 5 PASS

- [ ] **Step 5: Run the full test suite to confirm nothing broke**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_timeline_analyzer.py -v
```

Expected: all tests PASS (existing tests still pass because `enemy_jungler_id` defaults to `None`)

- [ ] **Step 6: Commit**

```bash
git add sidecar/timeline_analyzer.py sidecar/tests/test_timeline_analyzer.py
git commit -m "feat: smarter death classification — tower dive, ganked, outnumbered, 1v1"
```

---

## Task 2: Positive Moment Tests + Solo Kill Detection

**Files:**
- Modify: `sidecar/tests/test_timeline_analyzer.py`

- [ ] **Step 1: Write failing tests for positive moments**

Add to `sidecar/tests/test_timeline_analyzer.py`:

```python
def test_solo_kill():
    # Player kills an enemy with no assists
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": PARTICIPANT_ID, "victimId": 7,
             "assistingParticipantIds": [],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    kills = [m for m in moments if m.moment_type == "solo_kill"]
    assert len(kills) == 1
    assert "solo kill" in kills[0].description

def test_solo_kill_not_detected_with_assists():
    # Player kills enemy but had assists — not a solo kill
    timeline = {"info": {"frames": [
        make_frame(480000, [
            {"type": "CHAMPION_KILL", "timestamp": 480000,
             "killerId": PARTICIPANT_ID, "victimId": 7,
             "assistingParticipantIds": [2],
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    kills = [m for m in moments if m.moment_type == "solo_kill"]
    assert len(kills) == 0

def test_objective_secured():
    # Player's team (team 100, participants 1-5) kills Baron
    timeline = {"info": {"frames": [
        make_frame(1200000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 1200000,
             "killerId": 3,  # teammate on team 100
             "monsterType": "BARON_NASHOR",
             "position": {"x": 5007, "y": 10471}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    secured = [m for m in moments if m.moment_type == "objective_secured"]
    assert len(secured) == 1
    assert "Baron" in secured[0].description
    assert secured[0].gold_impact == 900
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_timeline_analyzer.py::test_solo_kill tests/test_timeline_analyzer.py::test_solo_kill_not_detected_with_assists tests/test_timeline_analyzer.py::test_objective_secured -v
```

Expected: all 3 FAIL

- [ ] **Step 3: Run tests again (implementation already done in Task 1)**

The implementation for both `_score_solo_kill` and `_score_objective_secured` was included in Task 1's full file rewrite. Run the tests now:

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_timeline_analyzer.py::test_solo_kill tests/test_timeline_analyzer.py::test_solo_kill_not_detected_with_assists tests/test_timeline_analyzer.py::test_objective_secured -v
```

Expected: all 3 PASS

- [ ] **Step 4: Run full timeline test suite**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_timeline_analyzer.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add sidecar/tests/test_timeline_analyzer.py
git commit -m "test: positive moment detection — solo kill and objective secured"
```

---

## Task 3: Smarter Counterfactuals in `counterfactual.py`

**Files:**
- Modify: `sidecar/counterfactual.py`
- Modify: `sidecar/tests/test_counterfactual.py`

- [ ] **Step 1: Write failing tests for new counterfactual branches**

Add to `sidecar/tests/test_counterfactual.py`:

```python
from timeline_analyzer import PivotalMomentData
from counterfactual import enrich_moments

def test_tower_dive_counterfactual():
    moments = [PivotalMomentData(
        timestamp_secs=300, moment_type="death",
        description="You were tower dived at 5:00.",
        counterfactual="", gold_impact=300
    )]
    enriched = enrich_moments(moments)
    assert "tower" in enriched[0].counterfactual.lower()

def test_ganked_counterfactual():
    moments = [PivotalMomentData(
        timestamp_secs=300, moment_type="death",
        description="You were ganked at 5:00.",
        counterfactual="", gold_impact=300
    )]
    enriched = enrich_moments(moments)
    assert "minimap" in enriched[0].counterfactual.lower() or "jungler" in enriched[0].counterfactual.lower()

def test_outnumbered_counterfactual():
    moments = [PivotalMomentData(
        timestamp_secs=480, moment_type="death",
        description="You were caught 3v1 at 8:00.",
        counterfactual="", gold_impact=300
    )]
    enriched = enrich_moments(moments)
    assert "outnumbered" in enriched[0].counterfactual.lower() or "disengage" in enriched[0].counterfactual.lower()

def test_1v1_loss_counterfactual():
    moments = [PivotalMomentData(
        timestamp_secs=480, moment_type="death",
        description="You lost a 1v1 at 8:00.",
        counterfactual="", gold_impact=300
    )]
    enriched = enrich_moments(moments)
    assert "1v1" in enriched[0].counterfactual.lower() or "matchup" in enriched[0].counterfactual.lower()

def test_solo_kill_counterfactual():
    moments = [PivotalMomentData(
        timestamp_secs=480, moment_type="solo_kill",
        description="You got a solo kill at 8:00.",
        counterfactual="", gold_impact=300
    )]
    enriched = enrich_moments(moments)
    assert len(enriched[0].counterfactual) > 0

def test_objective_secured_counterfactual():
    moments = [PivotalMomentData(
        timestamp_secs=1200, moment_type="objective_secured",
        description="Your team secured Baron Nashor at 20:00.",
        counterfactual="", gold_impact=900
    )]
    enriched = enrich_moments(moments)
    assert len(enriched[0].counterfactual) > 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_counterfactual.py::test_tower_dive_counterfactual tests/test_counterfactual.py::test_ganked_counterfactual tests/test_counterfactual.py::test_outnumbered_counterfactual tests/test_counterfactual.py::test_1v1_loss_counterfactual tests/test_counterfactual.py::test_solo_kill_counterfactual tests/test_counterfactual.py::test_objective_secured_counterfactual -v
```

Expected: all 6 FAIL

- [ ] **Step 3: Rewrite `counterfactual.py`**

Replace the entire file with:

```python
from timeline_analyzer import PivotalMomentData


def _counterfactual_for_death(moment: PivotalMomentData) -> str:
    desc = moment.description.lower()

    if "tower dived" in desc:
        return (
            "Enemies who dive your tower are gambling — if you can avoid the all-in and let "
            "the tower do damage, it's often a losing trade for them. Positioning away from "
            "the tower edge and having an escape ready denies the dive."
        )

    if "ganked" in desc:
        return (
            "Your opponent had jungle help here. Check your minimap before extending — if "
            "the enemy jungler isn't visible on the map, assume they could be in your lane. "
            "Ward tri-bush and river to spot this earlier."
        )

    if "v1" in desc:
        return (
            "Fighting outnumbered is almost never correct. Disengage early when you see "
            "multiple enemies collapsing — the longer you stay, the worse your odds. "
            "A flash to safety is worth more than trying to trade back."
        )

    if "1v1" in desc:
        return (
            "You lost a straight-up 1v1. Consider whether your champion wins this matchup "
            "at your current item level, or play for farm over fighting until you have "
            "your power spike."
        )

    # Fallback for any unclassified death
    mins = moment.timestamp_secs // 60
    if mins < 10:
        return (
            f"Dying at {mins} minutes in the early game is high cost — you missed CS, "
            f"XP, and gave your opponent a lead. Playing safer or recalling when low "
            f"would have preserved your lane advantage."
        )
    elif mins < 20:
        return (
            f"This death at {mins} minutes likely disrupted your team's mid-game tempo. "
            f"Fights in this window often decide which team gets the first major objective. "
            f"Consider whether the fight was necessary or if backing was the safer call."
        )
    else:
        return (
            f"Late-game deaths at {mins} minutes can be game-ending — respawn timers are long "
            f"and the enemy can convert a kill into an inhibitor or Baron. "
            f"Staying grouped and avoiding solo plays is the highest-value choice here."
        )


def _counterfactual_for_objective_missed(moment: PivotalMomentData) -> str:
    gold = moment.gold_impact
    desc_lower = moment.description.lower()
    if "baron" in desc_lower:
        return (
            f"Baron Nashor is the most impactful objective in the game (~{gold}g team advantage + buff). "
            f"When Baron spawns, your team should be grouped and contesting or forcing the enemy away. "
            f"Securing or denying Baron often determines the winner."
        )
    elif "dragon" in desc_lower:
        return (
            f"Each Dragon soul stack is worth roughly {gold}g in stats and compounds over the game. "
            f"Letting the enemy stack Dragons for free accelerates their scaling. "
            f"Contesting Dragon when you have lane priority is a high-value play."
        )
    else:
        return (
            f"Your team missed an objective worth ~{gold}g in team advantage. "
            f"Grouping around spawn timers and converting lane pressure into objectives "
            f"is one of the highest-leverage macro habits to build."
        )


def _counterfactual_for_tower(moment: PivotalMomentData) -> str:
    gold = moment.gold_impact
    return (
        f"Losing this tower gave the enemy ~{gold}g and opened a new avenue into your base. "
        f"Towers are best defended by not giving the enemy free time to siege — "
        f"rotating when you see your laner backing or being outnumbered prevents this."
    )


def _counterfactual_for_solo_kill(_moment: PivotalMomentData) -> str:
    return (
        "Clean 1v1 — you identified the right window to commit and won the trade. "
        "Look for similar patterns where your opponent is low or out of cooldowns."
    )


def _counterfactual_for_objective_secured(_moment: PivotalMomentData) -> str:
    return (
        "Good macro — converting map pressure into an objective is how leads become wins. "
        "Keep looking for these trades."
    )


def enrich_moments(moments: list[PivotalMomentData]) -> list[PivotalMomentData]:
    for moment in moments:
        if moment.moment_type == "death":
            moment.counterfactual = _counterfactual_for_death(moment)
        elif moment.moment_type == "objective_missed":
            moment.counterfactual = _counterfactual_for_objective_missed(moment)
        elif moment.moment_type == "tower_lost":
            moment.counterfactual = _counterfactual_for_tower(moment)
        elif moment.moment_type == "solo_kill":
            moment.counterfactual = _counterfactual_for_solo_kill(moment)
        elif moment.moment_type == "objective_secured":
            moment.counterfactual = _counterfactual_for_objective_secured(moment)
        elif not moment.counterfactual:
            moment.counterfactual = f"This event had an estimated ~{moment.gold_impact}g impact on the game outcome."
    return moments
```

- [ ] **Step 4: Run the new counterfactual tests**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/test_counterfactual.py -v
```

Expected: all tests PASS (11 total — 5 existing + 6 new)

- [ ] **Step 5: Commit**

```bash
git add sidecar/counterfactual.py sidecar/tests/test_counterfactual.py
git commit -m "feat: context-aware counterfactuals — tower dive, ganked, outnumbered, 1v1, positive moments"
```

---

## Task 4: Resolve Enemy Jungler ID in `main.py` and `trigger_analysis.py`

**Files:**
- Modify: `sidecar/main.py`
- Modify: `sidecar/trigger_analysis.py`

- [ ] **Step 1: Update `run_post_game_analysis()` in `sidecar/main.py`**

Find the section after `participant_index` is computed and replace the `analyze_timeline` call:

```python
        participant_index = participants.index(participant) + 1  # 1-indexed

        # Resolve enemy jungler (has Smite, summoner spell ID 11)
        SMITE_ID = 11
        player_team_ids = TEAM_100_IDS if participant_index in TEAM_100_IDS else TEAM_200_IDS
        enemy_participants = [p for p in participants if participants.index(p) + 1 not in player_team_ids]
        enemy_jungler = next(
            (p for p in enemy_participants if p.get("summoner1Id") == SMITE_ID or p.get("summoner2Id") == SMITE_ID),
            None,
        )
        enemy_jungler_id = participants.index(enemy_jungler) + 1 if enemy_jungler else None

        save_match(db, { ... })  # unchanged

        moments = analyze_timeline(timeline_data, participant_id=participant_index, enemy_jungler_id=enemy_jungler_id)
```

Also add the import at the top of `main.py`:

```python
from timeline_analyzer import analyze_timeline, TEAM_100_IDS
```

The full updated `run_post_game_analysis` block (replace lines 55–102 in main.py):

```python
async def run_post_game_analysis():
    player = get_player(db)
    if not player:
        return
    try:
        match_ids = await riot.get_recent_match_ids(player.riot_puuid, count=1)
        if not match_ids:
            return
        match_id = match_ids[0]
        existing = get_matches(db, last_n=1)
        if existing and existing[0].match_id == match_id:
            return  # already analyzed

        match_data = await riot.get_match(match_id)
        timeline_data = await riot.get_timeline(match_id)

        info = match_data["info"]
        puuid = player.riot_puuid
        participants = info["participants"]
        participant = next(p for p in participants if p["puuid"] == puuid)
        participant_index = participants.index(participant) + 1  # 1-indexed

        # Resolve enemy jungler by Smite (summoner spell ID 11)
        SMITE_ID = 11
        player_team_ids = TEAM_100_IDS if participant_index in TEAM_100_IDS else TEAM_200_IDS
        enemy_participants = [p for p in participants if participants.index(p) + 1 not in player_team_ids]
        enemy_jungler = next(
            (p for p in enemy_participants if p.get("summoner1Id") == SMITE_ID or p.get("summoner2Id") == SMITE_ID),
            None,
        )
        enemy_jungler_id = participants.index(enemy_jungler) + 1 if enemy_jungler else None

        save_match(db, {
            "match_id": match_id,
            "played_at": datetime.fromtimestamp(info["gameStartTimestamp"] / 1000, tz=timezone.utc),
            "champion": participant["championName"],
            "role": participant.get("teamPosition", "UNKNOWN"),
            "result": "win" if participant["win"] else "loss",
            "duration_secs": info["gameDuration"],
            "kda": f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
            "cs": participant["totalMinionsKilled"],
            "gold_earned": participant["goldEarned"],
            "vision_score": participant["visionScore"],
            "raw_timeline": timeline_data,
        })

        moments = analyze_timeline(timeline_data, participant_id=participant_index, enemy_jungler_id=enemy_jungler_id)
        enriched = enrich_moments(moments)
        save_pivotal_moments(db, match_id, [
            {
                "timestamp_secs": m.timestamp_secs,
                "moment_type": m.moment_type,
                "description": m.description,
                "counterfactual": m.counterfactual,
                "gold_impact": m.gold_impact,
            }
            for m in enriched
        ])

        set_pending_popup(db, match_id=match_id)
    except Exception as e:
        print(f"[watcher] Error during post-game analysis: {e}")
```

- [ ] **Step 2: Update `trigger_analysis.py`**

Replace the entire file:

```python
import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from database import init_db, get_player, Session, set_pending_popup, save_match, save_pivotal_moments
from riot_client import RiotClient
from timeline_analyzer import analyze_timeline, TEAM_100_IDS
from counterfactual import enrich_moments
from datetime import datetime, timezone

SMITE_ID = 11

async def main():
    engine = init_db('analyst.db')
    db = Session(engine)
    player = get_player(db)
    riot = RiotClient(api_key=os.environ['RIOT_API_KEY'], region=os.environ.get('REGION', 'NA1'))

    match_id = 'NA1_5531314507'
    print(f'Fetching match {match_id}...')
    match_data = await riot.get_match(match_id)
    timeline_data = await riot.get_timeline(match_id)

    info = match_data['info']
    participants = info['participants']
    participant = next(p for p in participants if p['puuid'] == player.riot_puuid)
    participant_index = participants.index(participant) + 1

    player_team_ids = TEAM_100_IDS if participant_index in TEAM_100_IDS else set(range(6, 11))
    enemy_participants = [p for p in participants if participants.index(p) + 1 not in player_team_ids]
    enemy_jungler = next(
        (p for p in enemy_participants if p.get("summoner1Id") == SMITE_ID or p.get("summoner2Id") == SMITE_ID),
        None,
    )
    enemy_jungler_id = participants.index(enemy_jungler) + 1 if enemy_jungler else None
    print(f'Enemy jungler participant ID: {enemy_jungler_id}')

    save_match(db, {
        'match_id': match_id,
        'played_at': datetime.fromtimestamp(info['gameStartTimestamp'] / 1000, tz=timezone.utc),
        'champion': participant['championName'],
        'role': participant.get('teamPosition', 'UNKNOWN'),
        'result': 'win' if participant['win'] else 'loss',
        'duration_secs': info['gameDuration'],
        'kda': f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
        'cs': participant['totalMinionsKilled'],
        'gold_earned': participant['goldEarned'],
        'vision_score': participant['visionScore'],
        'raw_timeline': timeline_data,
    })

    moments = analyze_timeline(timeline_data, participant_id=participant_index, enemy_jungler_id=enemy_jungler_id)
    enriched = enrich_moments(moments)
    save_pivotal_moments(db, match_id, [
        {'timestamp_secs': m.timestamp_secs, 'moment_type': m.moment_type,
         'description': m.description, 'counterfactual': m.counterfactual,
         'gold_impact': m.gold_impact}
        for m in enriched
    ])
    set_pending_popup(db, match_id=match_id)

    print(f'Champion: {participant["championName"]}, Result: {"win" if participant["win"] else "loss"}')
    print(f'Moments found: {len(enriched)}')
    for m in enriched:
        print(f'  [{m.moment_type}] {m.description}')
    await riot.close()

asyncio.run(main())
```

- [ ] **Step 3: Verify sidecar imports cleanly**

```bash
cd sidecar && venv/Scripts/python -c "import main; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 4: Run full test suite**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add sidecar/main.py sidecar/trigger_analysis.py
git commit -m "feat: resolve enemy jungler via Smite for gank detection"
```

---

## Task 5: Color-Code `MomentCard.tsx`

**Files:**
- Modify: `src/popup/MomentCard.tsx`

- [ ] **Step 1: Update `MomentCard.tsx` to use `momentType` for styling**

Replace the entire file:

```tsx
interface MomentCardProps {
  timestampSecs: number
  momentType: string
  description: string
  counterfactual: string
  goldImpact: number
}

const POSITIVE_TYPES = new Set(['solo_kill', 'objective_secured'])

export function MomentCard({ timestampSecs, momentType, description, counterfactual, goldImpact }: MomentCardProps) {
  const mins = Math.floor(timestampSecs / 60)
  const secs = timestampSecs % 60
  const time = `${mins}:${secs.toString().padStart(2, '0')}`
  const isPositive = POSITIVE_TYPES.has(momentType)

  return isPositive ? (
    <div className="border border-green-500/30 bg-green-500/5 rounded-lg p-3 mb-2">
      <div className="flex items-start gap-2">
        <span className="text-green-400 text-sm font-mono mt-0.5">✓ {time}</span>
        <div>
          <p className="text-white text-sm">{description}</p>
          <p className="text-gray-400 text-xs mt-1">{counterfactual}</p>
          <p className="text-green-500/70 text-xs mt-1">~{goldImpact}g impact</p>
        </div>
      </div>
    </div>
  ) : (
    <div className="border border-yellow-500/30 bg-yellow-500/5 rounded-lg p-3 mb-2">
      <div className="flex items-start gap-2">
        <span className="text-yellow-400 text-sm font-mono mt-0.5">⚠ {time}</span>
        <div>
          <p className="text-white text-sm">{description}</p>
          <p className="text-gray-400 text-xs mt-1">{counterfactual}</p>
          <p className="text-yellow-500/70 text-xs mt-1">~{goldImpact}g impact</p>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd c:/Users/rohan/OneDrive/Desktop/NewProject && npx tsc --noEmit
```

Expected: zero errors

- [ ] **Step 3: Commit**

```bash
git add src/popup/MomentCard.tsx
git commit -m "feat: color-code popup cards — green for wins, yellow for mistakes"
```

---

## Task 6: Final Verification

**Files:** None (verification only)

- [ ] **Step 1: Run the complete test suite**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/ -v
```

Expected: all tests PASS (existing 25 + new 14 = 39 total)

- [ ] **Step 2: Run trigger_analysis.py to manually verify output**

First update the Riot API key in `sidecar/.env` if it has expired (dev keys expire every 24h).

```bash
cd sidecar && venv/Scripts/python trigger_analysis.py
```

Expected output includes death subtype labels like `[death] You were ganked at 3:22.` or `[death] You lost a 1v1 at 5:03.` and any positive moments if present.

- [ ] **Step 3: Restart the app and verify popup**

In PowerShell from `NewProject`:
```powershell
npm run dev
```

Wait for sidecar to start, then the popup should appear within 5 seconds showing the re-analyzed moments with color coding.
