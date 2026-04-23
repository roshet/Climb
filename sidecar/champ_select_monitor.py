import asyncio
import logging
from collections import Counter
from typing import Optional

from sqlalchemy.orm import Session

from database import get_matches, get_pivotal_moments
from lcu_client import LcuClient

log = logging.getLogger(__name__)

MOMENT_LABELS: dict[str, str] = {
    "lane_death": "Lane Deaths",
    "cs_differential": "CS Deficit",
    "gold_differential": "Gold Deficit",
    "turret_plates_lost": "Plates Lost",
    "split_push_death": "Split Push Deaths",
    "enemy_roam_kill": "Enemy Roams",
    "low_vision": "Low Vision",
    "objective_missed": "Missed Objectives",
    "tower_lost": "Towers Lost",
    "death": "Deaths",
    "solo_kill": "Solo Kills",
    "objective_secured": "Objectives Secured",
    "gank_assist": "Gank Assists",
    "baron_secured": "Baron Secured",
    "dragon_stack": "Dragon Stacks",
    "roam_kill": "Roam Kills",
    "roam_assist": "Roam Assists",
    "ward_kill": "Vision Control",
    "bad_back_objective": "Bad Backs (Objective)",
    "bad_back_gold": "Bad Backs (Low Gold)",
}

POSITIVE_TYPES = {
    "solo_kill", "objective_secured", "gank_assist", "baron_secured",
    "dragon_stack", "roam_kill", "roam_assist", "ward_kill",
}


class ChampSelectMonitor:
    def __init__(self, db: Session, lcu: LcuClient) -> None:
        self._db = db
        self._lcu = lcu
        self._in_champ_select = False
        self._locked_champion: Optional[str] = None
        self._champ_data: Optional[dict] = None
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def get_state(self) -> dict:
        return {
            "in_champ_select": self._in_champ_select,
            "locked_champion": self._locked_champion,
            "champ_data": self._champ_data,
        }

    def _process_session(self, session: dict, champion_name: Optional[str]) -> None:
        local_cell = session.get("localPlayerCellId", -1)
        my_team = session.get("myTeam", [])
        player_entry = next((p for p in my_team if p.get("cellId") == local_cell), None)
        if not player_entry:
            self._in_champ_select = True
            return

        champion_id = player_entry.get("championId", 0)
        if champion_id == 0:
            self._in_champ_select = True
            return

        actions_flat = [a for row in session.get("actions", []) for a in row]
        locked = any(
            a.get("type") == "pick"
            and a.get("actorCellId") == local_cell
            and a.get("completed") is True
            for a in actions_flat
        )

        if locked and champion_name and self._locked_champion != champion_name:
            self._in_champ_select = True
            self._locked_champion = champion_name
            try:
                self._champ_data = self._build_champ_data(champion_name)
            except Exception as exc:
                log.debug("Failed to build champ data: %s", exc)
                self._champ_data = None
        elif not locked:
            self._in_champ_select = True

    def _build_champ_data(self, champion: str) -> dict:
        matches = get_matches(self._db, champion=champion, last_n=20)
        if not matches:
            return {"games": 0, "wins": 0, "win_rate": 0.0, "no_history": True, "patterns": []}

        games = len(matches)
        wins = sum(1 for m in matches if m.result == "win")
        win_rate = round(wins / games, 2)

        match_ids = [m.match_id for m in matches]
        moments = get_pivotal_moments(self._db, match_ids)

        negative_counts = Counter(
            m.moment_type for m in moments if m.moment_type not in POSITIVE_TYPES
        )
        positive_counts = Counter(
            m.moment_type for m in moments if m.moment_type in POSITIVE_TYPES
        )

        patterns = []
        for moment_type, count in negative_counts.most_common(2):
            label = MOMENT_LABELS.get(moment_type, moment_type.replace("_", " ").title())
            patterns.append({
                "label": "recurring_issue",
                "moment_type": moment_type,
                "summary": f"{label} in {count}/{games} games",
            })
        for moment_type, _count in positive_counts.most_common(1):
            label = MOMENT_LABELS.get(moment_type, moment_type.replace("_", " ").title())
            patterns.append({
                "label": "win_condition",
                "moment_type": moment_type,
                "summary": f"{label} in your wins",
            })

        return {"games": games, "wins": wins, "win_rate": win_rate, "no_history": False, "patterns": patterns}

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception as exc:
                log.debug("ChampSelectMonitor tick failed: %s", exc)
            await asyncio.sleep(2)

    async def _tick(self) -> None:
        session = await self._lcu.get_champ_select_session()
        if session is None:
            if self._in_champ_select:
                self._in_champ_select = False
                self._locked_champion = None
                self._champ_data = None
            return

        if self._locked_champion is None:
            local_cell = session.get("localPlayerCellId", -1)
            my_team = session.get("myTeam", [])
            player_entry = next((p for p in my_team if p.get("cellId") == local_cell), None)
            champion_id = player_entry.get("championId", 0) if player_entry else 0
            champion_name: Optional[str] = None
            if champion_id > 0:
                champion_name = await self._lcu.get_champion_name(champion_id) or "Unknown"
        else:
            champion_name = self._locked_champion

        self._process_session(session, champion_name)
