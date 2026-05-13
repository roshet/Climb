# LoL Personal Analyst Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a desktop app that auto-detects game endings, surfaces 3-5 pivotal "what if" moments per game, and provides a persistent chat interface that answers natural language questions about your match history.

**Architecture:** Electron shell spawns a FastAPI Python sidecar on startup. React UI talks to the sidecar over localhost HTTP. FastAPI owns all logic: Riot API calls, timeline analysis, counterfactual heuristics, Claude API, and SQLite storage. Electron polls a `/status` endpoint every 5 seconds to know when to show the popup.

**Tech Stack:** Electron 28, React 18, TypeScript, Vite, Tailwind CSS, FastAPI, SQLAlchemy, anthropic SDK, httpx, pytest, electron-builder

---

## File Map

```
NewProject/
├── electron/
│   └── main.ts                  # Sidecar spawn, tray, popup window, /status poll
├── src/
│   ├── chat/
│   │   ├── App.tsx              # Chat window root, message fetch/send
│   │   ├── MessageList.tsx      # Scrollable message history
│   │   └── InputBar.tsx         # Text input + submit
│   └── popup/
│       ├── App.tsx              # Popup window root, fetches latest analysis
│       ├── MomentCard.tsx       # Single pivotal moment display
│       └── Takeaway.tsx         # Biggest takeaway card
├── sidecar/
│   ├── main.py                  # FastAPI app, routes, background game watcher
│   ├── database.py              # SQLAlchemy models + all query functions
│   ├── riot_client.py           # Riot API wrapper (match-v5, timeline-v5, live client)
│   ├── timeline_analyzer.py     # Pivotal moment scoring from timeline events
│   ├── counterfactual.py        # Heuristic "what if" rules + gold impact
│   ├── claude_client.py         # Claude API, tool definitions, tool handlers
│   └── tests/
│       ├── conftest.py          # Shared fixtures (in-memory DB, sample data)
│       ├── test_database.py
│       ├── test_riot_client.py
│       ├── test_timeline_analyzer.py
│       ├── test_counterfactual.py
│       └── test_claude_client.py
├── package.json
├── tsconfig.json
├── vite.config.ts
├── electron-builder.yml
└── requirements.txt
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `vite.config.ts`
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`

- [ ] **Step 1: Initialize git and Node project**

```bash
cd "c:/Users/rohan/OneDrive/Desktop/NewProject"
git init
npm init -y
```

- [ ] **Step 2: Install Node dependencies**

```bash
npm install --save-dev electron@28 vite @vitejs/plugin-react electron-builder typescript
npm install react@18 react-dom@18
npm install --save-dev @types/react @types/react-dom @types/node
npm install tailwindcss autoprefixer postcss
npx tailwindcss init -p
```

- [ ] **Step 3: Write `package.json`**

Replace the contents of `package.json` with:

```json
{
  "name": "lol-analyst",
  "version": "0.1.0",
  "main": "dist/electron/main.js",
  "scripts": {
    "dev": "concurrently \"vite\" \"electron .\"",
    "build": "vite build && tsc -p tsconfig.electron.json",
    "package": "npm run build && electron-builder"
  },
  "dependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "@types/react": "^18.0.0",
    "@types/react-dom": "^18.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "autoprefixer": "^10.0.0",
    "concurrently": "^8.0.0",
    "electron": "^28.0.0",
    "electron-builder": "^24.0.0",
    "postcss": "^8.0.0",
    "tailwindcss": "^3.0.0",
    "typescript": "^5.0.0",
    "vite": "^5.0.0"
  }
}
```

```bash
npm install concurrently --save-dev
```

- [ ] **Step 4: Write `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020", "DOM"],
    "jsx": "react-jsx",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "rootDir": ".",
    "baseUrl": "."
  },
  "include": ["src/**/*", "electron/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

- [ ] **Step 5: Write `vite.config.ts`**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  root: 'src',
  build: {
    outDir: '../dist/renderer',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        chat: path.resolve(__dirname, 'src/chat/index.html'),
        popup: path.resolve(__dirname, 'src/popup/index.html'),
      }
    }
  },
  server: {
    port: 5173
  }
})
```

- [ ] **Step 6: Write `requirements.txt`**

```
fastapi==0.110.0
uvicorn==0.29.0
sqlalchemy==2.0.29
httpx==0.27.0
anthropic==0.25.0
pytest==8.1.1
pytest-asyncio==0.23.6
httpx[asyncio]
python-dotenv==1.0.1
```

- [ ] **Step 7: Write `.env.example`**

```
RIOT_API_KEY=RGAPI-your-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here
SUMMONER_NAME=YourSummonerName
REGION=NA1
SIDECAR_PORT=8765
```

- [ ] **Step 8: Write `.gitignore`**

```
node_modules/
dist/
.env
__pycache__/
*.pyc
sidecar/venv/
*.db
.pytest_cache/
```

- [ ] **Step 9: Set up Python virtual environment**

```bash
cd sidecar
python -m venv venv
venv/Scripts/activate   # Windows
pip install -r ../requirements.txt
cd ..
```

- [ ] **Step 10: Verify Python setup**

```bash
cd sidecar && venv/Scripts/python -m pytest --collect-only 2>&1 | head -5
```

Expected: `no tests ran` (no errors)

- [ ] **Step 11: Commit**

```bash
git add .
git commit -m "chore: project scaffolding — electron, react, python sidecar"
```

---

## Task 2: Database Layer

**Files:**
- Create: `sidecar/database.py`
- Create: `sidecar/tests/conftest.py`
- Create: `sidecar/tests/test_database.py`

- [ ] **Step 1: Write the failing tests**

Create `sidecar/tests/conftest.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from database import Base, init_db

@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
```

Create `sidecar/tests/test_database.py`:

```python
from datetime import datetime
from database import (
    Match, PivotalMoment, ChatMessage, Player,
    save_match, get_matches, save_pivotal_moments,
    get_pivotal_moments, save_chat_message, get_chat_history,
    save_player, get_player, set_pending_popup, get_pending_popup, clear_pending_popup
)

def test_save_and_retrieve_match(db):
    save_match(db, {
        "match_id": "NA1_123",
        "played_at": datetime(2026, 4, 1, 20, 0),
        "champion": "Jinx",
        "role": "BOTTOM",
        "result": "loss",
        "duration_secs": 1380,
        "kda": "5/2/8",
        "cs": 180,
        "gold_earned": 12000,
        "vision_score": 22,
        "raw_timeline": {"frames": []},
    })
    matches = get_matches(db)
    assert len(matches) == 1
    assert matches[0].champion == "Jinx"
    assert matches[0].result == "loss"

def test_save_and_retrieve_pivotal_moments(db):
    save_match(db, {
        "match_id": "NA1_123",
        "played_at": datetime(2026, 4, 1, 20, 0),
        "champion": "Jinx", "role": "BOTTOM", "result": "loss",
        "duration_secs": 1380, "kda": "5/2/8", "cs": 180,
        "gold_earned": 12000, "vision_score": 22, "raw_timeline": {},
    })
    save_pivotal_moments(db, "NA1_123", [
        {
            "timestamp_secs": 872,
            "moment_type": "recall",
            "description": "Recalled with tower at 20% HP nearby.",
            "counterfactual": "Staying to take the tower was the higher-value play. Est. cost: 400g.",
            "gold_impact": 400,
        }
    ])
    moments = get_pivotal_moments(db, ["NA1_123"])
    assert len(moments) == 1
    assert moments[0].moment_type == "recall"
    assert moments[0].gold_impact == 400

def test_chat_history_persists(db):
    save_chat_message(db, session_id="s1", match_id="NA1_123", role="user", content="Why did I lose?")
    save_chat_message(db, session_id="s1", match_id=None, role="assistant", content="You over-extended.")
    history = get_chat_history(db, session_id="s1")
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].content == "You over-extended."

def test_player_profile(db):
    save_player(db, summoner_name="TestPlayer", puuid="abc-123", region="NA1")
    player = get_player(db)
    assert player.summoner_name == "TestPlayer"
    assert player.riot_puuid == "abc-123"

def test_pending_popup_flag(db):
    assert get_pending_popup(db) is None
    set_pending_popup(db, match_id="NA1_123")
    assert get_pending_popup(db) == "NA1_123"
    clear_pending_popup(db)
    assert get_pending_popup(db) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/test_database.py -v 2>&1 | head -20
```

Expected: `ImportError: No module named 'database'`

- [ ] **Step 3: Write `sidecar/database.py`**

```python
import json
from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, String, Integer, DateTime, JSON, ForeignKey, Text
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


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


def init_db(db_path: str = "analyst.db") -> Session:
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return Session(engine)


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


# --- Pivotal moment queries ---

def save_pivotal_moments(db: Session, match_id: str, moments: list[dict]) -> None:
    for m in moments:
        db.add(PivotalMoment(match_id=match_id, **m))
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
    db.merge(Player(summoner_name=summoner_name, riot_puuid=puuid, region=region, last_synced_at=datetime.utcnow()))
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/test_database.py -v
```

Expected:
```
PASSED tests/test_database.py::test_save_and_retrieve_match
PASSED tests/test_database.py::test_save_and_retrieve_pivotal_moments
PASSED tests/test_database.py::test_chat_history_persists
PASSED tests/test_database.py::test_player_profile
PASSED tests/test_database.py::test_pending_popup_flag
5 passed
```

- [ ] **Step 5: Commit**

```bash
git add sidecar/database.py sidecar/tests/
git commit -m "feat: sqlite database layer with all models and query functions"
```

---

## Task 3: Riot API Client

**Files:**
- Create: `sidecar/riot_client.py`
- Create: `sidecar/tests/test_riot_client.py`

- [ ] **Step 1: Write the failing tests**

Create `sidecar/tests/test_riot_client.py`:

```python
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from riot_client import RiotClient

SAMPLE_PUUID = "abc-puuid-123"
SAMPLE_MATCH_ID = "NA1_4567890"

SAMPLE_MATCH = {
    "metadata": {"matchId": SAMPLE_MATCH_ID, "participants": [SAMPLE_PUUID]},
    "info": {
        "gameDuration": 1380,
        "participants": [{
            "puuid": SAMPLE_PUUID,
            "championName": "Jinx",
            "teamPosition": "BOTTOM",
            "win": False,
            "kills": 5, "deaths": 2, "assists": 8,
            "totalMinionsKilled": 180,
            "goldEarned": 12000,
            "visionScore": 22,
        }]
    }
}

SAMPLE_TIMELINE = {
    "metadata": {"matchId": SAMPLE_MATCH_ID},
    "info": {
        "frames": [
            {"timestamp": 60000, "participantFrames": {}, "events": []},
            {"timestamp": 120000, "participantFrames": {}, "events": [
                {"type": "CHAMPION_KILL", "timestamp": 95000, "killerId": 1, "victimId": 2, "position": {"x": 5000, "y": 7000}}
            ]}
        ]
    }
}

@pytest.fixture
def client():
    return RiotClient(api_key="RGAPI-test", region="NA1")

@pytest.mark.asyncio
async def test_get_match_ids(client):
    with patch.object(client._http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: [SAMPLE_MATCH_ID])
        ids = await client.get_recent_match_ids(SAMPLE_PUUID, count=1)
    assert ids == [SAMPLE_MATCH_ID]

@pytest.mark.asyncio
async def test_get_match(client):
    with patch.object(client._http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: SAMPLE_MATCH)
        match = await client.get_match(SAMPLE_MATCH_ID)
    assert match["info"]["participants"][0]["championName"] == "Jinx"

@pytest.mark.asyncio
async def test_get_timeline(client):
    with patch.object(client._http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: SAMPLE_TIMELINE)
        timeline = await client.get_timeline(SAMPLE_MATCH_ID)
    assert len(timeline["info"]["frames"]) == 2

@pytest.mark.asyncio
async def test_get_puuid_by_summoner(client):
    with patch.object(client._http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"puuid": SAMPLE_PUUID, "gameName": "TestPlayer", "tagLine": "NA1"})
        puuid = await client.get_puuid_by_summoner("TestPlayer", "NA1")
    assert puuid == SAMPLE_PUUID

@pytest.mark.asyncio
async def test_is_in_game_true(client):
    with patch.object(client._live_http, "get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        result = await client.is_in_game()
    assert result is True

@pytest.mark.asyncio
async def test_is_in_game_false_on_connection_error(client):
    with patch.object(client._live_http, "get", side_effect=httpx.ConnectError("refused")):
        result = await client.is_in_game()
    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/test_riot_client.py -v 2>&1 | head -10
```

Expected: `ImportError: No module named 'riot_client'`

- [ ] **Step 3: Write `sidecar/riot_client.py`**

```python
import httpx
from typing import Optional

REGIONAL_ROUTING = {
    "NA1": "americas", "BR1": "americas", "LAN": "americas", "LAS": "americas",
    "EUW1": "europe", "EUNE1": "europe", "TR1": "europe", "RU": "europe",
    "KR": "asia", "JP1": "asia",
    "OC1": "sea", "PH2": "sea", "SG2": "sea", "TH2": "sea", "TW2": "sea", "VN2": "sea",
}


class RiotClient:
    def __init__(self, api_key: str, region: str = "NA1"):
        self.api_key = api_key
        self.region = region
        self.regional = REGIONAL_ROUTING.get(region, "americas")
        headers = {"X-Riot-Token": api_key}
        self._http = httpx.AsyncClient(headers=headers, timeout=10.0)
        self._live_http = httpx.AsyncClient(verify=False, timeout=3.0)

    async def get_puuid_by_summoner(self, game_name: str, tag_line: str) -> str:
        url = f"https://{self.regional}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        r = self._http.get(url)
        r.raise_for_status()
        return r.json()["puuid"]

    async def get_recent_match_ids(self, puuid: str, count: int = 20) -> list[str]:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        r = self._http.get(url, params={"count": count, "queue": 420})
        r.raise_for_status()
        return r.json()

    async def get_match(self, match_id: str) -> dict:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        r = self._http.get(url)
        r.raise_for_status()
        return r.json()

    async def get_timeline(self, match_id: str) -> dict:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        r = self._http.get(url)
        r.raise_for_status()
        return r.json()

    async def is_in_game(self) -> bool:
        try:
            r = await self._live_http.get("https://127.0.0.1:2999/liveclientdata/allgamedata")
            return r.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def close(self):
        await self._http.aclose()
        await self._live_http.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/test_riot_client.py -v
```

Expected:
```
PASSED tests/test_riot_client.py::test_get_match_ids
PASSED tests/test_riot_client.py::test_get_match
PASSED tests/test_riot_client.py::test_get_timeline
PASSED tests/test_riot_client.py::test_get_puuid_by_summoner
PASSED tests/test_riot_client.py::test_is_in_game_true
PASSED tests/test_riot_client.py::test_is_in_game_false_on_connection_error
6 passed
```

- [ ] **Step 5: Commit**

```bash
git add sidecar/riot_client.py sidecar/tests/test_riot_client.py
git commit -m "feat: riot api client for match-v5, timeline-v5, and live client"
```

---

## Task 4: Timeline Analyzer

**Files:**
- Create: `sidecar/timeline_analyzer.py`
- Create: `sidecar/tests/test_timeline_analyzer.py`

The timeline analyzer receives the raw Riot timeline JSON and a participant index (0-9), and returns a list of pivotal moments sorted by gold impact descending.

- [ ] **Step 1: Write the failing tests**

Create `sidecar/tests/test_timeline_analyzer.py`:

```python
from timeline_analyzer import analyze_timeline, PivotalMomentData

PARTICIPANT_ID = 1  # 1-indexed in Riot API

def make_frame(timestamp_ms: int, events: list) -> dict:
    frames = {str(i): {"totalGold": 5000, "currentGold": 1000} for i in range(1, 11)}
    return {"timestamp": timestamp_ms, "participantFrames": frames, "events": events}

def test_detects_death_event():
    timeline = {"info": {"frames": [
        make_frame(60000, []),
        make_frame(880000, [
            {"type": "CHAMPION_KILL", "timestamp": 872000,
             "killerId": 3, "victimId": PARTICIPANT_ID,
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    death_moments = [m for m in moments if m.moment_type == "death"]
    assert len(death_moments) >= 1
    assert death_moments[0].timestamp_secs == 872

def test_detects_missed_objective():
    # Player's team (team 100, participants 1-5) didn't take dragon at 15 mins
    timeline = {"info": {"frames": [
        make_frame(900000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 905000,
             "killerId": 6,  # enemy team (participants 6-10)
             "monsterType": "DRAGON", "position": {"x": 9866, "y": 4414}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    obj_moments = [m for m in moments if m.moment_type == "objective_missed"]
    assert len(obj_moments) >= 1
    assert obj_moments[0].gold_impact >= 300

def test_detects_tower_kill_by_enemy():
    timeline = {"info": {"frames": [
        make_frame(720000, [
            {"type": "BUILDING_KILL", "timestamp": 725000,
             "killerId": 7, "teamId": 200,
             "buildingType": "TOWER_BUILDING",
             "laneType": "BOT_LANE", "towerType": "OUTER_TURRET"}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    tower_moments = [m for m in moments if m.moment_type == "tower_lost"]
    assert len(tower_moments) >= 1

def test_returns_top_5_max():
    # Generate many events
    events = [
        {"type": "CHAMPION_KILL", "timestamp": (i + 1) * 60000,
         "killerId": 3, "victimId": PARTICIPANT_ID,
         "position": {"x": 5000, "y": 7000}}
        for i in range(10)
    ]
    timeline = {"info": {"frames": [make_frame((i + 1) * 60000, [events[i]]) for i in range(10)]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    assert len(moments) <= 5

def test_sorted_by_gold_impact_descending():
    timeline = {"info": {"frames": [
        make_frame(900000, [
            {"type": "ELITE_MONSTER_KILL", "timestamp": 905000,
             "killerId": 6, "monsterType": "BARON_NASHOR",
             "position": {"x": 5007, "y": 10471}}
        ]),
        make_frame(500000, [
            {"type": "CHAMPION_KILL", "timestamp": 502000,
             "killerId": 3, "victimId": PARTICIPANT_ID,
             "position": {"x": 5000, "y": 7000}}
        ]),
    ]}}
    moments = analyze_timeline(timeline, participant_id=PARTICIPANT_ID)
    if len(moments) >= 2:
        assert moments[0].gold_impact >= moments[1].gold_impact
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/test_timeline_analyzer.py -v 2>&1 | head -10
```

Expected: `ImportError: No module named 'timeline_analyzer'`

- [ ] **Step 3: Write `sidecar/timeline_analyzer.py`**

```python
from dataclasses import dataclass

# Team 100 = participants 1-5, Team 200 = participants 6-10
TEAM_100_IDS = set(range(1, 6))
TEAM_200_IDS = set(range(6, 11))

# Gold values for objectives (approximate LoL values)
GOLD_VALUES = {
    "DRAGON": 350,
    "BARON_NASHOR": 900,
    "RIFTHERALD": 400,
    "TOWER_OUTER": 150,
    "TOWER_INNER": 250,
    "TOWER_BASE": 350,
    "INHIBITOR": 400,
    "DEATH": 300,  # approximate bounty
}


@dataclass
class PivotalMomentData:
    timestamp_secs: int
    moment_type: str
    description: str
    counterfactual: str
    gold_impact: int


def _player_team(participant_id: int) -> set:
    return TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS


def _enemy_team(participant_id: int) -> set:
    return TEAM_200_IDS if participant_id in TEAM_100_IDS else TEAM_100_IDS


def _score_death(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("victimId") != participant_id:
        return None
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="death",
        description=f"You died at {mins}:{secs:02d}.",
        counterfactual="Avoiding this death would have kept pressure on the map and denied your bounty.",
        gold_impact=GOLD_VALUES["DEATH"],
    )


def _score_objective(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "ELITE_MONSTER_KILL":
        return None
    enemy_team = _enemy_team(participant_id)
    killer_id = event.get("killerId", 0)
    if killer_id not in enemy_team:
        return None  # our team took it
    monster = event.get("monsterType", "UNKNOWN")
    gold = GOLD_VALUES.get(monster, 300)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="objective_missed",
        description=f"Enemy team secured {monster.replace('_', ' ').title()} at {mins}:{secs:02d}.",
        counterfactual=f"Your team missing this objective gave the enemy a ~{gold}g advantage and map pressure.",
        gold_impact=gold,
    )


def _score_tower(event: dict, participant_id: int) -> PivotalMomentData | None:
    if event.get("type") != "BUILDING_KILL":
        return None
    enemy_team = _enemy_team(participant_id)
    killer_id = event.get("killerId", 0)
    if killer_id not in enemy_team:
        return None  # our team took it
    tower_type = event.get("towerType", "OUTER_TURRET")
    gold = GOLD_VALUES.get(f"TOWER_{tower_type.replace('_TURRET', '')}", 150)
    ts = event["timestamp"] // 1000
    mins, secs = divmod(ts, 60)
    lane = event.get("laneType", "").replace("_LANE", "").title()
    return PivotalMomentData(
        timestamp_secs=ts,
        moment_type="tower_lost",
        description=f"Enemy took your {lane} {tower_type.replace('_', ' ').lower()} at {mins}:{secs:02d}.",
        counterfactual=f"Losing this tower opened your base and gave the enemy ~{gold}g.",
        gold_impact=gold,
    )


def analyze_timeline(timeline: dict, participant_id: int) -> list[PivotalMomentData]:
    moments: list[PivotalMomentData] = []
    frames = timeline.get("info", {}).get("frames", [])

    for frame in frames:
        for event in frame.get("events", []):
            event_type = event.get("type")
            moment = None
            if event_type == "CHAMPION_KILL":
                moment = _score_death(event, participant_id)
            elif event_type == "ELITE_MONSTER_KILL":
                moment = _score_objective(event, participant_id)
            elif event_type == "BUILDING_KILL":
                moment = _score_tower(event, participant_id)
            if moment:
                moments.append(moment)

    moments.sort(key=lambda m: m.gold_impact, reverse=True)
    return moments[:5]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/test_timeline_analyzer.py -v
```

Expected:
```
PASSED tests/test_timeline_analyzer.py::test_detects_death_event
PASSED tests/test_timeline_analyzer.py::test_detects_missed_objective
PASSED tests/test_timeline_analyzer.py::test_detects_tower_kill_by_enemy
PASSED tests/test_timeline_analyzer.py::test_returns_top_5_max
PASSED tests/test_timeline_analyzer.py::test_sorted_by_gold_impact_descending
5 passed
```

- [ ] **Step 5: Commit**

```bash
git add sidecar/timeline_analyzer.py sidecar/tests/test_timeline_analyzer.py
git commit -m "feat: timeline analyzer — pivotal moment detection from riot timeline events"
```

---

## Task 5: Counterfactual Engine

**Files:**
- Create: `sidecar/counterfactual.py`
- Create: `sidecar/tests/test_counterfactual.py`

The counterfactual engine enriches each `PivotalMomentData` with a specific "what if" explanation, turning raw event detection into coaching feedback.

- [ ] **Step 1: Write the failing tests**

Create `sidecar/tests/test_counterfactual.py`:

```python
from counterfactual import enrich_moments
from timeline_analyzer import PivotalMomentData

def make_moment(moment_type: str, gold_impact: int = 300, timestamp_secs: int = 600) -> PivotalMomentData:
    return PivotalMomentData(
        timestamp_secs=timestamp_secs,
        moment_type=moment_type,
        description="Test description.",
        counterfactual="",
        gold_impact=gold_impact,
    )

def test_death_early_game_counterfactual():
    moment = make_moment("death", timestamp_secs=480)  # 8 mins
    enriched = enrich_moments([moment])
    assert "recall" in enriched[0].counterfactual.lower() or "back" in enriched[0].counterfactual.lower() or "death" in enriched[0].counterfactual.lower()

def test_objective_missed_baron_counterfactual():
    moment = PivotalMomentData(
        timestamp_secs=1200,
        moment_type="objective_missed",
        description="Enemy team secured Baron Nashor at 20:00.",
        counterfactual="",
        gold_impact=900,
    )
    enriched = enrich_moments([moment])
    assert "baron" in enriched[0].counterfactual.lower() or "900" in enriched[0].counterfactual or "objective" in enriched[0].counterfactual.lower()

def test_tower_lost_counterfactual():
    moment = make_moment("tower_lost", gold_impact=250)
    enriched = enrich_moments([moment])
    assert len(enriched[0].counterfactual) > 20

def test_all_moments_get_counterfactuals():
    moments = [
        make_moment("death", timestamp_secs=300),
        make_moment("objective_missed", gold_impact=400),
        make_moment("tower_lost", gold_impact=200),
    ]
    enriched = enrich_moments(moments)
    assert all(len(m.counterfactual) > 10 for m in enriched)

def test_preserves_order():
    moments = [make_moment("death", timestamp_secs=i * 60) for i in range(3)]
    enriched = enrich_moments(moments)
    assert [m.timestamp_secs for m in enriched] == [m.timestamp_secs for m in moments]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/test_counterfactual.py -v 2>&1 | head -10
```

Expected: `ImportError: No module named 'counterfactual'`

- [ ] **Step 3: Write `sidecar/counterfactual.py`**

```python
from timeline_analyzer import PivotalMomentData


def _counterfactual_for_death(moment: PivotalMomentData) -> str:
    mins = moment.timestamp_secs // 60
    if mins < 10:
        return (
            f"Dying at {mins} minutes in the early game is high cost — you missed CS, "
            f"XP, and gave your opponent a lead. Playing safer or recalling when low "
            f"would have preserved your lane advantage."
        )
    elif mins < 20:
        return (
            f"This death at {mins} minutes likely disrupted your team's mid-game tempo. "
            f"Fights in this window often decide which team gets the first major objective. "
            f"Consider whether the fight was necessary or if backing was the safer call."
        )
    else:
        return (
            f"Late-game deaths at {mins} minutes can be game-ending — respawn timers are long "
            f"and the enemy can convert a kill into an inhibitor or Baron. "
            f"Staying grouped and avoiding solo plays is the highest-value choice here."
        )


def _counterfactual_for_objective(moment: PivotalMomentData) -> str:
    gold = moment.gold_impact
    desc_lower = moment.description.lower()
    if "baron" in desc_lower:
        return (
            f"Baron Nashor is the most impactful objective in the game (~{gold}g team advantage + buff). "
            f"When Baron spawns, your team should be grouped and contesting or forcing the enemy away. "
            f"Securing or denying Baron often determines the winner."
        )
    elif "dragon" in desc_lower:
        return (
            f"Each Dragon soul stack is worth roughly {gold}g in stats and compounds over the game. "
            f"Letting the enemy stack Dragons for free accelerates their scaling. "
            f"Contesting Dragon when you have lane priority is a high-value play."
        )
    else:
        return (
            f"Your team missed an objective worth ~{gold}g in team advantage. "
            f"Grouping around spawn timers and converting lane pressure into objectives "
            f"is one of the highest-leverage macro habits to build."
        )


def _counterfactual_for_tower(moment: PivotalMomentData) -> str:
    gold = moment.gold_impact
    return (
        f"Losing this tower gave the enemy ~{gold}g and opened a new avenue into your base. "
        f"Towers are best defended by not giving the enemy free time to siege — "
        f"rotating when you see your laner backing or being outnumbered prevents this."
    )


def enrich_moments(moments: list[PivotalMomentData]) -> list[PivotalMomentData]:
    for moment in moments:
        if moment.moment_type == "death":
            moment.counterfactual = _counterfactual_for_death(moment)
        elif moment.moment_type == "objective_missed":
            moment.counterfactual = _counterfactual_for_objective(moment)
        elif moment.moment_type == "tower_lost":
            moment.counterfactual = _counterfactual_for_tower(moment)
        elif not moment.counterfactual:
            moment.counterfactual = f"This event had an estimated ~{moment.gold_impact}g impact on the game outcome."
    return moments
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/test_counterfactual.py -v
```

Expected:
```
PASSED tests/test_counterfactual.py::test_death_early_game_counterfactual
PASSED tests/test_counterfactual.py::test_objective_missed_baron_counterfactual
PASSED tests/test_counterfactual.py::test_tower_lost_counterfactual
PASSED tests/test_counterfactual.py::test_all_moments_get_counterfactuals
PASSED tests/test_counterfactual.py::test_preserves_order
5 passed
```

- [ ] **Step 5: Commit**

```bash
git add sidecar/counterfactual.py sidecar/tests/test_counterfactual.py
git commit -m "feat: counterfactual engine with heuristic coaching rules per moment type"
```

---

## Task 6: Claude API Integration

**Files:**
- Create: `sidecar/claude_client.py`
- Create: `sidecar/tests/test_claude_client.py`

Claude receives the player's question, a summary of recent match history, and tools to query the database for more detail. It returns a natural language coaching response.

- [ ] **Step 1: Write the failing tests**

Create `sidecar/tests/test_claude_client.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from claude_client import ClaudeClient, build_system_prompt

def test_build_system_prompt_includes_player_name():
    prompt = build_system_prompt("TestPlayer")
    assert "TestPlayer" in prompt
    assert "analyst" in prompt.lower() or "coach" in prompt.lower()

def test_build_system_prompt_mentions_tools():
    prompt = build_system_prompt("TestPlayer")
    assert "get_matches" in prompt or "tool" in prompt.lower()

def test_claude_client_formats_tool_result_get_matches():
    db = MagicMock()
    mock_match = MagicMock()
    mock_match.match_id = "NA1_123"
    mock_match.champion = "Jinx"
    mock_match.result = "loss"
    mock_match.played_at.isoformat.return_value = "2026-04-01T20:00:00"
    mock_match.kda = "5/2/8"
    mock_match.cs = 180
    mock_match.gold_earned = 12000
    mock_match.vision_score = 22

    from database import get_matches
    with patch("claude_client.get_matches", return_value=[mock_match]):
        client = ClaudeClient(api_key="test-key", db=db)
        result = client._handle_tool("get_matches", {"result": "loss", "last_n": 5})

    assert "Jinx" in result
    assert "loss" in result

def test_claude_client_formats_tool_result_get_champion_stats():
    db = MagicMock()
    mock_match = MagicMock()
    mock_match.champion = "Jinx"
    mock_match.result = "win"
    mock_match.kda = "8/1/5"
    mock_match.cs = 210
    mock_match.gold_earned = 15000
    mock_match.vision_score = 25

    with patch("claude_client.get_matches", return_value=[mock_match]):
        client = ClaudeClient(api_key="test-key", db=db)
        result = client._handle_tool("get_champion_stats", {"champion": "Jinx", "last_n": 10})

    assert "Jinx" in result
    assert "win" in result.lower() or "1" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/test_claude_client.py -v 2>&1 | head -10
```

Expected: `ImportError: No module named 'claude_client'`

- [ ] **Step 3: Write `sidecar/claude_client.py`**

```python
import json
from sqlalchemy.orm import Session
import anthropic
from database import get_matches, get_pivotal_moments

TOOLS = [
    {
        "name": "get_matches",
        "description": "Query the player's match history. Returns matches filtered by champion, result, and/or date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "champion": {"type": "string", "description": "Filter by champion name, e.g. 'Jinx'"},
                "result": {"type": "string", "enum": ["win", "loss"], "description": "Filter by game result"},
                "last_n": {"type": "integer", "description": "Number of most recent matches to return (default 20)"},
            }
        }
    },
    {
        "name": "get_pivotal_moments",
        "description": "Get the pivotal moments and counterfactuals for specific match IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "match_ids": {"type": "array", "items": {"type": "string"}, "description": "List of match IDs"}
            },
            "required": ["match_ids"]
        }
    },
    {
        "name": "get_champion_stats",
        "description": "Get aggregated stats for a specific champion over the player's recent games.",
        "input_schema": {
            "type": "object",
            "properties": {
                "champion": {"type": "string", "description": "Champion name"},
                "last_n": {"type": "integer", "description": "Number of recent games to include (default 20)"}
            },
            "required": ["champion"]
        }
    }
]


def build_system_prompt(summoner_name: str) -> str:
    return f"""You are a personal League of Legends analyst and coach for {summoner_name}.

You have access to their full match history through these tools:
- get_matches: query matches by champion, result, or recency
- get_pivotal_moments: get the specific pivotal moments analyzed for any match
- get_champion_stats: get aggregated stats for a champion

When answering questions:
- Always use real data from the tools rather than speaking in generalities
- Reference specific games, timestamps, and statistics when possible
- Be direct about patterns you see — don't soften findings to be polite
- Prioritize the single most impactful thing the player should change
- Keep responses concise and actionable

Speak like a knowledgeable coach who has watched every game, not a generic tip site."""


def _format_matches(matches) -> str:
    if not matches:
        return "No matches found."
    lines = []
    for m in matches:
        lines.append(f"- {m.match_id}: {m.champion} {m.result.upper()} | KDA {m.kda} | CS {m.cs} | Gold {m.gold_earned} | Vision {m.vision_score} | {m.played_at.isoformat()}")
    return "\n".join(lines)


def _format_moments(moments) -> str:
    if not moments:
        return "No pivotal moments found."
    lines = []
    for m in moments:
        mins, secs = divmod(m.timestamp_secs, 60)
        lines.append(f"- [{m.match_id}] {mins}:{secs:02d} {m.moment_type}: {m.description} | Counterfactual: {m.counterfactual} | Impact: ~{m.gold_impact}g")
    return "\n".join(lines)


class ClaudeClient:
    def __init__(self, api_key: str, db: Session):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.db = db

    def _handle_tool(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "get_matches":
            matches = get_matches(
                self.db,
                champion=tool_input.get("champion"),
                result=tool_input.get("result"),
                last_n=tool_input.get("last_n", 20),
            )
            return _format_matches(matches)

        elif tool_name == "get_pivotal_moments":
            moments = get_pivotal_moments(self.db, tool_input["match_ids"])
            return _format_moments(moments)

        elif tool_name == "get_champion_stats":
            matches = get_matches(
                self.db,
                champion=tool_input["champion"],
                last_n=tool_input.get("last_n", 20),
            )
            if not matches:
                return f"No games found on {tool_input['champion']}."
            wins = sum(1 for m in matches if m.result == "win")
            avg_cs = sum(m.cs for m in matches) / len(matches)
            avg_gold = sum(m.gold_earned for m in matches) / len(matches)
            return (
                f"{tool_input['champion']} over last {len(matches)} games: "
                f"{wins}W/{len(matches)-wins}L ({100*wins//len(matches)}% WR) | "
                f"Avg CS: {avg_cs:.0f} | Avg Gold: {avg_gold:.0f}"
            )
        return "Unknown tool."

    def chat(self, summoner_name: str, messages: list[dict], match_context: str | None = None) -> str:
        system = build_system_prompt(summoner_name)
        if match_context:
            system += f"\n\nCurrent game context:\n{match_context}"

        api_messages = list(messages)

        while True:
            response = self.client.messages.create(
                model="claude-opus-4-6",
                max_tokens=1024,
                system=system,
                tools=TOOLS,
                messages=api_messages,
            )

            if response.stop_reason == "end_turn":
                return "".join(block.text for block in response.content if hasattr(block, "text"))

            # Handle tool use
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if not tool_uses:
                return "".join(block.text for block in response.content if hasattr(block, "text"))

            api_messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tool_use in tool_uses:
                result = self._handle_tool(tool_use.name, tool_use.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result,
                })
            api_messages.append({"role": "user", "content": tool_results})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/test_claude_client.py -v
```

Expected:
```
PASSED tests/test_claude_client.py::test_build_system_prompt_includes_player_name
PASSED tests/test_claude_client.py::test_build_system_prompt_mentions_tools
PASSED tests/test_claude_client.py::test_claude_client_formats_tool_result_get_matches
PASSED tests/test_claude_client.py::test_claude_client_formats_tool_result_get_champion_stats
4 passed
```

- [ ] **Step 5: Commit**

```bash
git add sidecar/claude_client.py sidecar/tests/test_claude_client.py
git commit -m "feat: claude api integration with tool use for match history queries"
```

---

## Task 7: FastAPI Application

**Files:**
- Create: `sidecar/main.py`

This wires all sidecar modules together into a running API. It also runs the game-end watcher as a background task.

- [ ] **Step 1: Write `sidecar/main.py`**

```python
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from claude_client import ClaudeClient
from counterfactual import enrich_moments
from database import (
    clear_pending_popup, get_chat_history, get_matches, get_pending_popup,
    get_pivotal_moments, get_player, init_db, save_chat_message, save_match,
    save_pivotal_moments, save_player, set_pending_popup,
)
from riot_client import RiotClient
from timeline_analyzer import analyze_timeline

load_dotenv()

RIOT_API_KEY = os.environ["RIOT_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SUMMONER_NAME = os.environ.get("SUMMONER_NAME", "")
REGION = os.environ.get("REGION", "NA1")

db: Session = init_db("analyst.db")
riot = RiotClient(api_key=RIOT_API_KEY, region=REGION)
claude = ClaudeClient(api_key=ANTHROPIC_API_KEY, db=db)

_watcher_task: Optional[asyncio.Task] = None


async def game_end_watcher():
    """Poll Live Client API. When in-game state drops, trigger analysis."""
    was_in_game = False
    while True:
        in_game = await riot.is_in_game()
        if was_in_game and not in_game:
            await run_post_game_analysis()
        was_in_game = in_game
        await asyncio.sleep(5)


async def run_post_game_analysis():
    player = get_player(db)
    if not player:
        return
    try:
        match_ids = await riot.get_recent_match_ids(player.riot_puuid, count=1)
        if not match_ids:
            return
        match_id = match_ids[0]
        existing = get_matches(db, last_n=1)
        if existing and existing[0].match_id == match_id:
            return  # already analyzed

        match_data = await riot.get_match(match_id)
        timeline_data = await riot.get_timeline(match_id)

        info = match_data["info"]
        puuid = player.riot_puuid
        participants = info["participants"]
        participant = next(p for p in participants if p["puuid"] == puuid)
        participant_index = participants.index(participant) + 1  # 1-indexed

        save_match(db, {
            "match_id": match_id,
            "played_at": datetime.utcfromtimestamp(info["gameStartTimestamp"] / 1000),
            "champion": participant["championName"],
            "role": participant.get("teamPosition", "UNKNOWN"),
            "result": "win" if participant["win"] else "loss",
            "duration_secs": info["gameDuration"],
            "kda": f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
            "cs": participant["totalMinionsKilled"],
            "gold_earned": participant["goldEarned"],
            "vision_score": participant["visionScore"],
            "raw_timeline": timeline_data,
        })

        moments = analyze_timeline(timeline_data, participant_id=participant_index)
        enriched = enrich_moments(moments)
        save_pivotal_moments(db, match_id, [
            {
                "timestamp_secs": m.timestamp_secs,
                "moment_type": m.moment_type,
                "description": m.description,
                "counterfactual": m.counterfactual,
                "gold_impact": m.gold_impact,
            }
            for m in enriched
        ])

        set_pending_popup(db, match_id=match_id)
    except Exception as e:
        print(f"[watcher] Error during post-game analysis: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _watcher_task
    _watcher_task = asyncio.create_task(game_end_watcher())
    yield
    if _watcher_task:
        _watcher_task.cancel()
    await riot.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- Routes ---

@app.get("/status")
def status():
    pending = get_pending_popup(db)
    return {"pending_popup": pending}


@app.post("/status/clear")
def clear_status():
    clear_pending_popup(db)
    return {"ok": True}


@app.get("/analysis/{match_id}")
def get_analysis(match_id: str):
    matches = get_matches(db, last_n=50)
    match = next((m for m in matches if m.match_id == match_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    moments = get_pivotal_moments(db, [match_id])
    return {
        "match_id": match_id,
        "champion": match.champion,
        "result": match.result,
        "duration_secs": match.duration_secs,
        "kda": match.kda,
        "moments": [
            {
                "timestamp_secs": m.timestamp_secs,
                "moment_type": m.moment_type,
                "description": m.description,
                "counterfactual": m.counterfactual,
                "gold_impact": m.gold_impact,
            }
            for m in moments
        ],
    }


class ChatRequest(BaseModel):
    session_id: str
    message: str
    match_id: Optional[str] = None


@app.post("/chat")
def chat(req: ChatRequest):
    player = get_player(db)
    if not player:
        raise HTTPException(status_code=400, detail="Player profile not set up")

    save_chat_message(db, session_id=req.session_id, match_id=req.match_id, role="user", content=req.message)

    history = get_chat_history(db, session_id=req.session_id)
    messages = [{"role": m.role, "content": m.content} for m in history]

    match_context = None
    if req.match_id:
        moments = get_pivotal_moments(db, [req.match_id])
        if moments:
            match_context = "\n".join(f"- {m.description} {m.counterfactual}" for m in moments)

    response = claude.chat(
        summoner_name=player.summoner_name,
        messages=messages,
        match_context=match_context,
    )

    save_chat_message(db, session_id=req.session_id, match_id=req.match_id, role="assistant", content=response)
    return {"response": response}


class SetupRequest(BaseModel):
    summoner_name: str
    tag_line: str
    region: str


@app.post("/setup")
async def setup(req: SetupRequest):
    riot.region = req.region
    riot.regional = RiotClient.__init__.__code__  # handled internally
    try:
        puuid = await riot.get_puuid_by_summoner(req.summoner_name, req.tag_line)
        save_player(db, summoner_name=req.summoner_name, puuid=puuid, region=req.region)
        return {"ok": True, "puuid": puuid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/matches")
def list_matches(champion: Optional[str] = None, result: Optional[str] = None, last_n: int = 20):
    matches = get_matches(db, champion=champion, result=result, last_n=last_n)
    return [
        {
            "match_id": m.match_id,
            "champion": m.champion,
            "result": m.result,
            "kda": m.kda,
            "cs": m.cs,
            "played_at": m.played_at.isoformat(),
        }
        for m in matches
    ]
```

- [ ] **Step 2: Verify the sidecar starts without errors**

First copy `.env.example` to `.env` and fill in your Riot API key and Anthropic API key.

```bash
cp .env.example .env
# Edit .env with your real keys, then:
cd sidecar
venv/Scripts/python -m uvicorn main:app --port 8765 --reload
```

Expected output: `INFO: Application startup complete.`

Stop the server with Ctrl+C.

- [ ] **Step 3: Run all sidecar tests together**

```bash
cd sidecar
venv/Scripts/python -m pytest tests/ -v
```

Expected: All previously written tests pass. `main.py` has no unit tests (it's integration glue — tested via Electron in Task 8).

- [ ] **Step 4: Commit**

```bash
git add sidecar/main.py
git commit -m "feat: fastapi sidecar with all routes — status, analysis, chat, setup, matches"
```

---

## Task 8: Electron Main Process

**Files:**
- Create: `electron/main.ts`
- Create: `electron/preload.ts`

- [ ] **Step 1: Create HTML entry points for the two React windows**

Create `src/chat/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>LoL Analyst</title></head>
<body>
  <div id="root"></div>
  <script type="module" src="./App.tsx"></script>
</body>
</html>
```

Create `src/popup/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Game Analysis</title></head>
<body>
  <div id="root"></div>
  <script type="module" src="./App.tsx"></script>
</body>
</html>
```

- [ ] **Step 2: Write `electron/preload.ts`**

```typescript
import { contextBridge } from 'electron'

// Minimal preload — UI talks directly to FastAPI over HTTP
// Only expose the sidecar port so React knows where to connect
contextBridge.exposeInMainWorld('sidecar', {
  port: process.env.SIDECAR_PORT || '8765',
})
```

- [ ] **Step 3: Write `electron/main.ts`**

```typescript
import { app, BrowserWindow, Tray, Menu, nativeImage } from 'electron'
import path from 'path'
import { spawn, ChildProcess } from 'child_process'

const SIDECAR_PORT = process.env.SIDECAR_PORT || '8765'
const SIDECAR_URL = `http://localhost:${SIDECAR_PORT}`
const isDev = process.env.NODE_ENV === 'development'

let tray: Tray | null = null
let chatWindow: BrowserWindow | null = null
let popupWindow: BrowserWindow | null = null
let sidecarProcess: ChildProcess | null = null
let statusPollInterval: ReturnType<typeof setInterval> | null = null

// --- Sidecar Management ---

function startSidecar() {
  const pythonPath = isDev
    ? path.join(__dirname, '..', 'sidecar', 'venv', 'Scripts', 'python.exe')
    : path.join(process.resourcesPath, 'sidecar', 'venv', 'Scripts', 'python.exe')

  const sidecarScript = isDev
    ? path.join(__dirname, '..', 'sidecar', 'main.py')
    : path.join(process.resourcesPath, 'sidecar', 'main.py')

  sidecarProcess = spawn(pythonPath, ['-m', 'uvicorn', 'main:app', '--port', SIDECAR_PORT], {
    cwd: path.dirname(sidecarScript),
    env: { ...process.env },
  })

  sidecarProcess.stdout?.on('data', (d) => console.log('[sidecar]', d.toString().trim()))
  sidecarProcess.stderr?.on('data', (d) => console.error('[sidecar]', d.toString().trim()))
}

function stopSidecar() {
  if (sidecarProcess) {
    sidecarProcess.kill()
    sidecarProcess = null
  }
}

// --- Window Management ---

function createChatWindow() {
  if (chatWindow) {
    chatWindow.focus()
    return
  }
  chatWindow = new BrowserWindow({
    width: 480,
    height: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
    title: 'LoL Analyst',
    backgroundColor: '#1a1a2e',
  })
  const url = isDev
    ? 'http://localhost:5173/chat/index.html'
    : `file://${path.join(__dirname, '../renderer/chat/index.html')}`
  chatWindow.loadURL(url)
  chatWindow.on('closed', () => { chatWindow = null })
}

function showPopup(matchId: string) {
  if (popupWindow) {
    popupWindow.close()
  }
  popupWindow = new BrowserWindow({
    width: 380,
    height: 520,
    frame: false,
    alwaysOnTop: true,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
    backgroundColor: '#1a1a2e',
  })

  const url = isDev
    ? `http://localhost:5173/popup/index.html?matchId=${matchId}`
    : `file://${path.join(__dirname, '../renderer/popup/index.html')}?matchId=${matchId}`

  popupWindow.loadURL(url)

  // Position bottom-right
  const { width, height } = require('electron').screen.getPrimaryDisplay().workAreaSize
  popupWindow.setPosition(width - 400, height - 540)

  // Auto-dismiss after 60 seconds
  setTimeout(() => {
    if (popupWindow && !popupWindow.isDestroyed()) {
      popupWindow.close()
    }
  }, 60000)

  popupWindow.on('closed', () => { popupWindow = null })
}

// --- Status Polling ---

async function pollStatus() {
  try {
    const res = await fetch(`${SIDECAR_URL}/status`)
    if (!res.ok) return
    const data = await res.json() as { pending_popup: string | null }
    if (data.pending_popup) {
      showPopup(data.pending_popup)
      await fetch(`${SIDECAR_URL}/status/clear`, { method: 'POST' })
    }
  } catch {
    // Sidecar not ready yet
  }
}

// --- Tray ---

function createTray() {
  const icon = nativeImage.createEmpty()
  tray = new Tray(icon)
  const menu = Menu.buildFromTemplate([
    { label: 'Open Chat', click: createChatWindow },
    { type: 'separator' },
    { label: 'Quit', click: () => app.quit() },
  ])
  tray.setContextMenu(menu)
  tray.setToolTip('LoL Analyst')
  tray.on('click', createChatWindow)
}

// --- App Lifecycle ---

app.whenReady().then(() => {
  startSidecar()
  createTray()

  // Wait 3s for sidecar to boot, then start polling
  setTimeout(() => {
    statusPollInterval = setInterval(pollStatus, 5000)
  }, 3000)
})

app.on('window-all-closed', (e: Event) => {
  e.preventDefault() // Keep running in tray
})

app.on('before-quit', () => {
  if (statusPollInterval) clearInterval(statusPollInterval)
  stopSidecar()
})
```

- [ ] **Step 4: Add tsconfig for Electron compilation**

Create `tsconfig.electron.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "dist/electron",
    "rootDir": "electron"
  },
  "include": ["electron/**/*"]
}
```

- [ ] **Step 5: Compile and verify no TypeScript errors**

```bash
npx tsc -p tsconfig.electron.json --noEmit
```

Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add electron/ src/chat/index.html src/popup/index.html tsconfig.electron.json
git commit -m "feat: electron main process — sidecar spawn, tray, popup window, status polling"
```

---

## Task 9: React Popup UI

**Files:**
- Create: `src/popup/App.tsx`
- Create: `src/popup/MomentCard.tsx`
- Create: `src/popup/Takeaway.tsx`

- [ ] **Step 1: Write `src/popup/MomentCard.tsx`**

```tsx
interface MomentCardProps {
  timestampSecs: number
  momentType: string
  description: string
  counterfactual: string
  goldImpact: number
}

export function MomentCard({ timestampSecs, description, counterfactual, goldImpact }: MomentCardProps) {
  const mins = Math.floor(timestampSecs / 60)
  const secs = timestampSecs % 60
  const time = `${mins}:${secs.toString().padStart(2, '0')}`

  return (
    <div className="border border-yellow-500/30 bg-yellow-500/5 rounded-lg p-3 mb-2">
      <div className="flex items-start gap-2">
        <span className="text-yellow-400 text-sm font-mono mt-0.5">⚠ {time}</span>
        <div>
          <p className="text-white text-sm">{description}</p>
          <p className="text-gray-400 text-xs mt-1">{counterfactual}</p>
          <p className="text-yellow-500/70 text-xs mt-1">~{goldImpact}g impact</p>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Write `src/popup/Takeaway.tsx`**

```tsx
interface TakeawayProps {
  champion: string
  result: 'win' | 'loss'
  durationSecs: number
  kda: string
}

export function Takeaway({ champion, result, durationSecs, kda }: TakeawayProps) {
  const mins = Math.floor(durationSecs / 60)
  const resultColor = result === 'win' ? 'text-blue-400' : 'text-red-400'

  return (
    <div className="border-t border-white/10 pt-3 mt-3">
      <div className="flex justify-between items-center mb-2">
        <span className="text-gray-300 text-sm font-medium">{champion}</span>
        <span className={`text-sm font-bold uppercase ${resultColor}`}>{result}</span>
      </div>
      <div className="flex gap-3 text-xs text-gray-500">
        <span>KDA {kda}</span>
        <span>{mins}m</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Write `src/popup/App.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MomentCard } from './MomentCard'
import { Takeaway } from './Takeaway'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Moment {
  timestamp_secs: number
  moment_type: string
  description: string
  counterfactual: string
  gold_impact: number
}

interface Analysis {
  match_id: string
  champion: string
  result: 'win' | 'loss'
  duration_secs: number
  kda: string
  moments: Moment[]
}

function getMatchId(): string | null {
  return new URLSearchParams(window.location.search).get('matchId')
}

function PopupApp() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [loading, setLoading] = useState(true)

  const port = window.sidecar?.port ?? '8765'
  const matchId = getMatchId()

  useEffect(() => {
    if (!matchId) { setLoading(false); return }
    fetch(`http://localhost:${port}/analysis/${matchId}`)
      .then(r => r.json())
      .then(data => { setAnalysis(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [matchId, port])

  const openChat = () => {
    fetch(`http://localhost:${port}/open-chat`, { method: 'POST' })
  }

  if (loading) {
    return (
      <div className="bg-[#1a1a2e] min-h-screen flex items-center justify-center">
        <p className="text-gray-400 text-sm">Analyzing game...</p>
      </div>
    )
  }

  if (!analysis) {
    return (
      <div className="bg-[#1a1a2e] min-h-screen flex items-center justify-center">
        <p className="text-red-400 text-sm">Could not load analysis.</p>
      </div>
    )
  }

  return (
    <div className="bg-[#1a1a2e] min-h-screen p-4 text-white font-sans">
      <div className="flex justify-between items-center mb-3">
        <h1 className="text-white font-bold text-base">Game Analysis</h1>
        <button
          onClick={() => window.close()}
          className="text-gray-500 hover:text-white text-lg leading-none"
        >✕</button>
      </div>

      <div className="mb-3">
        <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Pivotal Moments</p>
        {analysis.moments.length === 0
          ? <p className="text-gray-400 text-sm">No pivotal moments detected.</p>
          : analysis.moments.map((m, i) => (
              <MomentCard key={i}
                timestampSecs={m.timestamp_secs}
                momentType={m.moment_type}
                description={m.description}
                counterfactual={m.counterfactual}
                goldImpact={m.gold_impact}
              />
            ))
        }
      </div>

      <Takeaway
        champion={analysis.champion}
        result={analysis.result}
        durationSecs={analysis.duration_secs}
        kda={analysis.kda}
      />

      <button
        onClick={openChat}
        className="w-full mt-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
      >
        Ask about this game →
      </button>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<PopupApp />)
```

- [ ] **Step 4: Create shared CSS entry**

Create `src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  margin: 0;
  background-color: #1a1a2e;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
```

- [ ] **Step 5: Commit**

```bash
git add src/popup/ src/index.css
git commit -m "feat: popup UI — pivotal moment cards, game summary, ask-about-game button"
```

---

## Task 10: React Chat UI

**Files:**
- Create: `src/chat/App.tsx`
- Create: `src/chat/MessageList.tsx`
- Create: `src/chat/InputBar.tsx`

- [ ] **Step 1: Write `src/chat/MessageList.tsx`**

```tsx
import { useEffect, useRef } from 'react'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export function MessageList({ messages }: { messages: Message[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
      {messages.map((msg, i) => (
        <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
          <div className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
            msg.role === 'user'
              ? 'bg-blue-600 text-white rounded-br-sm'
              : 'bg-white/10 text-gray-100 rounded-bl-sm'
          }`}>
            {msg.content}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
```

- [ ] **Step 2: Write `src/chat/InputBar.tsx`**

```tsx
import { useState, KeyboardEvent } from 'react'

interface InputBarProps {
  onSend: (message: string) => void
  disabled: boolean
}

export function InputBar({ onSend, disabled }: InputBarProps) {
  const [value, setValue] = useState('')

  const submit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="border-t border-white/10 p-3 flex gap-2 items-end">
      <textarea
        className="flex-1 bg-white/10 text-white text-sm rounded-xl px-3 py-2 resize-none outline-none placeholder-gray-500 min-h-[40px] max-h-[120px]"
        placeholder="Ask anything about your games..."
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        disabled={disabled}
      />
      <button
        onClick={submit}
        disabled={disabled || !value.trim()}
        className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-xl px-3 py-2 text-sm transition-colors"
      >
        ↑
      </button>
    </div>
  )
}
```

- [ ] **Step 3: Write `src/chat/App.tsx`**

```tsx
import { useState, useEffect, useCallback } from 'react'
import { createRoot } from 'react-dom/client'
import { MessageList } from './MessageList'
import { InputBar } from './InputBar'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const SESSION_ID = `session-${Date.now()}`

function ChatApp() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: "Hi! I'm your personal LoL analyst. Ask me anything about your games — patterns, mistakes, champion performance, or what to focus on to climb." }
  ])
  const [loading, setLoading] = useState(false)
  const [matchId] = useState<string | null>(
    new URLSearchParams(window.location.search).get('matchId')
  )

  const port = window.sidecar?.port ?? '8765'

  const sendMessage = useCallback(async (text: string) => {
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)
    try {
      const res = await fetch(`http://localhost:${port}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: SESSION_ID, message: text, match_id: matchId }),
      })
      const data = await res.json() as { response: string }
      setMessages(prev => [...prev, { role: 'assistant', content: data.response }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error connecting to analyst. Is the sidecar running?' }])
    } finally {
      setLoading(false)
    }
  }, [port, matchId])

  return (
    <div className="bg-[#1a1a2e] h-screen flex flex-col text-white font-sans">
      <div className="border-b border-white/10 px-4 py-3 flex items-center justify-between">
        <h1 className="font-bold text-base">LoL Analyst</h1>
        {matchId && <span className="text-xs text-blue-400">Viewing specific game</span>}
      </div>
      <MessageList messages={messages} />
      {loading && (
        <div className="px-4 pb-1">
          <span className="text-gray-500 text-xs">Analyzing...</span>
        </div>
      )}
      <InputBar onSend={sendMessage} disabled={loading} />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<ChatApp />)
```

- [ ] **Step 4: Add `open-chat` endpoint to sidecar so popup button works**

Add this route to `sidecar/main.py` (after the existing routes):

```python
@app.post("/open-chat")
def open_chat_signal():
    # Electron polls this — we just set a flag
    db.merge(__import__('database').AppState(key="open_chat", value="1"))
    db.commit()
    return {"ok": True}
```

And update `pollStatus` in `electron/main.ts` to also check for the open-chat signal:

```typescript
async function pollStatus() {
  try {
    const res = await fetch(`${SIDECAR_URL}/status`)
    if (!res.ok) return
    const data = await res.json() as { pending_popup: string | null }
    if (data.pending_popup) {
      showPopup(data.pending_popup)
      await fetch(`${SIDECAR_URL}/status/clear`, { method: 'POST' })
    }
  } catch {
    // Sidecar not ready yet
  }
}
```

Also add `/open-chat` handling to `/status` response — update the `/status` route in `sidecar/main.py`:

```python
@app.get("/status")
def status():
    pending = get_pending_popup(db)
    open_chat_row = db.query(AppState).filter(AppState.key == "open_chat").first()
    open_chat = open_chat_row is not None and open_chat_row.value == "1"
    if open_chat:
        db.query(AppState).filter(AppState.key == "open_chat").delete()
        db.commit()
    return {"pending_popup": pending, "open_chat": open_chat}
```

Update `pollStatus` in `electron/main.ts`:

```typescript
async function pollStatus() {
  try {
    const res = await fetch(`${SIDECAR_URL}/status`)
    if (!res.ok) return
    const data = await res.json() as { pending_popup: string | null; open_chat: boolean }
    if (data.pending_popup) {
      showPopup(data.pending_popup)
      await fetch(`${SIDECAR_URL}/status/clear`, { method: 'POST' })
    }
    if (data.open_chat) {
      createChatWindow()
    }
  } catch {
    // Sidecar not ready yet
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add src/chat/ sidecar/main.py electron/main.ts
git commit -m "feat: chat UI with message history, streaming input, and open-chat signal"
```

---

## Task 11: First-Run Setup Screen & Integration Test

**Files:**
- Create: `src/chat/Setup.tsx`
- Modify: `src/chat/App.tsx`

Before the chat works, the player needs to enter their summoner name and Riot ID so the sidecar can look up their PUUID. This screen appears once on first launch.

- [ ] **Step 1: Write `src/chat/Setup.tsx`**

```tsx
import { useState } from 'react'

interface SetupProps {
  port: string
  onComplete: () => void
}

export function Setup({ port, onComplete }: SetupProps) {
  const [gameName, setGameName] = useState('')
  const [tagLine, setTagLine] = useState('')
  const [region, setRegion] = useState('NA1')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    if (!gameName.trim() || !tagLine.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`http://localhost:${port}/setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ summoner_name: gameName.trim(), tag_line: tagLine.trim(), region }),
      })
      if (!res.ok) {
        const err = await res.json() as { detail: string }
        setError(err.detail || 'Setup failed.')
        return
      }
      onComplete()
    } catch {
      setError('Could not connect to sidecar.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-[#1a1a2e] h-screen flex flex-col items-center justify-center text-white font-sans px-8">
      <h1 className="text-xl font-bold mb-2">LoL Analyst Setup</h1>
      <p className="text-gray-400 text-sm mb-6 text-center">Enter your Riot ID to get started. This is a one-time setup.</p>

      <div className="w-full max-w-sm space-y-3">
        <div className="flex gap-2">
          <input
            className="flex-1 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="Game Name"
            value={gameName}
            onChange={e => setGameName(e.target.value)}
          />
          <span className="text-gray-500 self-center">#</span>
          <input
            className="w-20 bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none placeholder-gray-500"
            placeholder="TAG"
            value={tagLine}
            onChange={e => setTagLine(e.target.value)}
          />
        </div>

        <select
          className="w-full bg-white/10 text-white text-sm rounded-xl px-3 py-2 outline-none"
          value={region}
          onChange={e => setRegion(e.target.value)}
        >
          {['NA1','EUW1','EUNE1','KR','BR1','LAN','LAS','OC1','TR1','RU','JP1'].map(r => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>

        {error && <p className="text-red-400 text-xs">{error}</p>}

        <button
          onClick={submit}
          disabled={loading || !gameName.trim() || !tagLine.trim()}
          className="w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-sm rounded-xl transition-colors"
        >
          {loading ? 'Connecting...' : 'Get Started'}
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Update `src/chat/App.tsx` to show Setup on first launch**

Replace the `ChatApp` function with:

```tsx
import { useState, useEffect, useCallback } from 'react'
import { createRoot } from 'react-dom/client'
import { MessageList } from './MessageList'
import { InputBar } from './InputBar'
import { Setup } from './Setup'
import '../index.css'

declare global {
  interface Window { sidecar: { port: string } }
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

const SESSION_ID = `session-${Date.now()}`

function ChatApp() {
  const [isSetup, setIsSetup] = useState<boolean | null>(null)
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: "Hi! I'm your personal LoL analyst. Ask me anything about your games — patterns, mistakes, champion performance, or what to focus on to climb." }
  ])
  const [loading, setLoading] = useState(false)
  const [matchId] = useState<string | null>(
    new URLSearchParams(window.location.search).get('matchId')
  )

  const port = window.sidecar?.port ?? '8765'

  useEffect(() => {
    fetch(`http://localhost:${port}/matches?last_n=1`)
      .then(r => r.json())
      .then((data: unknown[]) => setIsSetup(data.length >= 0))
      .catch(() => setIsSetup(false))

    // Check if player profile exists
    fetch(`http://localhost:${port}/status`)
      .then(r => r.json())
      .then(async () => {
        const res = await fetch(`http://localhost:${port}/matches?last_n=1`)
        const matches = await res.json()
        // If we get a valid response, sidecar is up — check player profile
        setIsSetup(true)
      })
      .catch(() => setIsSetup(false))
  }, [port])

  // Check player profile specifically
  useEffect(() => {
    fetch(`http://localhost:${port}/matches?last_n=1`)
      .then(r => {
        if (r.status === 400) { setIsSetup(false); return }
        setIsSetup(true)
      })
      .catch(() => setIsSetup(null))
  }, [port])

  const sendMessage = useCallback(async (text: string) => {
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)
    try {
      const res = await fetch(`http://localhost:${port}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: SESSION_ID, message: text, match_id: matchId }),
      })
      const data = await res.json() as { response: string }
      setMessages(prev => [...prev, { role: 'assistant', content: data.response }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error connecting to analyst.' }])
    } finally {
      setLoading(false)
    }
  }, [port, matchId])

  if (isSetup === null) {
    return <div className="bg-[#1a1a2e] h-screen flex items-center justify-center"><p className="text-gray-500 text-sm">Starting...</p></div>
  }

  if (!isSetup) {
    return <Setup port={port} onComplete={() => setIsSetup(true)} />
  }

  return (
    <div className="bg-[#1a1a2e] h-screen flex flex-col text-white font-sans">
      <div className="border-b border-white/10 px-4 py-3 flex items-center justify-between">
        <h1 className="font-bold text-base">LoL Analyst</h1>
        {matchId && <span className="text-xs text-blue-400">Viewing specific game</span>}
      </div>
      <MessageList messages={messages} />
      {loading && <div className="px-4 pb-1"><span className="text-gray-500 text-xs">Analyzing...</span></div>}
      <InputBar onSend={sendMessage} disabled={loading} />
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<ChatApp />)
```

- [ ] **Step 3: End-to-end smoke test**

Start the sidecar manually:

```bash
cd sidecar && venv/Scripts/python -m uvicorn main:app --port 8765
```

In a second terminal, test each endpoint:

```bash
# Should return pending_popup: null
curl http://localhost:8765/status

# Should return empty list (no player set up yet)
curl http://localhost:8765/matches

# Setup should fail with bad key (expected)
curl -X POST http://localhost:8765/setup \
  -H "Content-Type: application/json" \
  -d '{"summoner_name":"Test","tag_line":"NA1","region":"NA1"}'
```

Expected: All endpoints respond (even if setup fails due to invalid key — that's expected without a real Riot key).

- [ ] **Step 4: Commit**

```bash
git add src/chat/Setup.tsx src/chat/App.tsx
git commit -m "feat: first-run setup screen and end-to-end smoke test"
```

---

## Task 12: Tailwind Config & Final Polish

**Files:**
- Modify: `tailwind.config.js`
- Create: `electron-builder.yml`

- [ ] **Step 1: Update `tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{tsx,ts,html}'],
  theme: {
    extend: {
      colors: {
        navy: '#1a1a2e',
      }
    }
  },
  plugins: [],
}
```

- [ ] **Step 2: Write `electron-builder.yml`**

```yaml
appId: com.lolanalyst.app
productName: LoL Analyst
directories:
  output: release
files:
  - dist/**/*
  - sidecar/**/*
  - "!sidecar/tests/**/*"
  - "!sidecar/__pycache__/**/*"
extraResources:
  - from: sidecar/
    to: sidecar/
win:
  target: nsis
  icon: assets/icon.ico
```

- [ ] **Step 3: Run the full test suite one final time**

```bash
cd sidecar && venv/Scripts/python -m pytest tests/ -v
```

Expected: All 20 tests pass across all modules.

- [ ] **Step 4: Final commit**

```bash
git add tailwind.config.js electron-builder.yml
git commit -m "chore: tailwind config and electron-builder packaging config"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered in task |
|---|---|
| Game end detection via localhost:2999 | Task 3 (riot_client), Task 7 (watcher) |
| Post-game popup with 3-5 pivotal moments | Task 4 (analyzer), Task 9 (popup UI) |
| Counterfactual "what if" per moment | Task 5 (counterfactual), Task 7 (pipeline) |
| Persistent chat with natural language queries | Task 6 (claude), Task 10 (chat UI) |
| Claude tool use to query SQLite | Task 6 |
| SQLite local storage | Task 2 |
| Popup auto-dismiss after 60s | Task 8 |
| "Ask about this game" button seeds chat with context | Task 9, Task 10 |
| System tray always running | Task 8 |
| `/status` polling every 5s | Task 8 |
| First-run setup for summoner name | Task 11 |
| Dark theme | All UI tasks |
| Single player account (v1 scope) | Task 2 schema, Task 11 setup |

All spec requirements covered.
