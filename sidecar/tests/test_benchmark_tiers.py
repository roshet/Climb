import pytest
from benchmark_tiers import next_tier_up, APEX_TIERS


@pytest.mark.parametrize("tier,expected", [
    ("PLATINUM", "EMERALD"),
    ("EMERALD", "DIAMOND"),
    ("DIAMOND", "MASTER"),
    ("MASTER", "GRANDMASTER"),
    ("GRANDMASTER", "CHALLENGER"),
    ("CHALLENGER", "CHALLENGER"),  # caps
    ("IRON", "BRONZE"),
])
def test_next_tier_up(tier, expected):
    assert next_tier_up(tier) == expected


def test_unranked_defaults_to_platinum():
    assert next_tier_up(None) == "PLATINUM"
    assert next_tier_up("") == "PLATINUM"


def test_unknown_tier_defaults_to_platinum():
    assert next_tier_up("WOOD") == "PLATINUM"


def test_apex_tiers_constant():
    assert APEX_TIERS == {"MASTER", "GRANDMASTER", "CHALLENGER"}
