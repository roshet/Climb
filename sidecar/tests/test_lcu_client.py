import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lcu_client import LcuClient


def test_read_lockfile_parses_port_and_password(tmp_path):
    lockfile = tmp_path / "lockfile"
    lockfile.write_text("LeagueClient:12345:54321:mysecretpassword:https")
    with patch("lcu_client.LOCKFILE_PATHS", [str(lockfile)]):
        client = LcuClient()
        result = client._read_lockfile()
    assert result == (54321, "mysecretpassword")


def test_read_lockfile_returns_none_when_missing():
    with patch("lcu_client.LOCKFILE_PATHS", ["/nonexistent/path1", "/nonexistent/path2"]):
        client = LcuClient()
        assert client._read_lockfile() is None


async def test_get_champ_select_session_returns_none_when_no_lockfile():
    with patch("lcu_client.LOCKFILE_PATHS", ["/nonexistent/path"]):
        client = LcuClient()
        result = await client.get_champ_select_session()
    assert result is None


# ---------------------------------------------------------------------------
# get_champion_name tests
# ---------------------------------------------------------------------------

def _make_lockfile(tmp_path, port=54321, password="pass"):
    """Helper: write a lockfile and return its path string."""
    lockfile = tmp_path / "lockfile"
    lockfile.write_text(f"LeagueClient:12345:{port}:{password}:https")
    return str(lockfile)


def _mock_http_response(data, status_code=200):
    """Return a mock httpx response that yields *data* from .json()."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


async def test_get_champion_name_returns_none_when_no_lockfile():
    with patch("lcu_client.LOCKFILE_PATHS", ["/nonexistent/path"]):
        client = LcuClient()
        result = await client.get_champion_name(104)
    assert result is None


async def test_get_champion_name_resolves_from_api(tmp_path):
    lockfile_path = _make_lockfile(tmp_path)
    api_data = [{"id": 104, "name": "Graves"}, {"id": 1, "name": "Annie"}]

    mock_resp = _mock_http_response(api_data)
    mock_get = AsyncMock(return_value=mock_resp)
    mock_client_instance = AsyncMock()
    mock_client_instance.get = mock_get
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client_instance):
            client = LcuClient()
            result = await client.get_champion_name(104)

    assert result == "Graves"


async def test_get_champion_name_handles_missing_name_field(tmp_path):
    """Entry without 'name' key must not crash and should return None."""
    lockfile_path = _make_lockfile(tmp_path)
    api_data = [{"id": 104}]  # no "name" key

    mock_resp = _mock_http_response(api_data)
    mock_client_instance = AsyncMock()
    mock_client_instance.get = AsyncMock(return_value=mock_resp)
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("lcu_client.LOCKFILE_PATHS", [lockfile_path]):
        with patch("lcu_client.httpx.AsyncClient", return_value=mock_client_instance):
            client = LcuClient()
            result = await client.get_champion_name(104)

    assert result is None
