"""Tests for build_view.py — the dressing layer that resolves raw DB aggregates
into the suggested_build payload using LCU asset metadata."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from build_view import assemble_suggested_build, is_core_item, _icon_url, BUILD_SAMPLE_FLOOR


# ---------------------------------------------------------------------------
# Fake LCU
# ---------------------------------------------------------------------------

# Canonical rune signature used in above-floor tests:
#   primary_style=8000, keystone=8021, primary_runes=[9111,9105,8014],
#   sub_style=8200, sub_perks=[8234,8236], stat_shards=[5005,5008,5001]
RUNE_SIG = "8000|8021,9111,9105,8014|8200|8234,8236|5005,5008,5001"

# Spell signature: spells 4 and 14
SPELL_SIG = "4,14"


def _make_lcu(
    items=None,
    perks=None,
    perk_styles=None,
    summoner_spells=None,
):
    """Return a stub LCU with the four async getters returning the given dicts."""
    lcu = MagicMock()
    lcu.get_items = AsyncMock(return_value=items or {})
    lcu.get_perks = AsyncMock(return_value=perks or {})
    lcu.get_perk_styles = AsyncMock(return_value=perk_styles or {})
    lcu.get_summoner_spells = AsyncMock(return_value=summoner_spells or {})
    return lcu


def _stub_items():
    """A small items dict with varied meta for filtering tests."""
    return {
        # Core items (priceTotal>=1100, empty to, no bad categories)
        3157: {"name": "Zhonya's Hourglass", "iconPath": "/items/zhonya.png", "priceTotal": 2600, "to": [], "categories": ["Armor"]},
        3089: {"name": "Rabadon's Deathcap", "iconPath": "/items/rabadons.png", "priceTotal": 3400, "to": [], "categories": ["SpellDamage"]},
        3165: {"name": "Morellonomicon", "iconPath": "/items/morello.png", "priceTotal": 2500, "to": [], "categories": ["SpellDamage"]},
        3020: {"name": "Sorcerer's Shoes", "iconPath": "/items/sorc.png", "priceTotal": 1100, "to": [], "categories": ["Boots"]},
        3152: {"name": "Zaz'Zak's Realmspike", "iconPath": "/items/zazzak.png", "priceTotal": 3000, "to": [], "categories": ["SpellDamage"]},
        4628: {"name": "Horizon Focus", "iconPath": "/items/horizon.png", "priceTotal": 2700, "to": [], "categories": ["SpellDamage"]},
        3116: {"name": "Rylai's Crystal Scepter", "iconPath": "/items/rylais.png", "priceTotal": 2600, "to": [], "categories": ["SpellDamage"]},
        # Non-core: has "to" (upgradeable / component)
        1001: {"name": "Boots", "iconPath": "/items/boots.png", "priceTotal": 300, "to": [3020, 3006], "categories": ["Boots"]},
        # Non-core: cheap component
        1056: {"name": "Doran's Ring", "iconPath": "/items/dorans.png", "priceTotal": 400, "to": [], "categories": ["SpellDamage"]},
        # Non-core: Consumable
        2003: {"name": "Health Potion", "iconPath": "/items/hppot.png", "priceTotal": 50, "to": [], "categories": ["Consumable"]},
        # Non-core: Trinket
        3340: {"name": "Stealth Ward", "iconPath": "/items/ward.png", "priceTotal": 0, "to": [], "categories": ["Trinket"]},
    }


def _stub_perks():
    return {
        8021: {"name": "Fleet Footwork", "iconPath": "/perks/fleet.png"},
        9111: {"name": "Triumph", "iconPath": "/perks/triumph.png"},
        9105: {"name": "Legend: Alacrity", "iconPath": "/perks/alacrity.png"},
        8014: {"name": "Coup de Grace", "iconPath": "/perks/coup.png"},
        8234: {"name": "Nullifying Orb", "iconPath": "/perks/orb.png"},
        8236: {"name": "Transcendence", "iconPath": "/perks/trans.png"},
        5005: {"name": "Adaptive Force", "iconPath": "/perks/adaptive.png"},
        5008: {"name": "Adaptive Force", "iconPath": "/perks/adaptive.png"},
        5001: {"name": "Health Scaling", "iconPath": "/perks/health.png"},
    }


def _stub_perk_styles():
    return {
        8000: {"name": "Precision", "iconPath": "/styles/precision.png"},
        8200: {"name": "Sorcery", "iconPath": "/styles/sorcery.png"},
    }


def _stub_spells():
    return {
        4: {"name": "Flash", "iconPath": "/spells/flash.png"},
        14: {"name": "Ignite", "iconPath": "/spells/ignite.png"},
    }


def _stub_lcu():
    return _make_lcu(
        items=_stub_items(),
        perks=_stub_perks(),
        perk_styles=_stub_perk_styles(),
        summoner_spells=_stub_spells(),
    )


def _raw(n_samples=50, items=None, rune_page=None, spells=None):
    """Build a raw dict as returned by database.get_build_suggestions."""
    if items is None:
        items = [(3157, 40), (3089, 35), (3165, 30)]
    return {
        "n_samples": n_samples,
        "items": items,
        "rune_page": rune_page,
        "spells": spells,
    }


# ---------------------------------------------------------------------------
# is_core_item
# ---------------------------------------------------------------------------

def test_core_item_keeps_completed_item():
    """A completed item (priceTotal>=1100, empty to, no bad categories) is kept."""
    meta = {"priceTotal": 2600, "to": [], "categories": ["Armor"]}
    assert is_core_item(meta) is True


def test_core_item_keeps_berserkers_greaves():
    """Berserker's Greaves: upgraded boots with empty `to` — should be kept."""
    meta = {"priceTotal": 1100, "to": [], "categories": ["Boots", "AttackSpeed"]}
    assert is_core_item(meta) is True


def test_core_item_drops_basic_boots():
    """Basic Boots: has non-empty `to` (builds into something) — dropped."""
    meta = {"priceTotal": 300, "to": [3020, 3006], "categories": ["Boots"]}
    assert is_core_item(meta) is False


def test_core_item_drops_cheap_component():
    """Cheap component: priceTotal < 1100 — dropped."""
    meta = {"priceTotal": 400, "to": [], "categories": ["SpellDamage"]}
    assert is_core_item(meta) is False


def test_core_item_drops_consumable():
    """Health Potion: has Consumable category — dropped."""
    meta = {"priceTotal": 50, "to": [], "categories": ["Consumable"]}
    assert is_core_item(meta) is False


def test_core_item_drops_trinket():
    """Trinket ward: has Trinket category — dropped."""
    meta = {"priceTotal": 0, "to": [], "categories": ["Trinket"]}
    assert is_core_item(meta) is False


# ---------------------------------------------------------------------------
# _icon_url
# ---------------------------------------------------------------------------

def test_icon_url_none_when_falsy():
    assert _icon_url(None) is None
    assert _icon_url("") is None


def test_icon_url_prefix():
    url = _icon_url("/items/zhonya.png")
    assert url is not None
    assert url.startswith("/lcu-image?path=")


def test_icon_url_encodes_slashes():
    """Slashes in the path must be percent-encoded (safe='')."""
    url = _icon_url("/items/my item.png")
    assert url is not None
    assert "/items/my item.png" not in url  # raw form must not appear
    assert "%2F" in url or "%2f" in url     # slash encoded
    assert "%20" in url                      # space encoded


def test_icon_url_round_trip():
    """The encoded path round-trips back to the original via unquote."""
    import urllib.parse
    path = "/lol-game-data/assets/v1/perkimages/fleet.png"
    url = _icon_url(path)
    assert url is not None
    encoded = url[len("/lcu-image?path="):]
    assert urllib.parse.unquote(encoded) == path


# ---------------------------------------------------------------------------
# assemble_suggested_build — below sample floor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_below_floor_returns_insufficient():
    """n_samples < BUILD_SAMPLE_FLOOR → status insufficient."""
    lcu = _stub_lcu()
    raw = _raw(n_samples=BUILD_SAMPLE_FLOOR - 1)
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["status"] == "insufficient"
    assert result["role"] == "MIDDLE"
    assert result["target_tier"] == "DIAMOND"
    assert result["n_samples"] == BUILD_SAMPLE_FLOOR - 1
    assert result["items"] == []
    assert result["runes"] is None
    assert result["spells"] == []


@pytest.mark.asyncio
async def test_exactly_at_floor_is_ready():
    """n_samples == BUILD_SAMPLE_FLOOR → status ready."""
    lcu = _stub_lcu()
    raw = _raw(n_samples=BUILD_SAMPLE_FLOOR, items=[(3157, 30)], rune_page=None, spells=None)
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["status"] == "ready"


# ---------------------------------------------------------------------------
# assemble_suggested_build — above floor, full resolution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_items_resolved_with_name_and_icon():
    """Items in the result have resolved name and icon_url."""
    lcu = _stub_lcu()
    raw = _raw(n_samples=50, items=[(3157, 40), (3089, 35)])
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["status"] == "ready"
    assert len(result["items"]) == 2
    first = result["items"][0]
    assert first["id"] == 3157
    assert first["name"] == "Zhonya's Hourglass"
    assert first["icon_url"] is not None
    assert first["icon_url"].startswith("/lcu-image?path=")
    assert first["count"] == 40


@pytest.mark.asyncio
async def test_items_truncated_to_six():
    """Even with 7+ core items in raw, the result is capped at 6."""
    lcu = _stub_lcu()
    # All 7 are core items in _stub_items()
    items_raw = [
        (3157, 70), (3089, 65), (3165, 60), (3020, 55),
        (3152, 50), (4628, 45), (3116, 40),
    ]
    raw = _raw(n_samples=50, items=items_raw)
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["status"] == "ready"
    assert len(result["items"]) == 6


@pytest.mark.asyncio
async def test_non_core_items_filtered_out():
    """Non-core items (boots with to, cheap components, consumables, trinkets) are excluded."""
    lcu = _stub_lcu()
    # Mix: one core, then several non-core
    items_raw = [
        (3157, 50),   # core — kept
        (1001, 45),   # boots with to — dropped
        (1056, 40),   # cheap (<1100) — dropped
        (2003, 35),   # Consumable — dropped
        (3340, 30),   # Trinket — dropped
    ]
    raw = _raw(n_samples=50, items=items_raw)
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["status"] == "ready"
    assert len(result["items"]) == 1
    assert result["items"][0]["id"] == 3157


@pytest.mark.asyncio
async def test_runes_nested_correctly():
    """Rune resolution produces the correct nested structure."""
    lcu = _stub_lcu()
    raw = _raw(n_samples=50, rune_page=(RUNE_SIG, 45))
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["status"] == "ready"
    runes = result["runes"]
    assert runes is not None

    # primary_style
    assert runes["primary_style"]["id"] == 8000
    assert runes["primary_style"]["name"] == "Precision"

    # keystone (primary_perks[0])
    assert runes["keystone"]["id"] == 8021
    assert runes["keystone"]["name"] == "Fleet Footwork"

    # 3 non-keystone primary runes
    assert len(runes["primary_runes"]) == 3
    assert runes["primary_runes"][0]["id"] == 9111
    assert runes["primary_runes"][1]["id"] == 9105
    assert runes["primary_runes"][2]["id"] == 8014

    # sub_style
    assert runes["sub_style"]["id"] == 8200
    assert runes["sub_style"]["name"] == "Sorcery"

    # 2 sub runes
    assert len(runes["sub_runes"]) == 2
    assert runes["sub_runes"][0]["id"] == 8234
    assert runes["sub_runes"][1]["id"] == 8236

    # 3 stat shards
    assert len(runes["stat_shards"]) == 3
    assert runes["stat_shards"][0]["id"] == 5005
    assert runes["stat_shards"][1]["id"] == 5008
    assert runes["stat_shards"][2]["id"] == 5001


@pytest.mark.asyncio
async def test_runes_icon_url_encoded():
    """Rune icon_url is properly encoded and starts with /lcu-image?path=."""
    lcu = _stub_lcu()
    raw = _raw(n_samples=50, rune_page=(RUNE_SIG, 45))
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    runes = result["runes"]
    assert runes is not None
    ks_url = runes["keystone"]["icon_url"]
    assert ks_url is not None
    assert ks_url.startswith("/lcu-image?path=")
    # Raw path must not appear verbatim (it contains slashes that get encoded)
    assert "/perks/fleet.png" not in ks_url


@pytest.mark.asyncio
async def test_runes_none_when_no_rune_page():
    """If raw has no rune_page, runes in the result is None."""
    lcu = _stub_lcu()
    raw = _raw(n_samples=50, rune_page=None)
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["runes"] is None


@pytest.mark.asyncio
async def test_spells_resolved():
    """Spells resolve to list of 2 {id, name, icon_url} dicts."""
    lcu = _stub_lcu()
    raw = _raw(n_samples=50, spells=(SPELL_SIG, 40))
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["status"] == "ready"
    spells = result["spells"]
    assert len(spells) == 2
    ids = {s["id"] for s in spells}
    assert ids == {4, 14}
    for s in spells:
        assert "name" in s
        assert "icon_url" in s


@pytest.mark.asyncio
async def test_spells_empty_when_no_spells():
    """If raw has no spells, spells in the result is empty list."""
    lcu = _stub_lcu()
    raw = _raw(n_samples=50, spells=None)
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["spells"] == []


# ---------------------------------------------------------------------------
# LCU exception → insufficient (no exception escapes)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lcu_exception_returns_insufficient():
    """If any LCU getter raises, assemble_suggested_build returns insufficient without raising."""
    lcu = _make_lcu()
    lcu.get_items = AsyncMock(side_effect=RuntimeError("LCU connection refused"))
    raw = _raw(n_samples=50)
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["status"] == "insufficient"
    assert result["items"] == []
    assert result["runes"] is None
    assert result["spells"] == []


@pytest.mark.asyncio
async def test_lcu_perks_exception_returns_insufficient():
    """If get_perks raises during rune resolution, still returns insufficient."""
    lcu = _stub_lcu()
    lcu.get_perks = AsyncMock(side_effect=ConnectionError("LCU offline"))
    raw = _raw(n_samples=50, rune_page=(RUNE_SIG, 45))
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["status"] == "insufficient"


# ---------------------------------------------------------------------------
# Graceful fallback for unknown IDs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_rune_id_uses_str_fallback():
    """If an ID in the rune signature isn't in the perks map, name falls back to str(id)."""
    lcu = _make_lcu(
        items=_stub_items(),
        perks={},        # empty — no IDs will resolve
        perk_styles={},
        summoner_spells=_stub_spells(),
    )
    raw = _raw(n_samples=50, rune_page=(RUNE_SIG, 45))
    result = await assemble_suggested_build(lcu, raw, "MIDDLE", "DIAMOND")
    assert result["status"] == "ready"
    runes = result["runes"]
    assert runes is not None
    # Fallback name is str(id)
    assert runes["keystone"]["name"] == str(8021)
    assert runes["keystone"]["icon_url"] is None
