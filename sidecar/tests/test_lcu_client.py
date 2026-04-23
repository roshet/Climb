import pytest
from unittest.mock import patch
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
