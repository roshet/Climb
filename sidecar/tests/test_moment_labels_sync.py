import re
from pathlib import Path

from champ_select_monitor import MOMENT_LABELS

# repo_root/sidecar/tests/<this file> -> parents[2] == repo root
_CHAT_APP_TSX = Path(__file__).resolve().parents[2] / "src" / "chat" / "App.tsx"


def _frontend_moment_labels() -> dict[str, str]:
    text = _CHAT_APP_TSX.read_text(encoding="utf-8")
    block = re.search(r"MOMENT_LABELS[^=]*=\s*\{(.*?)\}", text, re.DOTALL)
    assert block, f"Could not find MOMENT_LABELS object literal in {_CHAT_APP_TSX}"
    # keys are unquoted JS identifiers; values are single-quoted strings (no embedded ')
    return dict(re.findall(r"(\w+)\s*:\s*'([^']*)'", block.group(1)))


def test_frontend_file_is_present():
    assert _CHAT_APP_TSX.exists(), f"Expected chat window at {_CHAT_APP_TSX}"


def test_backend_moment_labels_match_frontend():
    assert MOMENT_LABELS == _frontend_moment_labels(), (
        "MOMENT_LABELS drifted between src/chat/App.tsx and "
        "sidecar/champ_select_monitor.py — update both when adding/renaming a moment label."
    )
