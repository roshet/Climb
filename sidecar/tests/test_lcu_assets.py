"""Tests for LcuClient asset-resolution methods (Task 4).

Mirrors the mocking pattern in test_lcu_client.py:
  - _make_lockfile / _mock_http_response helpers
  - patch LOCKFILE_PATHS + httpx.AsyncClient
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lcu_client import LcuClient


# ---------------------------------------------------------------------------
# Shared helpers (same as test_lcu_client.py)
# ---------------------------------------------------------------------------

def _make_lockfile(tmp_path, port=54321, password="pass"):
    """Write a lockfile and return its path string."""
    lockfile = tmp_path / "lockfile"
    lockfile.write_text(f"LeagueClient:12345:{port}:{password}:https")
    return str(lockfile)


def _mock_http_response(data, status_code=200, content=b"", content_type="image/png"):
    """Return a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.content = content
    resp.headers = {"content-type": content_type}
    return resp


def _make_async_client(mock_resp):
    """Wrap a response in a fully-mocked AsyncClient context manager."""
    mock_get = AsyncMock(return_value=mock_resp)
    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# get_items
# ---------------------------------------------------------------------------

ITEMS_JSON = [
    {
        "id": 3078,
        "name": "Trinity Force",
        "iconPath": "/lol-game-data/assets/ASSETS/Items/Icons2D/3078.png",
        "priceTotal": 3333,
        "to": [3057, 3086],
        "categories": ["Damage", "AttackSpeed"],
    },
    {
        "id": 1001,
        "name": "Boots",
        "iconPath": "/lol-game-data/assets/ASSETS/Items/Icons2D/1001.png",
        "priceTotal": 300,
        "to": [],
        "categories": ["Boots"],
    },
    # entry missing name — must be skipped
    {"id": 9999, "iconPath": "/lol-game-data/assets/ASSETS/Items/Icons2D/9999.png"},
    # entry missing id — must be skipped
    {"name": "Ghost Item", "iconPath": None},
]


async def test_get_items_builds_id_map(tmp_path):
    lockfile_path = _make_lockfile(tmp_path)
    mock_resp = _mock_http_response(ITEMS_JSON)
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            result = await client.get_items()

    assert isinstance(result, dict)
    assert result[3078]["name"] == "Trinity Force"
    assert result[3078]["priceTotal"] == 3333
    assert result[3078]["to"] == [3057, 3086]
    assert result[3078]["categories"] == ["Damage", "AttackSpeed"]
    assert result[1001]["name"] == "Boots"
    # missing-name entry skipped
    assert 9999 not in result
    # missing-id entry skipped (no way to key it)
    assert len(result) == 2


async def test_get_items_defaults_optional_fields(tmp_path):
    """Items missing iconPath / priceTotal / to / categories get safe defaults."""
    lockfile_path = _make_lockfile(tmp_path)
    minimal_items = [{"id": 1, "name": "Minimal Item"}]
    mock_resp = _mock_http_response(minimal_items)
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            result = await client.get_items()

    assert result[1]["iconPath"] is None
    assert result[1]["priceTotal"] == 0
    assert result[1]["to"] == []
    assert result[1]["categories"] == []


async def test_get_items_cached_on_second_call(tmp_path):
    lockfile_path = _make_lockfile(tmp_path)
    mock_resp = _mock_http_response(ITEMS_JSON)
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            await client.get_items()
            await client.get_items()

    # HTTP GET called exactly once — second call hit cache
    assert mock_client.get.call_count == 1


async def test_get_items_returns_none_when_no_lockfile():
    with patch("lcu_client.LOCKFILE_PATHS", ["/nonexistent/path"]):
        client = LcuClient()
        result = await client.get_items()
    assert result is None


# ---------------------------------------------------------------------------
# get_perks
# ---------------------------------------------------------------------------

PERKS_JSON = [
    {"id": 8112, "name": "Electrocute", "iconPath": "/lol-game-data/assets/v1/perk-images/Styles/DomRecip/Electrocute/Electrocute.png"},
    {"id": 5008, "name": "Adaptive Force", "iconPath": None},
    # no name — skip
    {"id": 8000},
    # no id — skip
    {"name": "Ghost Perk"},
]


async def test_get_perks_builds_id_map(tmp_path):
    lockfile_path = _make_lockfile(tmp_path)
    mock_resp = _mock_http_response(PERKS_JSON)
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            result = await client.get_perks()

    assert result[8112]["name"] == "Electrocute"
    assert result[5008]["name"] == "Adaptive Force"
    assert result[5008]["iconPath"] is None
    assert 8000 not in result
    assert len(result) == 2


async def test_get_perks_cached_on_second_call(tmp_path):
    lockfile_path = _make_lockfile(tmp_path)
    mock_resp = _mock_http_response(PERKS_JSON)
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            await client.get_perks()
            await client.get_perks()

    assert mock_client.get.call_count == 1


async def test_get_perks_returns_none_when_no_lockfile():
    with patch("lcu_client.LOCKFILE_PATHS", ["/nonexistent/path"]):
        client = LcuClient()
        result = await client.get_perks()
    assert result is None


# ---------------------------------------------------------------------------
# get_perk_styles
# ---------------------------------------------------------------------------

PERK_STYLES_JSON = {
    "styles": [
        {"id": 8100, "name": "Domination", "iconPath": "/lol-game-data/assets/v1/perk-images/Styles/7200_Domination.png"},
        {"id": 8300, "name": "Inspiration", "iconPath": None},
        # no name — skip
        {"id": 9999},
        # no id — skip
        {"name": "Mystery Style"},
    ]
}


async def test_get_perk_styles_reads_from_styles_wrapper(tmp_path):
    """get_perk_styles must unwrap the {'styles': [...]} envelope."""
    lockfile_path = _make_lockfile(tmp_path)
    mock_resp = _mock_http_response(PERK_STYLES_JSON)
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            result = await client.get_perk_styles()

    assert result[8100]["name"] == "Domination"
    assert result[8300]["name"] == "Inspiration"
    assert result[8300]["iconPath"] is None
    assert 9999 not in result
    assert len(result) == 2


async def test_get_perk_styles_cached_on_second_call(tmp_path):
    lockfile_path = _make_lockfile(tmp_path)
    mock_resp = _mock_http_response(PERK_STYLES_JSON)
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            await client.get_perk_styles()
            await client.get_perk_styles()

    assert mock_client.get.call_count == 1


async def test_get_perk_styles_returns_none_when_no_lockfile():
    with patch("lcu_client.LOCKFILE_PATHS", ["/nonexistent/path"]):
        client = LcuClient()
        result = await client.get_perk_styles()
    assert result is None


# ---------------------------------------------------------------------------
# get_summoner_spells
# ---------------------------------------------------------------------------

SUMMONER_SPELLS_JSON = [
    {"id": 4, "name": "Flash", "iconPath": "/lol-game-data/assets/DATA/Spells/Icons2D/spell_SummonerFlash.png"},
    {"id": 14, "name": "Ignite", "iconPath": "/lol-game-data/assets/DATA/Spells/Icons2D/spell_SummonerDot.png"},
    # no name — skip
    {"id": 1},
    # no id — skip
    {"name": "Unknown Spell"},
]


async def test_get_summoner_spells_builds_id_map(tmp_path):
    lockfile_path = _make_lockfile(tmp_path)
    mock_resp = _mock_http_response(SUMMONER_SPELLS_JSON)
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            result = await client.get_summoner_spells()

    assert result[4]["name"] == "Flash"
    assert result[14]["name"] == "Ignite"
    assert 1 not in result
    assert len(result) == 2


async def test_get_summoner_spells_cached_on_second_call(tmp_path):
    lockfile_path = _make_lockfile(tmp_path)
    mock_resp = _mock_http_response(SUMMONER_SPELLS_JSON)
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            await client.get_summoner_spells()
            await client.get_summoner_spells()

    assert mock_client.get.call_count == 1


async def test_get_summoner_spells_returns_none_when_no_lockfile():
    with patch("lcu_client.LOCKFILE_PATHS", ["/nonexistent/path"]):
        client = LcuClient()
        result = await client.get_summoner_spells()
    assert result is None


# ---------------------------------------------------------------------------
# get_asset_bytes
# ---------------------------------------------------------------------------

async def test_get_asset_bytes_returns_content_and_content_type(tmp_path):
    lockfile_path = _make_lockfile(tmp_path)
    raw_bytes = b"\x89PNG\r\n\x1a\n"
    mock_resp = _mock_http_response(None, content=raw_bytes, content_type="image/png")
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            result = await client.get_asset_bytes(
                "/lol-game-data/assets/ASSETS/Items/Icons2D/3078.png"
            )

    assert result is not None
    content, ctype = result
    assert content == raw_bytes
    assert ctype == "image/png"


async def test_get_asset_bytes_lowercases_path(tmp_path):
    """The URL passed to .get() must use the lowercased path."""
    lockfile_path = _make_lockfile(tmp_path)
    raw_bytes = b"img"
    mock_resp = _mock_http_response(None, content=raw_bytes, content_type="image/png")
    mock_client = _make_async_client(mock_resp)

    mixed_case_path = "/lol-game-data/assets/ASSETS/Items/Icons2D/SomeItem.PNG"

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            await client.get_asset_bytes(mixed_case_path)

    called_url: str = mock_client.get.call_args[0][0]
    assert mixed_case_path.lower() in called_url
    # Confirm the original mixed-case is NOT used
    assert mixed_case_path not in called_url


async def test_get_asset_bytes_returns_none_on_non_200(tmp_path):
    lockfile_path = _make_lockfile(tmp_path)
    mock_resp = _mock_http_response(None, status_code=404, content=b"Not Found")
    mock_client = _make_async_client(mock_resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            result = await client.get_asset_bytes("/some/path.png")

    assert result is None


async def test_get_asset_bytes_returns_none_when_no_lockfile():
    with patch("lcu_client.LOCKFILE_PATHS", ["/nonexistent/path"]):
        client = LcuClient()
        result = await client.get_asset_bytes("/some/path.png")
    assert result is None


async def test_get_asset_bytes_default_content_type(tmp_path):
    """When content-type header is absent, default to image/png."""
    lockfile_path = _make_lockfile(tmp_path)
    raw_bytes = b"img"
    resp = MagicMock()
    resp.status_code = 200
    resp.content = raw_bytes
    resp.headers = {}  # no content-type key

    mock_client = _make_async_client(resp)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client):
            client = LcuClient()
            result = await client.get_asset_bytes("/path.png")

    assert result is not None
    _, ctype = result
    assert ctype == "image/png"
