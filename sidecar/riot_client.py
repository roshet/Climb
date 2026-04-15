import httpx
from typing import Optional

REGIONAL_ROUTING = {
    "NA1": "americas", "BR1": "americas", "LAN": "americas", "LAS": "americas",
    "EUW1": "europe", "EUNE1": "europe", "TR1": "europe", "RU": "europe",
    "KR": "asia", "JP1": "asia",
    "OC1": "sea", "PH2": "sea", "SG2": "sea", "TH2": "sea", "TW2": "sea", "VN2": "sea",
}


class RiotClient:
    def __init__(self, api_key: str, region: str = "NA1"):
        self.api_key = api_key
        self.region = region
        self.regional = REGIONAL_ROUTING.get(region, "americas")
        headers = {"X-Riot-Token": api_key}
        self._http = httpx.AsyncClient(headers=headers, timeout=10.0)
        self._live_http = httpx.AsyncClient(verify=False, timeout=3.0)

    async def get_puuid_by_summoner(self, game_name: str, tag_line: str) -> str:
        url = f"https://{self.regional}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        r = await self._http.get(url)
        r.raise_for_status()
        return r.json()["puuid"]

    async def get_recent_match_ids(self, puuid: str, count: int = 20, start_time: int | None = None) -> list[str]:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params: dict = {"count": count}
        if start_time is not None:
            params["startTime"] = start_time
        r = await self._http.get(url, params=params)
        r.raise_for_status()
        return r.json()

    async def get_match(self, match_id: str) -> dict:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        r = await self._http.get(url)
        r.raise_for_status()
        return r.json()

    async def get_timeline(self, match_id: str) -> dict:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        r = await self._http.get(url)
        r.raise_for_status()
        return r.json()

    async def is_in_game(self) -> bool:
        try:
            r = await self._live_http.get("https://127.0.0.1:2999/liveclientdata/allgamedata")
            return r.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self._http.aclose()
        await self._live_http.aclose()
