import asyncio
import json
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from pattern_detector import detect_patterns
from database import AppState

LIVE_CLIENT_BASE = "https://127.0.0.1:2999/liveclientdata"
DRAGON_FIRST_SPAWN = 300.0    # 5:00
DRAGON_RESPAWN_DELAY = 300.0  # 5 minutes
BARON_FIRST_SPAWN = 1200.0    # 20:00
BARON_RESPAWN_DELAY = 420.0   # 7 minutes
ALERT_DURATION = 8.0          # seconds each alert stays visible
SPAWN_WARN_WINDOW = 60.0      # seconds before spawn to show warning
DEBOUNCE_WINDOW = 30.0        # minimum seconds between same alert type


@dataclass
class Alert:
    id: str
    message: str
    alert_type: str   # "objective" | "death" | "pattern"
    expires_at: float


class LiveGameMonitor:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._in_game = False
        self._alerts: list[Alert] = []
        self._processed_event_ids: set[int] = set()
        self._next_dragon_spawn: float = DRAGON_FIRST_SPAWN
        self._next_baron_spawn: float = BARON_FIRST_SPAWN
        self._patterns_shown = False
        self._last_alert_times: dict[str, float] = {}
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._focus: dict | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def get_state(self) -> dict:
        now = time.time()
        self._alerts = [a for a in self._alerts if a.expires_at > now]
        return {
            "in_game": self._in_game,
            "alerts": [
                {
                    "id": a.id,
                    "message": a.message,
                    "alert_type": a.alert_type,
                    "expires_at": a.expires_at,
                }
                for a in self._alerts
            ],
        }

    def _add_alert(self, message: str, alert_type: str, debounce_key: str = "") -> None:
        now = time.time()
        if debounce_key:
            if now - self._last_alert_times.get(debounce_key, 0) < DEBOUNCE_WINDOW:
                return
            self._last_alert_times[debounce_key] = now
        if len(self._alerts) >= 3:
            self._alerts.pop(0)
        self._alerts.append(Alert(
            id=f"{alert_type}-{int(now * 1000)}",
            message=message,
            alert_type=alert_type,
            expires_at=now + ALERT_DURATION,
        ))

    def _death_message(self) -> str:
        if not self._focus:
            return "You're dead — use this time to plan your next move"
        display = self._focus.get("display", "")
        streak = self._focus.get("streak_clean", 0)
        if streak >= 1:
            s = "s" if streak != 1 else ""
            return f"You're dead — {streak} clean game{s} on {display}. Don't let it slip."
        return f"You're dead — think about {display} while you wait."

    def _load_focus(self) -> None:
        try:
            row = self._db.query(AppState).filter(AppState.key == "focus_card").first()
            self._focus = json.loads(row.value) if row and row.value else None
        except Exception:
            self._focus = None

    def _process_events(self, events: list[dict], active_player_name: str) -> None:
        for event in events:
            event_id = event.get("EventID", -1)
            if event_id in self._processed_event_ids:
                continue
            self._processed_event_ids.add(event_id)
            name = event.get("EventName", "")
            if name == "GameEnd":
                self._reset_game_state()
                return
            elif name == "DragonKill":
                self._next_dragon_spawn = event.get("EventTime", 0.0) + DRAGON_RESPAWN_DELAY
                self._add_alert("Next Dragon in 5:00 — stay aware", "objective", "dragon_kill")
            elif name == "BaronKill":
                self._next_baron_spawn = event.get("EventTime", 0.0) + BARON_RESPAWN_DELAY
                self._add_alert("Next Baron in 7:00 — ward up early", "objective", "baron_kill")
            elif name == "ChampionKill":
                victim = event.get("VictimName", "")
                if victim.lower() == active_player_name.lower():
                    self._add_alert(
                        self._death_message(),
                        "death",
                        f"death_{event_id}",
                    )

    def _check_spawn_timers(self, game_time: float) -> None:
        dragon_secs = self._next_dragon_spawn - game_time
        if 0 < dragon_secs <= SPAWN_WARN_WINDOW:
            self._add_alert("Dragon spawns soon — contest or trade", "objective", "dragon_soon")
        baron_secs = self._next_baron_spawn - game_time
        if 0 < baron_secs <= SPAWN_WARN_WINDOW:
            self._add_alert("Baron spawns soon — group or pressure", "objective", "baron_soon")

    def _maybe_show_patterns(self, game_time: float) -> None:
        if self._patterns_shown or game_time < 30.0:
            return
        self._patterns_shown = True
        try:
            patterns = detect_patterns(self._db)
            issues = [p for p in patterns if p.label == "recurring_issue"][:2]
            for p in issues:
                self._add_alert(f"Pattern: {p.summary}", "pattern")
        except Exception:
            pass

    def _reset_game_state(self) -> None:
        self._in_game = False
        self._alerts = []
        self._processed_event_ids = set()
        self._next_dragon_spawn = DRAGON_FIRST_SPAWN
        self._next_baron_spawn = BARON_FIRST_SPAWN
        self._patterns_shown = False
        self._last_alert_times = {}
        self._focus = None

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                pass
            await asyncio.sleep(2)

    async def _tick(self) -> None:
        async with httpx.AsyncClient(verify=False, timeout=2.0) as client:
            try:
                events_resp = await client.get(f"{LIVE_CLIENT_BASE}/eventdata")
                stats_resp = await client.get(f"{LIVE_CLIENT_BASE}/gamestats")
                player_resp = await client.get(f"{LIVE_CLIENT_BASE}/activeplayername")
            except Exception:
                if self._in_game:
                    self._in_game = False
                    self._reset_game_state()
                return

            if not self._in_game:
                self._in_game = True
                self._load_focus()

            events = events_resp.json().get("Events", [])
            game_time = stats_resp.json().get("gameTime", 0.0)
            active_player = player_resp.json()

            self._process_events(events, active_player)
            self._check_spawn_timers(game_time)
            self._maybe_show_patterns(game_time)
