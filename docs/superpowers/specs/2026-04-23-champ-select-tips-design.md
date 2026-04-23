# Champ Select Tips Design Spec

## Goal

Show a transparent always-on-top overlay window during League of Legends champ select, displaying the player's personal history and patterns for the champion they just locked in — giving them actionable coaching before the game starts.

## Problem

Every other LoL analysis tool is post-game only. By the time you read "you die early on Graves in 5/7 games," the game is already over. This feature surfaces that insight at the one moment when it's actually actionable: right after you lock in your champion, while you still have 3-4 minutes before the game starts.

## Architecture

Five components, following the existing live overlay pattern exactly:

| Component | File | Role |
|---|---|---|
| LCU client | `sidecar/lcu_client.py` | Discovers lockfile, authenticates, fetches champ select session |
| Champ select monitor | `sidecar/champ_select_monitor.py` | Polls LCU, detects lock-in, builds champion stats/patterns |
| Sidecar endpoint | `sidecar/main.py` | `GET /champ-select` exposes monitor state |
| React window | `src/champ-select/App.tsx` + `index.html` | Renders stats header + pattern bullets |
| Electron wiring | `electron/main.ts` + `vite.config.ts` | Creates/destroys window based on `/champ-select` state |

## LCU Integration

The League Client (LCU) API runs locally during an active League session. Access requires:

**Lockfile discovery:** The lockfile at `C:\Riot Games\League of Legends\lockfile` (with fallback to `C:\Program Files\Riot Games\League of Legends\lockfile`) contains: `LeagueClient:PID:PORT:PASSWORD:PROTOCOL`. We parse port and password.

**Authentication:** Basic auth with username `riot` and the lockfile password, against `https://127.0.0.1:PORT`. Self-signed cert — all requests use `verify=False`.

**Champion lock-in detection:** Poll `GET /lol-champ-select/v1/session` every 2 seconds. The response contains `localPlayerCellId` and `myTeam` array. The player has locked in when:
- `myTeam[localPlayerCellId].championId > 0`
- A flattened action in `session["actions"]` satisfies: `type == "pick"`, `actorCellId == localPlayerCellId`, `completed == true`

**Champion name resolution:** Fetch `/lol-game-data/assets/v1/champion-summary.json` once and cache it. Returns `[{id, name, alias}]`. Look up by `championId` to get the display name (e.g. `"Graves"`) that matches what's stored in our database.

**No lockfile / not in champ select:** If the lockfile doesn't exist or the session endpoint returns 404/connection refused, `get_state()` returns `{"in_champ_select": false, "locked_champion": null, "champ_data": null}` and no window appears.

## Champion Data Computation

`ChampSelectMonitor._build_champ_data(champion: str)` runs two DB queries against the existing schema:

1. `get_matches(db, champion=name, last_n=20)` — returns recent matches for this champion
2. `get_pivotal_moments(db, match_ids)` — returns all moments from those matches

From these, compute:
- `games`: total match count
- `wins`: count where `result == "win"`
- `win_rate`: wins / games (0.0 if no games)
- `patterns`: top 2 most frequent negative moment types (recurring issues) + top 1 positive moment type (win condition), each as `{"label": "recurring_issue"|"win_condition", "moment_type": str, "summary": str}`

Summary format: `"{MomentLabel} in {count}/{games} games"` for issues, `"{MomentLabel} in your wins"` for win conditions. The sidecar defines its own `MOMENT_LABELS: dict[str, str]` constant in `champ_select_monitor.py` (the frontend copy in `App.tsx` is not importable from Python).

**No history case:** If `games == 0`, patterns is empty and `champ_data` includes `"no_history": true`.

## API Contract

`GET /champ-select` response:

```json
{
  "in_champ_select": true,
  "locked_champion": "Graves",
  "champ_data": {
    "games": 7,
    "wins": 4,
    "win_rate": 0.57,
    "no_history": false,
    "patterns": [
      {"label": "recurring_issue", "moment_type": "lane_death", "summary": "Early deaths in 5/7 games"},
      {"label": "recurring_issue", "moment_type": "objective_missed", "summary": "Missed dragon in 4/7 games"},
      {"label": "win_condition", "moment_type": "solo_kill", "summary": "Solo kills in your wins"}
    ]
  }
}
```

When not in champ select:
```json
{"in_champ_select": false, "locked_champion": null, "champ_data": null}
```

## React Window

`src/champ-select/App.tsx` polls `GET /champ-select` every 2 seconds. Renders nothing when `in_champ_select` is false. When true and `locked_champion` is set:

```
┌──────────────────────────────┐
│  ⬤ Graves    7 games · 57% WR│
├──────────────────────────────┤
│ ⚠ Early deaths in 5/7 games  │  ← red left border
│ ⚠ Missed dragon in 4/7 games │  ← red left border
│ ✓ Solo kills in your wins    │  ← green left border
└──────────────────────────────┘
```

No history state shows: `"No history yet for Graves — good luck!"` in grey.

Color coding:
- `recurring_issue` → red border (`border-red-500 bg-red-950/80`)
- `win_condition` → green border (`border-green-500 bg-green-950/80`)

Champion initial shown as a coloured circle (purple, matching the rest of the app).

## Electron Window

`champSelectWindow` in `electron/main.ts`:
- `transparent: true`, `frame: false`, `alwaysOnTop: true`, `focusable: false`, `skipTaskbar: true`
- Size: 320×260, positioned top-right (same as live overlay but slightly taller)
- Dev URL: `http://localhost:5173/champ-select/index.html`
- Prod URL: `file://.../renderer/champ-select/index.html`

`pollStatus` checks `/champ-select` alongside `/live`. Both `champSelectWindow` and `overlayWindow` are independent — they can coexist. Typical lifecycle:

1. Champ select starts → `champSelectWindow` created
2. Champion locked in → window shows tips
3. Game loading → `champSelectWindow` destroyed
4. Game starts → `overlayWindow` created

## Error Handling

- Lockfile missing or unreadable → `in_champ_select: false`, no window, no crash
- LCU request fails (connection refused, timeout) → same as above; monitor keeps polling silently
- Champion name not found in summary → fall back to `"Unknown"`, show no-history state
- DB query fails → `champ_data: null`, window shows error-safe empty state
- Pattern computation returns no results → show stats only, omit patterns section

## Testing

`sidecar/tests/test_champ_select_monitor.py` — 8 unit tests:
1. `test_no_state_when_not_in_champ_select` — get_state returns in_champ_select=false by default
2. `test_lock_in_detected` — _process_session sets locked_champion when championId > 0 and action completed
3. `test_no_lock_without_completed_action` — championId > 0 but action not completed → not detected
4. `test_champ_data_with_history` — _build_champ_data returns correct win_rate and patterns from DB
5. `test_champ_data_no_history` — no matches → no_history=true, patterns=[]
6. `test_pattern_top_2_issues` — only top 2 most frequent negative types returned
7. `test_win_condition_extracted` — positive moment types correctly labelled win_condition
8. `test_session_exit_resets_state` — when session returns 404, locked_champion resets to null
