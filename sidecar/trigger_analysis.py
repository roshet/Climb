import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from database import init_db, get_player, Session, set_pending_popup, save_match, save_pivotal_moments
from riot_client import RiotClient
from timeline_analyzer import analyze_timeline, TEAM_100_IDS
from counterfactual import enrich_moments
from datetime import datetime, timezone

SMITE_ID = 11

async def main():
    engine = init_db('analyst.db')
    db = Session(engine)
    player = get_player(db)
    riot = RiotClient(api_key=os.environ['RIOT_API_KEY'], region=os.environ.get('REGION', 'NA1'))

    match_id = 'NA1_5531314507'
    print(f'Fetching match {match_id}...')
    match_data = await riot.get_match(match_id)
    timeline_data = await riot.get_timeline(match_id)

    info = match_data['info']
    participants = info['participants']
    participant = next(p for p in participants if p['puuid'] == player.riot_puuid)
    participant_index = participants.index(participant) + 1

    player_team_ids = TEAM_100_IDS if participant_index in TEAM_100_IDS else set(range(6, 11))
    enemy_participants = [p for p in participants if participants.index(p) + 1 not in player_team_ids]
    enemy_jungler = next(
        (p for p in enemy_participants if p.get("summoner1Id") == SMITE_ID or p.get("summoner2Id") == SMITE_ID),
        None,
    )
    enemy_jungler_id = participants.index(enemy_jungler) + 1 if enemy_jungler else None
    print(f'Enemy jungler participant ID: {enemy_jungler_id}')

    save_match(db, {
        'match_id': match_id,
        'played_at': datetime.fromtimestamp(info['gameStartTimestamp'] / 1000, tz=timezone.utc),
        'champion': participant['championName'],
        'role': participant.get('teamPosition', 'UNKNOWN'),
        'result': 'win' if participant['win'] else 'loss',
        'duration_secs': info['gameDuration'],
        'kda': f"{participant['kills']}/{participant['deaths']}/{participant['assists']}",
        'cs': participant['totalMinionsKilled'],
        'gold_earned': participant['goldEarned'],
        'vision_score': participant['visionScore'],
        'raw_timeline': timeline_data,
    })

    moments = analyze_timeline(timeline_data, participant_id=participant_index, enemy_jungler_id=enemy_jungler_id)
    enriched = enrich_moments(moments)
    save_pivotal_moments(db, match_id, [
        {'timestamp_secs': m.timestamp_secs, 'moment_type': m.moment_type,
         'description': m.description, 'counterfactual': m.counterfactual,
         'gold_impact': m.gold_impact}
        for m in enriched
    ])
    set_pending_popup(db, match_id=match_id)

    print(f'Champion: {participant["championName"]}, Result: {"win" if participant["win"] else "loss"}')
    print(f'Moments found: {len(enriched)}')
    for m in enriched:
        print(f'  [{m.moment_type}] {m.description}')
    await riot.close()

asyncio.run(main())
