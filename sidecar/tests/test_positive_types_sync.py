import re
from pathlib import Path

from champ_select_monitor import POSITIVE_TYPES

# repo_root/sidecar/tests/<this file> -> parents[2] == repo root
_CONSTANTS_TS = Path(__file__).resolve().parents[2] / "src" / "popup" / "constants.ts"


def _frontend_positive_types() -> set[str]:
    text = _CONSTANTS_TS.read_text(encoding="utf-8")
    block = re.search(r"POSITIVE_TYPES\s*=\s*new Set\(\[(.*?)\]\)", text, re.DOTALL)
    assert block, f"Could not find POSITIVE_TYPES Set literal in {_CONSTANTS_TS}"
    return set(re.findall(r"['\"]([^'\"]+)['\"]", block.group(1)))


def test_frontend_file_is_present():
    # Guards against a silently-skipped check if the file ever moves.
    assert _CONSTANTS_TS.exists(), f"Expected frontend constants at {_CONSTANTS_TS}"


def test_backend_positive_types_matches_frontend():
    assert POSITIVE_TYPES == _frontend_positive_types(), (
        "POSITIVE_TYPES drifted between src/popup/constants.ts and "
        "sidecar/champ_select_monitor.py — update both when adding a positive moment type."
    )
