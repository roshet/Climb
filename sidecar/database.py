import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import create_engine, String, Integer, Float, DateTime, JSON, ForeignKey, Text, Engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, relationship


class Base(DeclarativeBase):
    pass


class Match(Base):
    __tablename__ = "matches"
    match_id: Mapped[str] = mapped_column(String, primary_key=True)
    played_at: Mapped[datetime] = mapped_column(DateTime)
    champion: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    result: Mapped[str] = mapped_column(String)
    duration_secs: Mapped[int] = mapped_column(Integer)
    kda: Mapped[str] = mapped_column(String)
    cs: Mapped[int] = mapped_column(Integer)
    gold_earned: Mapped[int] = mapped_column(Integer)
    vision_score: Mapped[int] = mapped_column(Integer)
    raw_timeline: Mapped[dict] = mapped_column(JSON)
    lane_opponent_champion: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    moments: Mapped[list["PivotalMoment"]] = relationship(back_populates="match")


class PivotalMoment(Base):
    __tablename__ = "pivotal_moments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.match_id"))
    timestamp_secs: Mapped[int] = mapped_column(Integer)
    moment_type: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    counterfactual: Mapped[str] = mapped_column(Text)
    gold_impact: Mapped[int] = mapped_column(Integer)
    match: Mapped["Match"] = relationship(back_populates="moments")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String)
    match_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Player(Base):
    __tablename__ = "player"
    summoner_name: Mapped[str] = mapped_column(String, primary_key=True)
    riot_puuid: Mapped[str] = mapped_column(String)
    region: Mapped[str] = mapped_column(String)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AppState(Base):
    __tablename__ = "app_state"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric: Mapped[str] = mapped_column(String)
    target: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Benchmark(Base):
    __tablename__ = "benchmarks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_tier: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    metric_key: Mapped[str] = mapped_column(String)
    sum_value: Mapped[float] = mapped_column(Float, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    patch: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class BenchmarkHarvestedMatch(Base):
    __tablename__ = "benchmark_harvested_matches"
    match_id: Mapped[str] = mapped_column(String, primary_key=True)
    harvested_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db(db_path: str = "analyst.db") -> Engine:
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        # Add columns introduced after the first release. Check existence explicitly so a
        # real failure (locked db, permissions) surfaces instead of being swallowed.
        existing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(matches)"))}
        if "lane_opponent_champion" not in existing_cols:
            conn.execute(text("ALTER TABLE matches ADD COLUMN lane_opponent_champion TEXT"))
            conn.commit()
    return engine


# --- Match queries ---

def save_match(db: Session, data: dict) -> Match:
    match = Match(**data)
    db.merge(match)
    db.commit()
    return match


def get_matches(db: Session, champion: Optional[str] = None, result: Optional[str] = None, last_n: int = 50) -> list[Match]:
    q = db.query(Match)
    if champion:
        q = q.filter(Match.champion == champion)
    if result:
        q = q.filter(Match.result == result)
    return q.order_by(Match.played_at.desc()).limit(last_n).all()


def get_all_match_ids(db: Session) -> set[str]:
    return {row[0] for row in db.query(Match.match_id).all()}


# --- Pivotal moment queries ---

def save_pivotal_moments(db: Session, match_id: str, moments: list[dict]) -> None:
    for m in moments:
        db.add(PivotalMoment(match_id=match_id, **m))
    db.commit()


def delete_pivotal_moments(db: Session, match_id: str) -> None:
    db.query(PivotalMoment).filter(PivotalMoment.match_id == match_id).delete()
    db.commit()


def get_pivotal_moments(db: Session, match_ids: list[str]) -> list[PivotalMoment]:
    return db.query(PivotalMoment).filter(PivotalMoment.match_id.in_(match_ids)).all()


# --- Chat queries ---

def save_chat_message(db: Session, session_id: str, match_id: Optional[str], role: str, content: str) -> None:
    db.add(ChatMessage(session_id=session_id, match_id=match_id, role=role, content=content))
    db.commit()


def get_chat_history(db: Session, session_id: str) -> list[ChatMessage]:
    return db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()


# --- Player queries ---

def save_player(db: Session, summoner_name: str, puuid: str, region: str) -> None:
    db.merge(Player(summoner_name=summoner_name, riot_puuid=puuid, region=region, last_synced_at=datetime.now(timezone.utc)))
    db.commit()


def get_player(db: Session) -> Optional[Player]:
    return db.query(Player).first()


# --- Goal queries ---

def create_goal(db: Session, metric: str, target: float) -> Goal:
    goal = Goal(metric=metric, target=target)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def get_goals(db: Session) -> list[Goal]:
    return db.query(Goal).order_by(Goal.created_at).all()


def delete_goal(db: Session, goal_id: int) -> None:
    db.query(Goal).filter(Goal.id == goal_id).delete()
    db.commit()


# --- Popup flag ---

def set_pending_popup(db: Session, match_id: str) -> None:
    db.merge(AppState(key="pending_popup", value=match_id))
    db.commit()


def get_pending_popup(db: Session) -> Optional[str]:
    row = db.query(AppState).filter(AppState.key == "pending_popup").first()
    return row.value if row else None


def clear_pending_popup(db: Session) -> None:
    db.query(AppState).filter(AppState.key == "pending_popup").delete()
    db.commit()


# --- Benchmark queries ---

def record_benchmark_samples(db: Session, target_tier: str, role: str, patch: str,
                             metrics: dict[str, float]) -> None:
    now = datetime.now(timezone.utc)
    for metric_key, value in metrics.items():
        row = (
            db.query(Benchmark)
            .filter(
                Benchmark.target_tier == target_tier,
                Benchmark.role == role,
                Benchmark.metric_key == metric_key,
                Benchmark.patch == patch,
            )
            .first()
        )
        if row is None:
            row = Benchmark(target_tier=target_tier, role=role, metric_key=metric_key,
                            sum_value=0.0, sample_count=0, patch=patch)
            db.add(row)
        row.sum_value += value
        row.sample_count += 1
        row.updated_at = now
    db.commit()


def get_benchmarks(db: Session, target_tier: str, role: str) -> dict[str, tuple[float, int]]:
    rows = (
        db.query(Benchmark)
        .filter(Benchmark.target_tier == target_tier, Benchmark.role == role)
        .all()
    )
    out: dict[str, tuple[float, int]] = {}
    for r in rows:
        s, c = out.get(r.metric_key, (0.0, 0))
        out[r.metric_key] = (s + r.sum_value, c + r.sample_count)
    return out


def is_match_harvested(db: Session, match_id: str) -> bool:
    return db.query(BenchmarkHarvestedMatch).filter(
        BenchmarkHarvestedMatch.match_id == match_id).first() is not None


def mark_match_harvested(db: Session, match_id: str) -> None:
    db.merge(BenchmarkHarvestedMatch(match_id=match_id))
    db.commit()


# --- Generic app_state ---

def get_app_state(db: Session, key: str) -> Optional[str]:
    row = db.query(AppState).filter(AppState.key == key).first()
    return row.value if row else None


def set_app_state(db: Session, key: str, value: str) -> None:
    db.merge(AppState(key=key, value=value))
    db.commit()
