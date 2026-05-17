import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import create_engine, String, Integer, DateTime, JSON, ForeignKey, Text, Engine, text
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


def init_db(db_path: str = "analyst.db") -> Engine:
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE matches ADD COLUMN lane_opponent_champion TEXT"))
            conn.commit()
        except Exception:
            pass  # column already exists
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
