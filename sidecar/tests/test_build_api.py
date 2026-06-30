"""API-layer tests for /champ-select suggested_build and /lcu-image (Task 6)."""
import os
import tempfile

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("RIOT_API_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test_build_api.db")

import main as main_module  # noqa: E402
from database import record_build_samples, set_app_state  # noqa: E402


@pytest.fixture
def api_db(db, monkeypatch):
    monkeypatch.setattr(main_module, "db", db)
    return db


@pytest.fixture
def lcu_stub(monkeypatch):
    stub = MagicMock()
    stub.get_items = AsyncMock(return_value={})
    stub.get_perks = AsyncMock(return_value={})
    stub.get_perk_styles = AsyncMock(return_value={})
    stub.get_summoner_spells = AsyncMock(return_value={})
    stub.get_asset_bytes = AsyncMock(return_value=(b"abc", "image/png"))
    monkeypatch.setattr(main_module, "lcu", stub)
    return stub


def _stub_monitor(monkeypatch, state: dict):
    mock = MagicMock()
    mock.get_state.return_value = state
    monkeypatch.setattr(main_module, "champ_select_monitor", mock)
    return mock


def _record_samples(db, champion: str, role: str, target_tier: str, n: int = 30) -> None:
    """Insert *n* build samples so n_samples >= BUILD_SAMPLE_FLOOR."""
    for _ in range(n):
        record_build_samples(db, champion, role, target_tier, "14.12", {
            "spells": "4,14",
            "items": [],
        })


async def test_suggested_build_ready_with_assigned_position(api_db, lcu_stub, monkeypatch):
    """≥30 samples + assigned_position='middle' → status=ready, role=MIDDLE."""
    _record_samples(api_db, "Ahri", "MIDDLE", "DIAMOND")
    set_app_state(api_db, "benchmark_target_tier", "DIAMOND")
    _stub_monitor(monkeypatch, {
        "in_champ_select": True,
        "locked_champion": "Ahri",
        "champ_data": {"games": 5, "wins": 3, "win_rate": 0.6, "no_history": False,
                       "patterns": [], "focus": None},
        "assigned_position": "middle",
    })
    state = await main_module.get_champ_select()
    sb = state["champ_data"]["suggested_build"]
    assert sb["status"] == "ready"
    assert sb["role"] == "MIDDLE"


async def test_suggested_build_fallback_to_most_sampled_role(api_db, lcu_stub, monkeypatch):
    """assigned_position='' falls back to most_sampled_role (deterministic: only JUNGLE samples)."""
    _record_samples(api_db, "Ahri", "JUNGLE", "DIAMOND")
    set_app_state(api_db, "benchmark_target_tier", "DIAMOND")
    _stub_monitor(monkeypatch, {
        "in_champ_select": True,
        "locked_champion": "Ahri",
        "champ_data": {"games": 5, "wins": 3, "win_rate": 0.6, "no_history": False,
                       "patterns": [], "focus": None},
        "assigned_position": "",
    })
    state = await main_module.get_champ_select()
    sb = state["champ_data"]["suggested_build"]
    assert sb["role"] == "JUNGLE"


async def test_lcu_image_proxies_bytes(lcu_stub, monkeypatch):
    """Valid /lol-game-data/assets path returns (bytes, media_type) from lcu.get_asset_bytes."""
    lcu_stub.get_asset_bytes.return_value = (b"abc", "image/png")
    response = await main_module.lcu_image(path="/lol-game-data/assets/x.png")
    assert response.body == b"abc"
    assert response.media_type == "image/png"


async def test_lcu_image_rejects_invalid_path(lcu_stub, monkeypatch):
    """Path not starting with /lol-game-data/assets raises HTTPException 400."""
    with pytest.raises(HTTPException) as exc_info:
        await main_module.lcu_image(path="/evil")
    assert exc_info.value.status_code == 400


async def test_lcu_image_rejects_path_traversal(lcu_stub, monkeypatch):
    """A '..' traversal that escapes the asset namespace is rejected (SSRF guard)."""
    with pytest.raises(HTTPException) as exc_info:
        await main_module.lcu_image(
            path="/lol-game-data/assets/../../lol-summoner/v1/current-summoner")
    assert exc_info.value.status_code == 400
    # the guard must reject before ever touching the LCU client
    lcu_stub.get_asset_bytes.assert_not_called()
