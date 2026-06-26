from database import (
    record_build_samples, get_build_suggestions, most_sampled_role,
)


def test_record_items_accumulate_across_calls(db):
    """Items are recorded per element_id and counts accumulate across calls."""
    build1 = {"items": [3157, 3089], "rune_page": None, "spells": None}
    build2 = {"items": [3157, 6655], "rune_page": None, "spells": None}
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build1)
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build2)
    result = get_build_suggestions(db, "Syndra", "MIDDLE", "DIAMOND")
    items_map = {item_id: count for item_id, count in result["items"]}
    assert items_map[3157] == 2  # in both builds
    assert items_map[3089] == 1  # in build1 only
    assert items_map[6655] == 1  # in build2 only


def test_record_rune_page_and_spells(db):
    """Rune page and spells are recorded correctly."""
    build = {
        "items": [],
        "rune_page": "8100|8134|8105|8347|9111|8299",
        "spells": "4_14",
    }
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build)
    result = get_build_suggestions(db, "Syndra", "MIDDLE", "DIAMOND")
    assert result["rune_page"] == ("8100|8134|8105|8347|9111|8299", 1)
    assert result["spells"] == ("4_14", 1)


def test_cross_patch_sum(db):
    """Counts are summed across different patches."""
    build = {"items": [3157], "rune_page": "sig1", "spells": "4_14"}
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build)
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.13", build)
    result = get_build_suggestions(db, "Syndra", "MIDDLE", "DIAMOND")
    items_map = {item_id: count for item_id, count in result["items"]}
    assert items_map[3157] == 2
    assert result["rune_page"] == ("sig1", 2)
    assert result["spells"] == ("4_14", 2)


def test_champion_role_tier_isolation(db):
    """Different champion/role/tier combinations are isolated from each other."""
    build = {"items": [3157], "rune_page": "sig1", "spells": "4_14"}
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build)
    # Different champion
    result = get_build_suggestions(db, "Zed", "MIDDLE", "DIAMOND")
    assert result["n_samples"] == 0
    assert result["items"] == []
    assert result["rune_page"] is None
    # Different role
    result = get_build_suggestions(db, "Syndra", "TOP", "DIAMOND")
    assert result["n_samples"] == 0
    # Different tier
    result = get_build_suggestions(db, "Syndra", "MIDDLE", "MASTER")
    assert result["n_samples"] == 0


def test_n_samples_equals_spell_count(db):
    """n_samples equals the sum of spells-kind counts when spells rows exist."""
    build = {"items": [3157, 3089], "rune_page": "sig1", "spells": "4_14"}
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build)
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build)
    result = get_build_suggestions(db, "Syndra", "MIDDLE", "DIAMOND")
    assert result["n_samples"] == 2  # 2 spells-kind increments


def test_n_samples_fallback_to_rune_page(db):
    """n_samples falls back to rune_page counts when no spells rows exist."""
    build = {"items": [3157], "rune_page": "sig1", "spells": None}
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build)
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build)
    result = get_build_suggestions(db, "Syndra", "MIDDLE", "DIAMOND")
    assert result["n_samples"] == 2  # falls back to rune_page count
    assert result["spells"] is None


def test_most_sampled_role_picks_max(db):
    """most_sampled_role returns the role with the greatest summed spells count."""
    build_mid = {"items": [], "rune_page": None, "spells": "4_14"}
    build_top = {"items": [], "rune_page": None, "spells": "4_12"}
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build_mid)
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build_mid)
    record_build_samples(db, "Syndra", "TOP", "DIAMOND", "14.12", build_top)
    result = most_sampled_role(db, "Syndra", "DIAMOND")
    assert result == "MIDDLE"


def test_most_sampled_role_none_when_empty(db):
    """most_sampled_role returns None when no data exists."""
    result = most_sampled_role(db, "Syndra", "DIAMOND")
    assert result is None


def test_empty_returns_zero_and_none(db):
    """Empty DB returns n_samples==0, rune_page is None, spells is None, items==[]."""
    result = get_build_suggestions(db, "Syndra", "MIDDLE", "DIAMOND")
    assert result["n_samples"] == 0
    assert result["rune_page"] is None
    assert result["spells"] is None
    assert result["items"] == []


def test_items_returned_as_ints(db):
    """Item IDs in the result are ints, not strings."""
    build = {"items": [3157], "rune_page": None, "spells": None}
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build)
    result = get_build_suggestions(db, "Syndra", "MIDDLE", "DIAMOND")
    for item_id, _ in result["items"]:
        assert isinstance(item_id, int)


def test_items_sorted_by_count_desc(db):
    """Items in the result are sorted by count descending."""
    build1 = {"items": [3157], "rune_page": None, "spells": None}
    build2 = {"items": [3089], "rune_page": None, "spells": None}
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build1)
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build2)
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build2)  # 3089 appears twice
    result = get_build_suggestions(db, "Syndra", "MIDDLE", "DIAMOND")
    assert result["items"][0][0] == 3089  # higher count first
    assert result["items"][0][1] == 2
    assert result["items"][1][0] == 3157
    assert result["items"][1][1] == 1


def test_most_sampled_role_sums_across_patches(db):
    """most_sampled_role sums spells counts across patches."""
    build = {"items": [], "rune_page": None, "spells": "4_14"}
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.12", build)
    record_build_samples(db, "Syndra", "MIDDLE", "DIAMOND", "14.13", build)
    record_build_samples(db, "Syndra", "TOP", "DIAMOND", "14.12", build)
    # MIDDLE has 2 across patches, TOP has 1 — MIDDLE should win
    result = most_sampled_role(db, "Syndra", "DIAMOND")
    assert result == "MIDDLE"
