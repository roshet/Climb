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
        self._items_cache: Optional[dict[int, dict]] = None
        self._perks_cache: Optional[dict[int, dict]] = None
        self._perk_styles_cache: Optional[dict[int, dict]] = None
        self._summoner_spells_cache: Optional[dict[int, dict]] = None

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

    # ------------------------------------------------------------------
    # Private helper: fetch a JSON payload from an LCU asset endpoint.
    # Returns the parsed list/dict, or None on any failure.
    # ------------------------------------------------------------------

    async def _fetch_json(self, asset_path: str):
        creds = self._read_lockfile()
        if not creds:
            return None
        port, password = creds
        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            try:
                resp = await client.get(
                    f"https://127.0.0.1:{port}{asset_path}",
                    auth=("riot", password),
                )
                if resp.status_code != 200:
                    return None
                return resp.json()
            except Exception as exc:
                log.debug("LCU request failed: %s", exc)
                return None

    # ------------------------------------------------------------------
    # Asset-resolution methods (lazy id→meta caches)
    # ------------------------------------------------------------------

    async def get_items(self) -> Optional[dict[int, dict]]:
        """Return id→{name, iconPath, priceTotal, to, categories} for all items."""
        if self._items_cache is not None:
            return self._items_cache
        data = await self._fetch_json("/lol-game-data/assets/v1/items.json")
        if data is None:
            return None
        result: dict[int, dict] = {}
        for entry in data:
            item_id = entry.get("id")
            name = entry.get("name")
            if item_id is None or not name:
                continue
            result[item_id] = {
                "name": name,
                "iconPath": entry.get("iconPath", None),
                "priceTotal": entry.get("priceTotal", 0),
                "to": entry.get("to", []),
                "categories": entry.get("categories", []),
            }
        self._items_cache = result
        return result

    async def get_perks(self) -> Optional[dict[int, dict]]:
        """Return id→{name, iconPath} for all perks (keystones, runes, stat shards)."""
        if self._perks_cache is not None:
            return self._perks_cache
        data = await self._fetch_json("/lol-game-data/assets/v1/perks.json")
        if data is None:
            return None
        result: dict[int, dict] = {}
        for entry in data:
            perk_id = entry.get("id")
            name = entry.get("name")
            if perk_id is None or not name:
                continue
            result[perk_id] = {
                "name": name,
                "iconPath": entry.get("iconPath", None),
            }
        self._perks_cache = result
        return result

    async def get_perk_styles(self) -> Optional[dict[int, dict]]:
        """Return id→{name, iconPath} for all perk styles (rune trees)."""
        if self._perk_styles_cache is not None:
            return self._perk_styles_cache
        data = await self._fetch_json("/lol-game-data/assets/v1/perkstyles.json")
        if data is None:
            return None
        # Payload is an object {"styles": [...]} not a bare list
        styles = data.get("styles", []) if isinstance(data, dict) else []
        result: dict[int, dict] = {}
        for entry in styles:
            style_id = entry.get("id")
            name = entry.get("name")
            if style_id is None or not name:
                continue
            result[style_id] = {
                "name": name,
                "iconPath": entry.get("iconPath", None),
            }
        self._perk_styles_cache = result
        return result

    async def get_summoner_spells(self) -> Optional[dict[int, dict]]:
        """Return id→{name, iconPath} for all summoner spells."""
        if self._summoner_spells_cache is not None:
            return self._summoner_spells_cache
        data = await self._fetch_json("/lol-game-data/assets/v1/summoner-spells.json")
        if data is None:
            return None
        result: dict[int, dict] = {}
        for entry in data:
            spell_id = entry.get("id")
            name = entry.get("name")
            if spell_id is None or not name:
                continue
            result[spell_id] = {
                "name": name,
                "iconPath": entry.get("iconPath", None),
            }
        self._summoner_spells_cache = result
        return result

    async def get_asset_bytes(self, path: str) -> Optional[tuple[bytes, str]]:
        """Fetch raw bytes for an LCU asset path.

        Lowercases the path before requesting (LCU is case-sensitive on some
        installs).  Returns (content, content_type) or None on any failure.
        Not cached — caller should cache if needed.
        """
        creds = self._read_lockfile()
        if not creds:
            return None
        port, password = creds
        lowered = path.lower()
        async with httpx.AsyncClient(verify=False, timeout=5.0) as client:
            try:
                resp = await client.get(
                    f"https://127.0.0.1:{port}{lowered}",
                    auth=("riot", password),
                )
                if resp.status_code != 200:
                    return None
                content_type = resp.headers.get("content-type", "image/png")
                return (resp.content, content_type)
            except Exception as exc:
                log.debug("LCU request failed: %s", exc)
                return None
