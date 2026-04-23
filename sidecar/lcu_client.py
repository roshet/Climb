import logging
from pathlib import Path
from typing import Optional

import httpx

log = logging.getLogger(__name__)

# Windows-only: LCU lockfile is written by the League client at one of these paths
LOCKFILE_PATHS = [
    r"C:\Riot Games\League of Legends\lockfile",
    r"C:\Program Files\Riot Games\League of Legends\lockfile",
]


class LcuClient:
    def __init__(self) -> None:
        self._champion_cache: dict[int, str] = {}

    def _read_lockfile(self) -> Optional[tuple[int, str]]:
        """Returns (port, password) or None if lockfile not found."""
        for path_str in LOCKFILE_PATHS:
            try:
                text = Path(path_str).read_text()
                parts = text.strip().split(":")
                if len(parts) >= 5:
                    return int(parts[2]), parts[3]
            except (OSError, ValueError):
                continue
        return None

    async def get_champ_select_session(self) -> Optional[dict]:
        creds = self._read_lockfile()
        if not creds:
            return None
        port, password = creds
        async with httpx.AsyncClient(verify=False, timeout=2.0) as client:
            try:
                resp = await client.get(
                    f"https://127.0.0.1:{port}/lol-champ-select/v1/session",
                    auth=("riot", password),
                )
                if resp.status_code != 200:
                    return None
                return resp.json()
            except Exception as exc:
                log.debug("LCU request failed: %s", exc)
                return None

    async def get_champion_name(self, champion_id: int) -> Optional[str]:
        if champion_id <= 0:
            return None
        if champion_id in self._champion_cache:
            return self._champion_cache[champion_id]
        creds = self._read_lockfile()
        if not creds:
            return None
        port, password = creds
        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            try:
                resp = await client.get(
                    f"https://127.0.0.1:{port}/lol-game-data/assets/v1/champion-summary.json",
                    auth=("riot", password),
                )
                if resp.status_code != 200:
                    return None
                for champ in resp.json():
                    cid = champ.get("id", -1)
                    name = champ.get("name")
                    if cid > 0 and name:
                        self._champion_cache[cid] = name
                return self._champion_cache.get(champion_id)
            except Exception as exc:
                log.debug("LCU request failed: %s", exc)
                return None
