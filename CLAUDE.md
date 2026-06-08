# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Climb is a Windows desktop app (Electron + React frontend, Python FastAPI "sidecar"
backend) that coaches League of Legends players. The Electron main process spawns and
supervises the Python sidecar on `localhost:8765`; all five React windows talk to the
sidecar over HTTP. Version 0.1.0; package name `lol-analyst`, product name `Climb`.

## Commands

Frontend / Electron (run from repo root):
- `npm run dev` — compiles electron TS, then runs Vite + tsc-watch + Electron concurrently (live reload).
- `npm run build` — `vite build` (renderer → `dist/renderer/`) + `tsc -p tsconfig.electron.json` (→ `dist/electron/`).
- `npm run package` — build + `electron-builder` → NSIS installer in `dist-installer/`.
- There are no `lint`/`typecheck`/`test` npm scripts yet.

Backend (run from `sidecar/`):
- Install: `pip install -r requirements.txt`
- Run standalone: `python -m uvicorn main:app --port 8765` (Electron normally spawns this).
- Test all: `python -m pytest`
- Single test: `python -m pytest tests/test_pattern_detector.py::test_detects_recurring_issue -v`
- `pytest.ini` sets `pythonpath=.`, `testpaths=tests`, `asyncio_mode=auto` — run pytest from inside `sidecar/`.

## Configuration

The sidecar reads config from environment variables, injected by the Electron main process:
`RIOT_API_KEY`, `GEMINI_API_KEY`, `REGION` (e.g. `NA1`), `DB_PATH`. For standalone backend
dev, put these in `sidecar/.env` (loaded via python-dotenv). NOTE: `.env.example` currently
lists `ANTHROPIC_API_KEY` but the code uses `GEMINI_API_KEY` — use `GEMINI_API_KEY`.
In the packaged app, user config lives in `%APPDATA%/Climb/config.json` (written by the
setup window) and the DB in `%APPDATA%/Climb/analyst.db`. In dev the DB is `sidecar/analyst.db`.

## Architecture

Data flow: League client running → Riot/LCU/Live-Client data fetched → stored in SQLite →
analyzed (timeline + role analyzers + Gemini) → served via FastAPI → rendered in React windows.

Three external data sources (don't confuse them):
- **Riot Web API** (`riot_client.py`): match-v5 + timeline-v5 + account-v1. Public internet, needs API key + TLS.
- **Live Client Data API** (`127.0.0.1:2999`): in-game events / death detection. Self-signed cert (`verify=False` is correct here only).
- **LCU** (`lcu_client.py`): champion-select session + champion-id resolution. Self-signed cert.

Backend (`sidecar/`):
- `main.py` — FastAPI app, ~15 REST endpoints, lifespan-managed background tasks
  (`game_end_watcher`, `LiveGameMonitor`, `ChampSelectMonitor`, backfill).
- `database.py` — SQLAlchemy models: `matches` (incl. `raw_timeline` JSON, `lane_opponent_champion`),
  `pivotal_moments`, `chat_messages`, `player`, `app_state`. Migrations are ad-hoc `ALTER TABLE` in `init_db()`.
- `timeline_analyzer.py` (base) + `laner_analyzer.py` + `jungle_analyzer.py` — role-aware
  pivotal-moment detection (deaths, objectives, towers, CS/gold diffs, backs, vision).
- `pattern_detector.py` — cross-game recurring issues / win conditions (≥3 games, ±10% WR).
- `claude_client.py` — **named misleadingly; it uses Google Gemini (`google.genai`,
  `gemini-2.5-flash`), not Anthropic.** Tool-use chat (`get_matches`, `get_pivotal_moments`,
  `get_champion_stats`), coaching-note generation, and focus-card sentence generation.
- `counterfactual.py` — static fallback coaching when the LLM is unavailable.
- `backfill.py` — first-run history backfill (respects 429s, skips already-analyzed).
- `improvement_tracker.py`, `champ_select_monitor.py`, `live_game_monitor.py`, `riot_client.py`, `lcu_client.py`.

Frontend (`src/`), five Vite entry points (see `vite.config.ts`), each its own window:
- `chat/` — main window: chat (LLM tool-use), match history, patterns, focus card, trend chart.
- `popup/` — 60s auto-closing post-game summary (moments + improvement + focus result).
- `champ-select/` — transparent click-through overlay during pick/ban (champion stats, patterns, matchups, coaching sentence).
- `overlay/` — transparent click-through in-game alert overlay (`/live`).
- `setup/` — first-run config (API keys + Riot ID), talks to main via IPC.

Electron (`electron/`):
- `main.ts` — spawns/supervises the sidecar (auto-restart), creates/destroys windows based
  on `/status`, `/live`, `/champ-select` polling, loads/saves `config.json`.
- `preload.ts` — context-isolated bridge: exposes `window.sidecar.port` and `window.electron` IPC.

## Conventions & gotchas

- Each React window currently redefines its own copies of shared types (`Pattern`,
  `MatchupEntry`, `Focus`) and its own `fetch`+poll logic — there is no shared types/api
  module yet. Keep new shapes consistent with the backend JSON until that's consolidated.
- Windows talk to the backend via `http://localhost:${window.sidecar.port}` (default 8765).
- `docs/superpowers/plans/` and `docs/superpowers/specs/` hold the dated design history;
  new features here have historically started with a spec + plan there.
