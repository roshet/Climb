# Match History + Game Detail View Design

## Goal

Add a browsable match history to the main chat window so users can review any past game's pivotal moments without waiting for the post-game popup.

## Architecture

**Frontend — three new components, one modified:**

- `src/chat/App.tsx` — gains `tab: 'chat' | 'history'` state and `selectedMatchId: string | null` state. A tab bar (Chat | History) replaces the current plain header. Renders `HistoryList` or `GameDetail` when on the History tab; renders the existing chat view when on the Chat tab. `chatMatchId` becomes mutable state (was URL-only) so "Ask about this game →" can set it from the history flow.

- `src/chat/HistoryList.tsx` (new) — fetches `GET /matches?last_n=20` on mount. Renders a scrollable list of game rows. Each row shows: champion name, WIN/LOSS result chip (green/red), KDA, relative date (e.g. "2 days ago"), and a moment count badge (e.g. "6 moments"). Clicking a row calls `onSelect(matchId)` which sets `selectedMatchId` in App.

- `src/chat/GameDetail.tsx` (new) — fetches `GET /analysis/{matchId}` on mount. Renders: a `← History` back button (calls `onBack`), the four stat tiles (champion, result, KDA, duration), the All / Good / Fix filter bar, and `MomentCard` list. Bottom button "Ask about this game →" calls `onAskAboutGame(matchId)` which switches App to the Chat tab with that `matchId` as context. Imports `MomentCard` and `POSITIVE_TYPES` from their existing popup locations (`src/popup/MomentCard.tsx`, `src/popup/constants.ts`).

- `src/chat/MessageList.tsx` — no changes needed.

**Backend — one endpoint change:**

- `GET /matches` in `sidecar/main.py` adds two fields to each returned object:
  - `role: string` — already present on the Match model, just not serialised
  - `moment_count: number` — fetched via one batch call to `get_pivotal_moments` for all match IDs in the response, then counted per match

## Navigation Flow

```
Chat tab  ──[click History tab]──►  HistoryList
                                         │
                                 [click a game row]
                                         │
                                         ▼
                                    GameDetail
                                    /         \
                          [← History]    [Ask about this game →]
                               │                    │
                               ▼                    ▼
                          HistoryList          Chat tab
                                            (chatMatchId set)
```

## Data Flow

- `App` owns `tab`, `selectedMatchId`, and `chatMatchId` state.
- `HistoryList` is stateless beyond its fetched data; selection is lifted to App via `onSelect`.
- `GameDetail` is stateless beyond its fetched analysis; navigation is lifted to App via `onBack` and `onAskAboutGame`.
- `chatMatchId` defaults to the URL `?matchId=` param on load (preserving existing popup→chat flow) and can be overwritten by the "Ask about this game →" action.

## API Contract

`GET /matches?last_n=20` response shape (updated):

```json
[
  {
    "match_id": "NA1_1234",
    "champion": "Caitlyn",
    "role": "BOTTOM",
    "result": "win",
    "kda": "12/2/7",
    "cs": 241,
    "duration_secs": 1680,
    "played_at": "2026-04-20T18:32:00",
    "moment_count": 6
  }
]
```

`GET /analysis/{match_id}` — unchanged, already used by popup.

## What Is Not In Scope

- Filtering or sorting the history list (by champion, result, etc.) — the chat already handles this conversationally
- Pagination beyond last 20 games
- Any changes to the popup window — it continues to work as before for post-game flow
