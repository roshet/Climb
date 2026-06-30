"""Tests for timeline metric columns on the Match model (Task 2)."""

from datetime import datetime

from sqlalchemy import create_engine, text

from database import Base, get_matches, init_db, save_match


# ----- shared fixture data -----

BASE_MATCH = {
    "match_id": "NA1_TLM1",
    "played_at": datetime(2026, 5, 1, 20, 0),
    "champion": "Jinx",
    "role": "BOTTOM",
    "result": "win",
    "duration_secs": 1800,
    "kda": "8/2/5",
    "cs": 180,
    "gold_earned": 14000,
    "vision_score": 25,
    "raw_timeline": {},
}


# ----- tests -----


def test_save_match_with_timeline_metrics(db):
    """Three timeline metric columns are persisted when provided."""
    save_match(db, {
        **BASE_MATCH,
        "cs_at_10": 92,
        "gold_at_10": 3500,
        "gold_at_14": 6200,
    })
    matches = get_matches(db)
    assert len(matches) == 1
    assert matches[0].cs_at_10 == 92
    assert matches[0].gold_at_10 == 3500
    assert matches[0].gold_at_14 == 6200


def test_save_match_timeline_metrics_explicit_null(db):
    """Explicitly passing None persists as NULL."""
    save_match(db, {
        **BASE_MATCH,
        "match_id": "NA1_TLM2",
        "cs_at_10": None,
        "gold_at_10": None,
        "gold_at_14": None,
    })
    matches = get_matches(db)
    assert matches[0].cs_at_10 is None
    assert matches[0].gold_at_10 is None
    assert matches[0].gold_at_14 is None


def test_save_match_timeline_metrics_absent_stays_null(db):
    """Omitting the keys entirely also gives NULL (column is nullable)."""
    save_match(db, BASE_MATCH)
    matches = get_matches(db)
    assert matches[0].cs_at_10 is None
    assert matches[0].gold_at_10 is None
    assert matches[0].gold_at_14 is None


def test_init_db_adds_timeline_columns_to_existing_db(tmp_path):
    """init_db ALTER-TABLE path adds the three columns to a pre-existing DB
    that was created before these columns existed."""
    db_path = str(tmp_path / "old.db")

    # Simulate a pre-existing DB: matches table exists but lacks the new columns.
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(text(
            """CREATE TABLE matches (
                match_id TEXT PRIMARY KEY,
                played_at TEXT,
                champion TEXT,
                role TEXT,
                result TEXT,
                duration_secs INTEGER,
                kda TEXT,
                cs INTEGER,
                gold_earned INTEGER,
                vision_score INTEGER,
                raw_timeline TEXT,
                lane_opponent_champion TEXT
            )"""
        ))
        conn.commit()
    engine.dispose()

    # init_db should detect missing columns and ALTER TABLE to add them.
    init_db(db_path)

    engine2 = create_engine(f"sqlite:///{db_path}")
    with engine2.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(matches)"))}
    engine2.dispose()

    assert "cs_at_10" in cols
    assert "gold_at_10" in cols
    assert "gold_at_14" in cols
