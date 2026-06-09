# Climb

A desktop coaching app for League of Legends. Climb backfills your recent match
history from the Riot API, runs role-aware timeline analysis to find the pivotal
moments in each game, enriches them with AI coaching, detects cross-game
patterns, and surfaces it all through in-client overlays and a chat coach.

> Windows desktop app — Electron + React (renderer) with a Python FastAPI
> "sidecar" backend the Electron process spawns and supervises.

## Features

- **Post-game popup** — an auto-closing summary of each game's key moments, the gold each mistake cost, and how you did on your focus.
- **Champion-select overlay** — your stats, recurring patterns, tough matchups, and a coaching tip for the champion you locked.
- **In-game overlay** — lightweight, click-through alerts for objectives, deaths, and pattern reminders.
- **Focus card** — your top recurring issue with a coaching sentence and a clean-game streak.
- **Chat coach** — ask about your history, patterns, and specific games; the model uses tools to pull your real data.
- **Match history & trends** — filter by champion, see gold-lost / mistake trends over time.

## Prerequisites

- **Node.js** 22+ (developed on 24)
- **Python** 3.11
- A **Riot API key** — https://developer.riotgames.com/
- A **Google Gemini API key** — https://aistudio.google.com/apikey
- The **League of Legends client** (for the live/champ-select overlays)

## Getting started (development)

```bash
# 1. Install dependencies
npm install
pip install -r requirements.txt

# 2. Run the full app (Electron spawns the sidecar)
npm run dev
```

On first launch a setup window collects your Riot ID and API keys; they're saved
to `%APPDATA%/Climb/config.json` and injected into the sidecar as environment
variables.

### Running the backend on its own

The sidecar is a standalone FastAPI app. For backend-only work, create
`sidecar/.env` (see `.env.example`) and run:

```bash
cd sidecar
python -m uvicorn main:app --port 8765
```

Required environment variables: `RIOT_API_KEY`, `GEMINI_API_KEY`, `REGION`
(e.g. `NA1`), and optionally `DB_PATH`.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite + Electron with live reload (spawns the sidecar) |
| `npm run build` | Build the renderer and compile the Electron code |
| `npm run package` | Build + `electron-builder` → NSIS installer in `dist-installer/` |
| `npm run typecheck` | `tsc --noEmit` over the renderer + Electron code |
| `npm run lint` | ESLint over the TypeScript/React code |
| `npm test` | Vitest (frontend unit/component tests) |

Backend tests:

```bash
cd sidecar
python -m pytest                 # all tests
python -m pytest tests/test_pattern_detector.py -v   # a single file
```

CI (`.github/workflows/ci.yml`) runs the backend tests plus the frontend
typecheck, lint, test, and build on every push and pull request.

## Project layout

```
electron/    Electron main process + preload (spawns the sidecar, manages windows)
src/         React renderer — one folder per window (chat, popup, champ-select, overlay, setup)
src/shared/  Shared API types, a typed sidecar client, and constants
sidecar/     Python FastAPI backend, SQLite, Riot/LCU/LLM integrations, analyzers, tests
docs/        Design specs and implementation plans
```

For a deeper tour of the architecture and data flow, see
[CLAUDE.md](./CLAUDE.md).

## How it works (high level)

```
League client ──► Riot Web API ─┐
              └─► LCU / Live API ─┴─► sidecar (FastAPI)
                                        ├─ store matches + timelines (SQLite)
                                        ├─ role-aware timeline analysis → pivotal moments
                                        ├─ Gemini coaching + cross-game pattern detection
                                        └─ REST API ──► Electron windows (React)
```

Three external data sources, kept distinct: the **Riot Web API** (match-v5 /
timeline-v5, over the internet), the **Live Client Data API** (`127.0.0.1:2999`,
in-game events), and the **LCU** (champion select). The latter two serve
self-signed certs on loopback.

## License

Unlicensed / personal project.
