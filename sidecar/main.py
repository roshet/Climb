import asyncio
import json
import os
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backfill import analyze_and_save_match, run_backfill, SMITE_ID
from pattern_detector import detect_patterns
from claude_client import ClaudeClient
from database import (
    AppState,
    PivotalMoment,
    clear_pending_popup, delete_pivotal_moments, get_chat_history, get_matches,
    get_pending_popup, get_pivotal_moments, get_player, init_db, save_chat_message,
    save_pivotal_moments, save_player, set_pending_popup,
)
from timeline_analyzer import analyze_timeline, TEAM_100_IDS, TEAM_200_IDS
from riot_client import RiotClient, REGIONAL_ROUTING
from live_game_monitor import LiveGameMonitor
from champ_select_monitor import ChampSelectMonitor, MOMENT_LABELS, POSITIVE_TYPES
from improvement_tracker import get_improvement_data
from lcu_client import LcuClient

load_dotenv()

RIOT_API_KEY = os.environ["RIOT_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
REGION = os.environ.get("REGION", "NA1")

engine = init_db(os.environ.get("DB_PATH", "analyst.db"))
db = Session(engine)
riot = RiotClient(api_key=RIOT_API_KEY, region=REGION)
claude = ClaudeClient(api_key=GEMINI_API_KEY, db=db)
live_monitor = LiveGameMonitor(db)
lcu = LcuClient()
champ_select_monitor = ChampSelectMonitor(db, lcu)

_watcher_task: Optional[asyncio.Task] = None
_backfill_running = False


async def _generate_and_store_focus_card() -> None:
    try:
        patterns = detect_patterns(db)
        top_issue = next((p for p in patterns if p.label == "recurring_issue"), None)
        if not top_issue:
            return
        player = get_player(db)
        if not player:
            return
        focus = claude.generate_focus_card(top_issue, player.summoner_name)
        focus["moment_type"] = top_issue.moment_type
        db.merge(AppState(key="focus_card", value=json.dumps(focus)))
        db.commit()
    except Exception as e:
        print(f"[focus_card] Failed to generate: {e}")


async def backfill_history() -> None:
    global _backfill_running
    if _backfill_running:
        return
    _backfill_running = True
    try:
        player = get_player(db)
        if not player:
            return
        await run_backfill(riot, db, claude, player)
        await _generate_and_store_focus_card()
    finally:
        _backfill_running = False


async def game_end_watcher():
    """Poll Live Client API. When in-game state drops, trigger analysis."""
    was_in_game = False
    while True:
        try:
            in_game = await riot.is_in_game()
            if in_game != was_in_game:
                print(f"[watcher] in_game state changed: {was_in_game} -> {in_game}")
            if was_in_game and not in_game:
                print("[watcher] Game ended, running analysis...")
                await run_post_game_analysis()
            was_in_game = in_game
        except Exception as e:
            print(f"[watcher] Unexpected error: {e}")
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
        await analyze_and_save_match(riot, db, claude, player, match_id)
        set_pending_popup(db, match_id=match_id)
        await _generate_and_store_focus_card()
    except Exception as e:
        print(f"[watcher] Error during post-game analysis: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _watcher_task
    _watcher_task = asyncio.create_task(game_end_watcher())
    asyncio.create_task(backfill_history())
    live_monitor.start()
    champ_select_monitor.start()
    yield
    if _watcher_task:
        _watcher_task.cancel()
    monitor_task = live_monitor._task
    live_monitor.stop()
    if monitor_task:
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    cs_task = champ_select_monitor._task
    champ_select_monitor.stop()
    if cs_task:
        try:
            await cs_task
        except asyncio.CancelledError:
            pass
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
    return {"pending_popup": pending, "open_chat": open_chat_match_id, "backfill_running": _backfill_running}


@app.post("/status/clear")
def clear_status():
    clear_pending_popup(db)
    return {"ok": True}


@app.get("/patterns")
def get_patterns():
    patterns = detect_patterns(db)
    return {
        "patterns": [
            {
                "moment_type": p.moment_type,
                "label": p.label,
                "games_seen": p.games_seen,
                "total_games": p.total_games,
                "win_rate_with": round(p.win_rate_with, 3),
                "overall_win_rate": round(p.overall_win_rate, 3),
                "summary": p.summary,
            }
            for p in patterns
        ]
    }


@app.get("/live")
def get_live():
    return live_monitor.get_state()


@app.get("/champ-select")
def get_champ_select():
    return champ_select_monitor.get_state()


@app.get("/improvement/{match_id}")
def get_improvement(match_id: str):
    data = get_improvement_data(db, match_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return data


def _compute_streak_clean(
    recent_ids: list[str],
    moments_by_match: dict[str, set],
    moment_type: str,
) -> int:
    streak = 0
    for mid in recent_ids:
        if moment_type not in moments_by_match.get(mid, set()):
            streak += 1
        else:
            break
    return streak


def _compute_focus_history(
    recent_ids: list[str],
    moments_by_match: dict[str, set],
    moment_type: str,
    n: int = 10,
) -> list[bool]:
    history_ids = list(reversed(recent_ids[:n]))
    return [
        moment_type not in moments_by_match.get(mid, set())
        for mid in history_ids
    ]


def _compute_focus_trend(history: list[bool]) -> Optional[str]:
    if len(history) < 6:
        return None
    mid = len(history) // 2
    first_half = sum(history[:mid])
    second_half = sum(history[mid:])
    if second_half > first_half:
        return "improving"
    if second_half < first_half:
        return "regressing"
    return None


def _get_matchup_stats(
    db: Session,
    matches: list,
    min_games: int = 3,
    top_n: int = 5,
) -> list[dict]:
    with_opponent = [m for m in matches if m.lane_opponent_champion]
    by_opponent: dict[str, list] = {}
    for m in with_opponent:
        by_opponent.setdefault(m.lane_opponent_champion, []).append(m)

    results = []
    for opponent, opp_matches in by_opponent.items():
        if len(opp_matches) < min_games:
            continue
        wins = sum(1 for m in opp_matches if m.result == "win")
        losses = len(opp_matches) - wins
        win_rate = round(wins / len(opp_matches), 3)

        loss_ids = [m.match_id for m in opp_matches if m.result == "loss"]
        dominant_moment = None
        if loss_ids:
            moments = db.query(PivotalMoment).filter(
                PivotalMoment.match_id.in_(loss_ids)
            ).all()
            if moments:
                counts = Counter(m.moment_type for m in moments)
                dominant_moment = min(counts, key=lambda t: (-counts[t], t))

        results.append({
            "opponent": opponent,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "dominant_moment": dominant_moment,
        })

    results.sort(key=lambda r: (r["win_rate"], r["opponent"]))
    return results[:top_n]


@app.get("/focus")
def get_focus():
    row = db.query(AppState).filter(AppState.key == "focus_card").first()
    if not row or not row.value:
        return None
    stored = json.loads(row.value)
    patterns = detect_patterns(db)
    top_issue = next((p for p in patterns if p.label == "recurring_issue"), None)
    if not top_issue:
        return None
    if stored.get("moment_type") != top_issue.moment_type:
        return None
    recent_matches = get_matches(db, last_n=20)
    recent_ids = [m.match_id for m in recent_matches]
    recent_moments = get_pivotal_moments(db, recent_ids)
    moments_by_match: dict[str, set] = {}
    for m in recent_moments:
        moments_by_match.setdefault(m.match_id, set()).add(m.moment_type)
    streak_clean = _compute_streak_clean(recent_ids, moments_by_match, top_issue.moment_type)
    display = MOMENT_LABELS.get(
        top_issue.moment_type,
        top_issue.moment_type.replace("_", " ").title(),
    )
    history = _compute_focus_history(recent_ids, moments_by_match, top_issue.moment_type)
    trend = _compute_focus_trend(history)
    return {
        "moment_type": top_issue.moment_type,
        "display": display,
        "coaching_sentence": stored.get("coaching_sentence", ""),
        "cta_message": stored.get("cta_message", ""),
        "win_rate": round(top_issue.win_rate_with, 3),
        "games_seen": top_issue.games_seen,
        "total_games": top_issue.total_games,
        "streak_clean": streak_clean,
        "history": history,
        "trend": trend,
    }


@app.get("/player")
def get_player_profile():
    player = get_player(db)
    if not player:
        raise HTTPException(status_code=404, detail="No player profile")
    return {"summoner_name": player.summoner_name, "region": player.region}


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
        "role": match.role,
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

    try:
        patterns = detect_patterns(db)
        if patterns:
            issues = [p for p in patterns if p.label == "recurring_issue"]
            wins = [p for p in patterns if p.label == "win_condition"]
            lines: list[str] = []
            if issues:
                lines.append("Recurring issues (last 20 games):")
                lines.extend(
                    f"- {p.moment_type}: {p.games_seen}/{p.total_games} games, "
                    f"{int(p.win_rate_with * 100)}% win rate (overall {int(p.overall_win_rate * 100)}%)"
                    for p in issues
                )
            if wins:
                lines.append("Win conditions:")
                lines.extend(
                    f"- {p.moment_type}: {p.games_seen}/{p.total_games} games, "
                    f"{int(p.win_rate_with * 100)}% win rate"
                    for p in wins
                )
            pattern_context = "\n".join(lines)
            match_context = (match_context + "\n\n" + pattern_context) if match_context else pattern_context
    except Exception:
        pass  # pattern injection is best-effort; chat works without it

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
        asyncio.create_task(backfill_history())
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


@app.post("/admin/reanalyze-all")
async def reanalyze_all():
    player = get_player(db)
    if not player:
        raise HTTPException(status_code=400, detail="No player profile")
    matches = get_matches(db, last_n=100)
    reanalyzed = 0
    errors = []
    for match in matches:
        try:
            match_data = await riot.get_match(match.match_id)
            info = match_data["info"]
            participants = info["participants"]
            participant = next(p for p in participants if p["puuid"] == player.riot_puuid)
            participant_index = participants.index(participant) + 1
            player_team_ids = TEAM_100_IDS if participant_index in TEAM_100_IDS else TEAM_200_IDS
            enemy_jungler_entry = next(
                ((i + 1, p) for i, p in enumerate(participants)
                 if (i + 1) not in player_team_ids
                 and (p.get("summoner1Id") == SMITE_ID or p.get("summoner2Id") == SMITE_ID)),
                None,
            )
            enemy_jungler_id = enemy_jungler_entry[0] if enemy_jungler_entry else None
            lane_opponent_entry = next(
                ((i + 1, p) for i, p in enumerate(participants)
                 if (i + 1) not in player_team_ids
                 and p.get("teamPosition") == match.role),
                None,
            )
            lane_opponent_id = lane_opponent_entry[0] if lane_opponent_entry else None
            moments = analyze_timeline(
                match.raw_timeline,
                participant_id=participant_index,
                enemy_jungler_id=enemy_jungler_id,
                role=match.role,
                champion=match.champion,
                lane_opponent_id=lane_opponent_id,
            )
            delete_pivotal_moments(db, match.match_id)
            save_pivotal_moments(db, match.match_id, [
                {
                    "timestamp_secs": m.timestamp_secs,
                    "moment_type": m.moment_type,
                    "description": m.description,
                    "counterfactual": m.counterfactual,
                    "gold_impact": m.gold_impact,
                }
                for m in moments
            ])
            reanalyzed += 1
        except Exception as e:
            print(f"[reanalyze] Error for {match.match_id}: {e}")
            errors.append({"match_id": match.match_id, "error": str(e)})
    return {"ok": True, "reanalyzed": reanalyzed, "errors": errors}


@app.get("/matches")
def list_matches(champion: Optional[str] = None, result: Optional[str] = None, last_n: int = 20):
    matches = get_matches(db, champion=champion, result=result, last_n=last_n)
    match_ids = [m.match_id for m in matches]
    all_moments = get_pivotal_moments(db, match_ids) if match_ids else []
    moment_counts: dict[str, int] = {}
    gold_by_match: dict[str, int] = {}
    for moment in all_moments:
        moment_counts[moment.match_id] = moment_counts.get(moment.match_id, 0) + 1
        if moment.moment_type not in POSITIVE_TYPES:
            gold_by_match[moment.match_id] = gold_by_match.get(moment.match_id, 0) + abs(moment.gold_impact)
    return [
        {
            "match_id": m.match_id,
            "champion": m.champion,
            "role": m.role,
            "result": m.result,
            "kda": m.kda,
            "cs": m.cs,
            "duration_secs": m.duration_secs,
            "played_at": m.played_at.isoformat(),
            "moment_count": moment_counts.get(m.match_id, 0),
            "gold_lost": gold_by_match.get(m.match_id, 0),
        }
        for m in matches
    ]
