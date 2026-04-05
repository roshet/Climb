import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from claude_client import ClaudeClient
from counterfactual import enrich_moments
from database import (
    AppState,
    clear_pending_popup, get_chat_history, get_matches, get_pending_popup,
    get_pivotal_moments, get_player, init_db, save_chat_message, save_match,
    save_pivotal_moments, save_player, set_pending_popup,
)
from riot_client import RiotClient, REGIONAL_ROUTING
from timeline_analyzer import analyze_timeline

load_dotenv()

RIOT_API_KEY = os.environ["RIOT_API_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
REGION = os.environ.get("REGION", "NA1")

engine = init_db("analyst.db")
db = Session(engine)
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
            "played_at": datetime.fromtimestamp(info["gameStartTimestamp"] / 1000, tz=timezone.utc),
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
    db.close()


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- Routes ---

@app.get("/status")
def status():
    pending = get_pending_popup(db)
    open_chat_row = db.query(AppState).filter(AppState.key == "open_chat").first()
    open_chat_match_id: Optional[str] = None
    if open_chat_row is not None:
        open_chat_match_id = open_chat_row.value or None
        db.query(AppState).filter(AppState.key == "open_chat").delete()
        db.commit()
    return {"pending_popup": pending, "open_chat": open_chat_match_id}


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
    riot.regional = REGIONAL_ROUTING.get(req.region, "americas")
    try:
        puuid = await riot.get_puuid_by_summoner(req.summoner_name, req.tag_line)
        save_player(db, summoner_name=req.summoner_name, puuid=puuid, region=req.region)
        return {"ok": True, "puuid": puuid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class OpenChatRequest(BaseModel):
    match_id: Optional[str] = None


@app.post("/open-chat")
def open_chat_signal(req: OpenChatRequest):
    db.merge(AppState(key="open_chat", value=req.match_id or ""))
    db.commit()
    return {"ok": True}


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
