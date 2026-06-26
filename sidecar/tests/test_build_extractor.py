"""Tests for build_extractor — pure extract/encode/decode functions."""

import pytest
from build_extractor import (
    decode_rune_signature,
    decode_spell_signature,
    encode_rune_signature,
    encode_spell_signature,
    extract_participant_build,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _perks(
    primary_style: int = 8000,
    primary_selections: list | None = None,
    sub_style: int = 8200,
    sub_selections: list | None = None,
    stat_perks: dict | None = None,
) -> dict:
    """Build a well-formed perks dict."""
    if primary_selections is None:
        primary_selections = [8005, 9111, 9105, 8014]  # keystone + 3
    if sub_selections is None:
        sub_selections = [8275, 8236]
    if stat_perks is None:
        stat_perks = {"offense": 5005, "flex": 5008, "defense": 5001}
    return {
        "styles": [
            {
                "description": "primaryStyle",
                "style": primary_style,
                "selections": [{"perk": s} for s in primary_selections],
            },
            {
                "description": "subStyle",
                "style": sub_style,
                "selections": [{"perk": s} for s in sub_selections],
            },
        ],
        "statPerks": stat_perks,
    }


def _participant(
    items: dict | None = None,
    summoner1Id: int = 4,
    summoner2Id: int = 14,
    perks: dict | None = None,
) -> dict:
    """Build a well-formed participant dict."""
    base_items = {
        "item0": 3158,
        "item1": 6675,
        "item2": 3031,
        "item3": 3036,
        "item4": 6333,
        "item5": 3072,
        "item6": 3363,  # trinket — must be excluded
    }
    if items is not None:
        base_items.update(items)
    return {
        **base_items,
        "summoner1Id": summoner1Id,
        "summoner2Id": summoner2Id,
        "perks": perks if perks is not None else _perks(),
    }


# ---------------------------------------------------------------------------
# extract_participant_build — items
# ---------------------------------------------------------------------------

def test_items_item0_through_item5_captured():
    p = _participant()
    result = extract_participant_build(p)
    expected = {3158, 6675, 3031, 3036, 6333, 3072}
    assert set(result["items"]) == expected


def test_items_item6_trinket_excluded():
    p = _participant()
    result = extract_participant_build(p)
    assert 3363 not in result["items"]  # item6 value


def test_items_zeros_excluded():
    p = _participant(items={"item0": 0, "item1": 3158, "item2": 0, "item3": 0, "item4": 0, "item5": 0})
    result = extract_participant_build(p)
    assert result["items"] == [3158]


def test_items_duplicates_deduped():
    # Same item id in two slots — should count once.
    p = _participant(items={"item0": 3158, "item1": 3158, "item2": 0, "item3": 0, "item4": 0, "item5": 0})
    result = extract_participant_build(p)
    assert result["items"].count(3158) == 1


def test_items_all_empty_returns_empty_list():
    p = _participant(items={"item0": 0, "item1": 0, "item2": 0, "item3": 0, "item4": 0, "item5": 0})
    result = extract_participant_build(p)
    assert result["items"] == []


# ---------------------------------------------------------------------------
# extract_participant_build — spells
# ---------------------------------------------------------------------------

def test_spells_order_normalized_higher_first():
    # summoner1Id=14, summoner2Id=4 → "4,14" (smaller first)
    p = _participant(summoner1Id=14, summoner2Id=4)
    result = extract_participant_build(p)
    assert result["spells"] == "4,14"


def test_spells_already_ordered_stays_same():
    p = _participant(summoner1Id=4, summoner2Id=14)
    result = extract_participant_build(p)
    assert result["spells"] == "4,14"


def test_spells_missing_summoner1_returns_none():
    p = _participant()
    del p["summoner1Id"]
    result = extract_participant_build(p)
    assert result["spells"] is None


def test_spells_missing_summoner2_returns_none():
    p = _participant()
    del p["summoner2Id"]
    result = extract_participant_build(p)
    assert result["spells"] is None


def test_spells_zero_summoner1_returns_none():
    p = _participant(summoner1Id=0, summoner2Id=14)
    result = extract_participant_build(p)
    assert result["spells"] is None


def test_spells_zero_summoner2_returns_none():
    p = _participant(summoner1Id=4, summoner2Id=0)
    result = extract_participant_build(p)
    assert result["spells"] is None


# ---------------------------------------------------------------------------
# extract_participant_build — rune_page (happy path via encode)
# ---------------------------------------------------------------------------

def test_rune_page_well_formed_produces_signature():
    p = _participant()
    result = extract_participant_build(p)
    assert result["rune_page"] == "8000|8005,9111,9105,8014|8200|8275,8236|5005,5008,5001"


# ---------------------------------------------------------------------------
# encode_rune_signature / decode_rune_signature
# ---------------------------------------------------------------------------

def test_encode_rune_signature_format():
    p = _participant()
    sig = encode_rune_signature(p["perks"])
    assert sig == "8000|8005,9111,9105,8014|8200|8275,8236|5005,5008,5001"


def test_decode_rune_signature_round_trip():
    p = _participant()
    sig = encode_rune_signature(p["perks"])
    decoded = decode_rune_signature(sig)
    assert decoded["primary_style"] == 8000
    assert decoded["primary_perks"] == [8005, 9111, 9105, 8014]  # [0] is keystone
    assert decoded["sub_style"] == 8200
    assert decoded["sub_perks"] == [8275, 8236]
    assert decoded["stat_shards"] == [5005, 5008, 5001]


def test_decode_rune_signature_keystone_is_primary_perks_0():
    sig = "8000|8005,9111,9105,8014|8200|8275,8236|5005,5008,5001"
    decoded = decode_rune_signature(sig)
    assert decoded["primary_perks"][0] == 8005  # keystone


def test_rune_signature_round_trip_preserves_all_ids():
    original_perks = _perks(
        primary_style=8100,
        primary_selections=[8112, 8143, 8138, 8106],
        sub_style=8300,
        sub_selections=[8345, 8347],
        stat_perks={"offense": 5008, "flex": 5002, "defense": 5003},
    )
    sig = encode_rune_signature(original_perks)
    decoded = decode_rune_signature(sig)
    assert decoded["primary_style"] == 8100
    assert decoded["primary_perks"] == [8112, 8143, 8138, 8106]
    assert decoded["sub_style"] == 8300
    assert decoded["sub_perks"] == [8345, 8347]
    assert decoded["stat_shards"] == [5008, 5002, 5003]


# ---------------------------------------------------------------------------
# Malformed perks → rune_page None
# ---------------------------------------------------------------------------

def test_rune_page_none_when_styles_missing():
    p = _participant()
    del p["perks"]["styles"]
    result = extract_participant_build(p)
    assert result["rune_page"] is None


def test_rune_page_none_when_styles_empty():
    p = _participant()
    p["perks"]["styles"] = []
    result = extract_participant_build(p)
    assert result["rune_page"] is None


def test_rune_page_none_when_only_one_style():
    p = _participant()
    p["perks"]["styles"] = p["perks"]["styles"][:1]
    result = extract_participant_build(p)
    assert result["rune_page"] is None


def test_rune_page_none_when_primary_selections_too_short():
    perks = _perks(primary_selections=[8005, 9111, 9105])  # only 3 instead of 4
    p = _participant(perks=perks)
    result = extract_participant_build(p)
    assert result["rune_page"] is None


def test_rune_page_none_when_sub_selections_too_short():
    perks = _perks(sub_selections=[8275])  # only 1 instead of 2
    p = _participant(perks=perks)
    result = extract_participant_build(p)
    assert result["rune_page"] is None


def test_rune_page_none_when_stat_perks_missing():
    p = _participant()
    del p["perks"]["statPerks"]
    result = extract_participant_build(p)
    assert result["rune_page"] is None


def test_rune_page_none_when_stat_perks_incomplete():
    perks = _perks(stat_perks={"offense": 5005, "flex": 5008})  # missing defense
    p = _participant(perks=perks)
    result = extract_participant_build(p)
    assert result["rune_page"] is None


def test_rune_page_none_when_perks_entirely_missing():
    p = _participant()
    del p["perks"]
    result = extract_participant_build(p)
    assert result["rune_page"] is None


def test_rune_page_none_when_perks_is_none():
    p = _participant()
    p["perks"] = None
    result = extract_participant_build(p)
    assert result["rune_page"] is None


# ---------------------------------------------------------------------------
# encode_spell_signature / decode_spell_signature
# ---------------------------------------------------------------------------

def test_encode_spell_signature_order_normalized():
    p = {"summoner1Id": 14, "summoner2Id": 4}
    assert encode_spell_signature(p) == "4,14"


def test_encode_spell_signature_already_ordered():
    p = {"summoner1Id": 4, "summoner2Id": 14}
    assert encode_spell_signature(p) == "4,14"


def test_encode_spell_signature_none_when_zero():
    assert encode_spell_signature({"summoner1Id": 0, "summoner2Id": 14}) is None
    assert encode_spell_signature({"summoner1Id": 4, "summoner2Id": 0}) is None


def test_encode_spell_signature_none_when_missing():
    assert encode_spell_signature({"summoner2Id": 14}) is None
    assert encode_spell_signature({"summoner1Id": 4}) is None
    assert encode_spell_signature({}) is None


def test_decode_spell_signature_round_trip():
    p = {"summoner1Id": 14, "summoner2Id": 4}
    sig = encode_spell_signature(p)
    decoded = decode_spell_signature(sig)
    assert set(decoded) == {4, 14}
    assert len(decoded) == 2


def test_decode_spell_signature_returns_two_ints():
    decoded = decode_spell_signature("4,14")
    assert decoded == [4, 14]


# ---------------------------------------------------------------------------
# Index-order fallback when description field is missing
# ---------------------------------------------------------------------------

def test_rune_page_fallback_to_index_order_when_description_missing():
    """If style entries lack 'description', styles[0]=primary styles[1]=sub."""
    perks = {
        "styles": [
            {
                "style": 8000,
                "selections": [{"perk": 8005}, {"perk": 9111}, {"perk": 9105}, {"perk": 8014}],
            },
            {
                "style": 8200,
                "selections": [{"perk": 8275}, {"perk": 8236}],
            },
        ],
        "statPerks": {"offense": 5005, "flex": 5008, "defense": 5001},
    }
    p = _participant(perks=perks)
    result = extract_participant_build(p)
    assert result["rune_page"] == "8000|8005,9111,9105,8014|8200|8275,8236|5005,5008,5001"
