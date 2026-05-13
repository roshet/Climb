# LoL Personal Analyst — Design Spec
**Date:** 2026-04-03
**Status:** Approved

---

## Overview

A desktop application that acts as a personal League of Legends analyst. It automatically detects when a game ends, surfaces the 3-5 pivotal decision moments that decided the game (with "what if" counterfactual context), and provides a persistent chat interface where the player can ask natural language questions about their match history.

**Target user:** Single player (your own account), with a path to supporting any summoner name later.

**Core gap it fills:** Existing tools (op.gg, Mobalytics, iTero) show you *what* happened. This tells you *why it mattered* and *what you could have done differently* at each specific moment — and lets you have a real conversation about your patterns over time. Meeko.ai attempted the conversational angle but shut down, leaving the space open.

---

## Architecture

### Stack
- **Desktop shell:** Electron
- **UI:** React + TypeScript (dark theme)
- **Analysis engine:** FastAPI (Python) running as a local sidecar
- **Database:** SQLite (local, on-disk)
- **AI:** Claude API (Anthropic) with tool use
- **Data source:** Riot Games API (match-v5, timeline-v5, Live Client Data API)

### System Diagram

```
┌─────────────────────────────────────────────┐
│              ELECTRON SHELL                  │
│                                              │
│  ┌─────────────┐    ┌──────────────────┐    │
│  │  Chat UI    │    │  Post-Game Popup │    │
│  │  (React)    │    │  (React)         │    │
│  └──────┬──────┘    └────────┬─────────┘    │
│         │ HTTP localhost      │              │
│  ┌──────▼────────────────────▼──────────┐   │
│  │         FastAPI Sidecar (Python)      │   │
│  │                                       │   │
│  │  ┌──────────┐  ┌──────────────────┐  │   │
│  │  │ Riot API │  │ Timeline Analyzer │  │   │
│  │  │ Client   │  │ + Counterfactual  │  │   │
│  │  └──────────┘  └──────────────────┘  │   │
│  │                                       │   │
│  │  ┌──────────┐  ┌──────────────────┐  │   │
│  │  │ Claude   │  │ SQLite Database  │  │   │
│  │  │ API      │  │ (match history)  │  │   │
│  │  └──────────┘  └──────────────────┘  │   │
│  └───────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### Communication
- Electron spawns the FastAPI sidecar process on startup and kills it on quit
- React UI communicates with FastAPI over `localhost` HTTP only — no Electron IPC complexity
- FastAPI owns all data, logic, and external API calls
- Electron handles system tray, native window management, and popup triggering
- **Popup notification:** Electron's main process polls a FastAPI `/status` endpoint every 5 seconds. When FastAPI completes a new analysis, it sets a `pending_popup` flag in SQLite. Electron sees the flag, fetches the analysis, shows the popup window, and clears the flag. No WebSocket complexity needed.

---

## Features

### 1. Game End Detection
- FastAPI polls Riot's Live Client Data API (`localhost:2999`) while a game is active
- When the connection drops, the game has ended
- Triggers the post-game analysis pipeline automatically
- No manual input required from the player

### 2. Post-Game Analysis Pipeline

```
Game Ends
    │
    ▼
FastAPI detects localhost:2999 drops
    │
    ▼
Fetch match data from Riot API
├── match-v5 (KDA, CS, items, damage summary)
└── timeline-v5 (60s frames + all events: kills, objectives, gold)
    │
    ▼
Timeline Analyzer
├── Score every event by game-state impact
│   (gold swings, objectives taken/missed, deaths at critical moments)
├── Rank and surface top 3-5 pivotal moments
└── For each moment, run Counterfactual Engine:
    "You recalled here. 68% of winning players in this
     matchup stayed and took the tower. Est. cost: 400g."
    │
    ▼
Claude API generates natural language summary
├── Plain English explanation of each pivotal moment
└── One "biggest takeaway" connecting this game to your broader patterns
    │
    ▼
Store everything in SQLite (including raw timeline for re-analysis)
    │
    ▼
Electron popup appears (bottom-right corner)
```

### 3. Post-Game Popup UI

Appears automatically after each game. Lives in the bottom-right corner. Auto-dismisses after 60 seconds if untouched.

```
┌─────────────────────────────────────────┐
│  Game Analysis — Jinx (Loss, 23 min)  ✕ │
├─────────────────────────────────────────┤
│  PIVOTAL MOMENTS                        │
│                                         │
│  ⚠ 14:32 — You recalled with 80% HP    │
│  Tower was at 200HP. Staying wins it.   │
│  Est. cost: ~400g + pressure            │
│                                         │
│  ⚠ 18:07 — Solo fight at dragon pit    │
│  Enemy jungler was 47s away. Safe play  │
│  was to wait for your team.             │
│                                         │
│  ⚠ 22:15 — Missed Baron call           │
│  Your team had 3k gold lead. 6/10       │
│  similar situations end in Baron.       │
├─────────────────────────────────────────┤
│  BIGGEST TAKEAWAY                       │
│  You're over-extending when ahead.      │
│  This pattern appears in 6 of your      │
│  last 10 losses.                        │
├─────────────────────────────────────────┤
│        [Ask about this game →]          │
└─────────────────────────────────────────┘
```

### 4. Persistent Chat Interface

Accessible from the system tray at any time. Pre-seeded with game context when opened from the popup.

```
┌─────────────────────────────────────────┐
│  LoL Analyst          [Recent Games ▾]  │
├─────────────────────────────────────────┤
│                                         │
│  [AI]: Your last 10 games on Jinx show  │
│  a pattern — you win laning phase 70%   │
│  of the time but convert that to a win  │
│  only 40% of the time...                │
│                                         │
│  [You]: What should I focus on first?   │
│                                         │
│  [AI]: Your #1 priority is objective    │
│  timing. In 7 of your last 10 losses... │
│                                         │
├─────────────────────────────────────────┤
│  Ask anything about your games...   [↑] │
└─────────────────────────────────────────┘
```

Claude uses **tool calls** to query SQLite on demand rather than receiving all match data upfront. This keeps context focused and responses fast.

Available Claude tools:
- `get_matches(filters)` — query matches by champion, result, date range, etc.
- `get_pivotal_moments(match_ids)` — retrieve analyzed moments for specific games
- `get_champion_stats(champion, last_n)` — aggregated stats for a champion over N games

Conversation history persists across sessions in SQLite. When opened from the popup, the chat is pre-seeded with that game's match context.

---

## Counterfactual Engine

The counterfactual engine compares player decisions against heuristic rules grounded in Riot data. This is **not** full ML at v1 — it uses rule-based analysis informed by:

- Gold value of objectives at each time window (well-documented in LoL theory)
- Statistical outcomes of decision types at the player's rank
- Timeline data patterns (e.g. recalling with objectives available nearby)

Example rule: *"If a player recalls within 30 seconds of a tower dropping below 20% HP and the enemy is not nearby, flag as a missed opportunity. Estimate gold cost as remaining tower HP converted to gold value."*

This is honest, explainable, and useful at v1. The architecture supports upgrading to ML-based counterfactuals later without redesigning the system.

---

## Data Storage (SQLite Schema)

```sql
-- Core match record
matches (
    match_id        TEXT PRIMARY KEY,
    played_at       DATETIME,
    champion        TEXT,
    role            TEXT,
    result          TEXT,        -- 'win' | 'loss'
    duration_secs   INTEGER,
    kda             TEXT,        -- "5/2/8"
    cs              INTEGER,
    gold_earned     INTEGER,
    vision_score    INTEGER,
    raw_timeline    JSON         -- full Riot timeline stored for re-analysis
)

-- Pivotal moments extracted per game
pivotal_moments (
    id              INTEGER PRIMARY KEY,
    match_id        TEXT REFERENCES matches,
    timestamp_secs  INTEGER,
    moment_type     TEXT,        -- 'death' | 'objective_missed' | 'recall' | 'fight'
    description     TEXT,        -- plain English description
    counterfactual  TEXT,        -- "what if" explanation
    gold_impact     INTEGER      -- estimated gold cost of the decision
)

-- Chat history
chat_messages (
    id              INTEGER PRIMARY KEY,
    session_id      TEXT,
    match_id        TEXT,        -- NULL if not about a specific game
    role            TEXT,        -- 'user' | 'assistant'
    content         TEXT,
    created_at      DATETIME
)

-- Player profile (single row)
player (
    summoner_name   TEXT,
    riot_puuid      TEXT,
    region          TEXT,
    last_synced_at  DATETIME
)
```

`raw_timeline` is stored as JSON so games can be re-analyzed later without re-fetching from the Riot API.

---

## Project Structure

```
NewProject/
├── electron/               # Electron main process
│   ├── main.ts             # App entry, sidecar spawning, tray
│   └── preload.ts          # Renderer bridge
├── src/                    # React UI
│   ├── chat/               # Persistent chat window
│   └── popup/              # Post-game popup window
├── sidecar/                # Python FastAPI backend
│   ├── main.py             # FastAPI app entry
│   ├── riot_client.py      # Riot API wrapper
│   ├── timeline_analyzer.py # Pivotal moment detection
│   ├── counterfactual.py   # "What if" engine
│   ├── claude_client.py    # Claude API + tool definitions
│   └── database.py         # SQLite models + queries
├── docs/
│   └── superpowers/specs/
│       └── 2026-04-03-lol-analyst-design.md
└── package.json
```

---

## Out of Scope (v1)

- Support for multiple summoner accounts
- Replay file (`.rofl`) parsing — using Riot API timeline data instead
- ML-based counterfactual modeling — heuristic rules at v1
- Mobile or web version
- Sharing or social features

---

## Success Criteria

- Game end is detected automatically within 60 seconds of the game ending
- Post-game popup appears with 3-5 pivotal moments, each with a counterfactual
- Chat correctly answers natural language questions about match history using real data
- All data stored locally — no external database, no accounts required beyond Riot API key
