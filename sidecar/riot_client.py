import httpx

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
        self.platform = region.lower()
        headers = {"X-Riot-Token": api_key}
        # Public Riot API: keep TLS verification on (protects the API key in transit).
        self._http = httpx.AsyncClient(headers=headers, timeout=10.0)
        # Local Live Client Data API serves a self-signed cert on loopback, so verify=False
        # is required here (and safe — traffic never leaves the machine).
        self._live_http = httpx.AsyncClient(verify=False, timeout=3.0)

    async def get_puuid_by_summoner(self, game_name: str, tag_line: str) -> str:
        url = f"https://{self.regional}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        r = await self._http.get(url)
        r.raise_for_status()
        return r.json()["puuid"]

    async def get_recent_match_ids(self, puuid: str, count: int = 20,
                                   start_time: int | None = None,
                                   queue: int | None = None) -> list[str]:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params: dict = {"count": count}
        if start_time is not None:
            params["startTime"] = start_time
        if queue is not None:
            params["queue"] = queue
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

    _APEX_SLUG = {
        "MASTER": "masterleagues",
        "GRANDMASTER": "grandmasterleagues",
        "CHALLENGER": "challengerleagues",
    }

    async def get_solo_rank(self, puuid: str) -> str | None:
        url = f"https://{self.platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
        r = await self._http.get(url)
        r.raise_for_status()
        for entry in r.json():
            if entry.get("queueType") == "RANKED_SOLO_5x5":
                return entry.get("tier")
        return None

    async def get_apex_league_puuids(self, tier: str) -> list[str]:
        slug = self._APEX_SLUG[tier]
        url = f"https://{self.platform}.api.riotgames.com/lol/league/v4/{slug}/by-queue/RANKED_SOLO_5x5"
        r = await self._http.get(url)
        r.raise_for_status()
        return [e["puuid"] for e in r.json().get("entries", []) if e.get("puuid")]

    async def get_tier_division_puuids(self, tier: str, division: str, page: int = 1) -> list[str]:
        url = f"https://{self.platform}.api.riotgames.com/lol/league/v4/entries/RANKED_SOLO_5x5/{tier}/{division}"
        r = await self._http.get(url, params={"page": page})
        r.raise_for_status()
        return [e["puuid"] for e in r.json() if e.get("puuid")]

    async def is_in_game(self) -> bool:
        try:
            r = await self._live_http.get("https://127.0.0.1:2999/liveclientdata/allgamedata")
            return r.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self._http.aclose()
        await self._live_http.aclose()
