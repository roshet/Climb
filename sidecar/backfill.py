import asyncio
from datetime import datetime, timezone

import httpx

from database import (
    get_all_match_ids, save_match, save_pivotal_moments,
)
from pattern_detector import detect_patterns
from timeline_analyzer import analyze_timeline, TEAM_100_IDS, TEAM_200_IDS

BACKFILL_DAYS = 30
SMITE_ID = 11


async def analyze_and_save_match(
    riot_client,
    db_session,
    claude_client,
    player,
    match_id: str,
) -> None:
    match_data = await riot_client.get_match(match_id)
    timeline_data = await riot_client.get_timeline(match_id)

    info = match_data["info"]
    participants = info["participants"]
    participant = next(p for p in participants if p["puuid"] == player.riot_puuid)
    participant_index = participants.index(participant) + 1
    role = participant.get("teamPosition", "UNKNOWN")
    champion = participant["championName"]

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
         and p.get("teamPosition") == role),
        None,
    )
    lane_opponent_id = lane_opponent_entry[0] if lane_opponent_entry else None
    lane_opponent_champion = lane_opponent_entry[1]["championName"] if lane_opponent_entry else None

    save_match(db_session, {
        "match_id": match_id,
        "played_at": datetime.fromtimestamp(info["gameStartTimestamp"] / 1000, tz=timezone.utc),
        "champion": champion,
        "role": role,
        "result": "win" if participant["win"] else "loss",
        "duration_secs": info["gameDuration"],
        "kda": f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
        "cs": participant["totalMinionsKilled"],
        "gold_earned": participant["goldEarned"],
        "vision_score": participant["visionScore"],
        "raw_timeline": timeline_data,
        "lane_opponent_champion": lane_opponent_champion,
    })

    moments = analyze_timeline(
        timeline_data,
        participant_id=participant_index,
        enemy_jungler_id=enemy_jungler_id,
        role=role,
        champion=champion,
        lane_opponent_id=lane_opponent_id,
    )
    side = "blue" if participant_index in TEAM_100_IDS else "red"
    game_context = {
        "participant_id": participant_index,
        "champion": champion,
        "role": role,
        "side": side,
        "result": "win" if participant["win"] else "loss",
        "kda": f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
        "duration_secs": info["gameDuration"],
    }
    try:
        game_patterns = detect_patterns(db_session)
    except Exception as e:
        print(f"[backfill] detect_patterns failed ({e}); skipping pattern context")
        game_patterns = None
    enriched = claude_client.generate_coaching_notes(moments, game_context, timeline_data, patterns=game_patterns)
    save_pivotal_moments(db_session, match_id, [
        {
            "timestamp_secs": m.timestamp_secs,
            "moment_type": m.moment_type,
            "description": m.description,
            "counterfactual": m.counterfactual,
            "gold_impact": m.gold_impact,
        }
        for m in enriched
    ])


async def _backfill_opponent_champions(riot_client, db_session, player) -> None:
    from database import Match
    null_rows = (
        db_session.query(Match)
        .filter(Match.lane_opponent_champion.is_(None))
        .limit(20)
        .all()
    )
    if not null_rows:
        return
    print(f"[backfill] Filling opponent champion for {len(null_rows)} existing matches")
    for match in null_rows:
        try:
            match_data = await riot_client.get_match(match.match_id)
            info = match_data["info"]
            participants = info["participants"]
            participant = next(
                (p for p in participants if p["puuid"] == player.riot_puuid), None
            )
            if not participant:
                continue
            participant_index = participants.index(participant) + 1
            player_team_ids = TEAM_100_IDS if participant_index in TEAM_100_IDS else TEAM_200_IDS
            role = participant.get("teamPosition", "UNKNOWN")
            lane_opponent_entry = next(
                ((i + 1, p) for i, p in enumerate(participants)
                 if (i + 1) not in player_team_ids
                 and p.get("teamPosition") == role),
                None,
            )
            if lane_opponent_entry:
                match.lane_opponent_champion = lane_opponent_entry[1]["championName"]
                db_session.commit()
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[backfill] Could not update opponent for {match.match_id}: {e}")


async def run_backfill(riot_client, db_session, claude_client, player) -> None:
    start_time = int(datetime.now(timezone.utc).timestamp() - BACKFILL_DAYS * 24 * 3600)
    match_ids = await riot_client.get_recent_match_ids(
        player.riot_puuid, count=20, start_time=start_time
    )
    existing_ids = get_all_match_ids(db_session)
    new_ids = [mid for mid in match_ids if mid not in existing_ids]
    print(f"[backfill] {len(new_ids)} new matches to analyze")

    for match_id in new_ids:
        try:
            await analyze_and_save_match(riot_client, db_session, claude_client, player, match_id)
            await asyncio.sleep(3)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                print(f"[backfill] Rate limited — waiting 10s before retrying {match_id}")
                await asyncio.sleep(10)
                try:
                    await analyze_and_save_match(riot_client, db_session, claude_client, player, match_id)
                    await asyncio.sleep(3)
                except Exception as retry_err:
                    print(f"[backfill] Retry failed for {match_id}: {retry_err}")
            else:
                print(f"[backfill] HTTP error for {match_id}: {e}")
        except Exception as e:
            print(f"[backfill] Error processing {match_id}: {e}")

    await _backfill_opponent_champions(riot_client, db_session, player)
    print(f"[backfill] Complete")
