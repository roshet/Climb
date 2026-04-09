import json
from sqlalchemy.orm import Session
from google import genai
from google.genai import types
from database import get_matches, get_pivotal_moments
from timeline_analyzer import TEAM_100_IDS, TEAM_200_IDS

TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_matches",
        description="Query the player's match history. Returns matches filtered by champion, result, and/or recency.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "champion": types.Schema(type=types.Type.STRING, description="Filter by champion name, e.g. 'Jinx'"),
                "result":   types.Schema(type=types.Type.STRING, description="Filter by game result: 'win' or 'loss'"),
                "last_n":   types.Schema(type=types.Type.INTEGER, description="Number of most recent matches to return (default 20)"),
            }
        )
    ),
    types.FunctionDeclaration(
        name="get_pivotal_moments",
        description="Get the pivotal moments and counterfactuals for specific match IDs.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "match_ids": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(type=types.Type.STRING),
                    description="List of match IDs",
                )
            },
            required=["match_ids"]
        )
    ),
    types.FunctionDeclaration(
        name="get_champion_stats",
        description="Get aggregated stats for a specific champion over the player's recent games.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "champion": types.Schema(type=types.Type.STRING, description="Champion name"),
                "last_n":   types.Schema(type=types.Type.INTEGER, description="Number of recent games to include (default 20)"),
            },
            required=["champion"]
        )
    ),
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
        lines.append(f"- {m.match_id}: {m.champion} {m.result} | KDA {m.kda} | CS {m.cs} | Gold {m.gold_earned} | Vision {m.vision_score} | {m.played_at.isoformat()}")
    return "\n".join(lines)


def _format_moments(moments) -> str:
    if not moments:
        return "No pivotal moments found."
    lines = []
    for m in moments:
        mins, secs = divmod(m.timestamp_secs, 60)
        lines.append(f"- [{m.match_id}] {mins}:{secs:02d} {m.moment_type}: {m.description} | Counterfactual: {m.counterfactual} | Impact: ~{m.gold_impact}g")
    return "\n".join(lines)


def _summarize_event(event: dict, participant_id: int) -> str | None:
    """Convert a raw timeline event to a one-line readable summary."""
    ts = event.get("timestamp", 0) // 1000
    mins, secs = divmod(ts, 60)
    t = f"{mins}:{secs:02d}"
    event_type = event.get("type", "")
    player_team = TEAM_100_IDS if participant_id in TEAM_100_IDS else TEAM_200_IDS

    if event_type == "CHAMPION_KILL":
        killer = event.get("killerId", 0)
        victim = event.get("victimId", 0)
        assisters = event.get("assistingParticipantIds", [])
        if victim == participant_id:
            assist_str = f" (assists: {assisters})" if assisters else ""
            return f"{t} — You were killed by participant {killer}{assist_str}"
        elif killer == participant_id:
            return f"{t} — You killed participant {victim}"
        elif participant_id in assisters:
            return f"{t} — You assisted killing participant {victim}"
        else:
            return f"{t} — Fight: participant {killer} killed participant {victim}"

    elif event_type == "ELITE_MONSTER_KILL":
        monster = event.get("monsterType", "UNKNOWN")
        killer = event.get("killerId", 0)
        team = "your team" if killer in player_team else "enemy team"
        return f"{t} — {team} secured {monster}"

    elif event_type == "BUILDING_KILL":
        lane = event.get("laneType", "UNKNOWN").replace("_LANE", "")
        tower = event.get("towerType", "TURRET").replace("_TURRET", "").lower()
        team_id = event.get("teamId", 0)
        player_team_id = 100 if participant_id in TEAM_100_IDS else 200
        loser = "your team" if team_id == player_team_id else "enemy team"
        return f"{t} — {lane} {tower} tower lost by {loser}"

    return None


def _build_context_window(
    all_events: list[dict],
    moment_ts_secs: int,
    participant_id: int,
    window_secs: int = 90,
) -> str:
    """Return readable summary of all events within window_secs of moment_ts_secs."""
    lines = []
    for event in all_events:
        ts = event.get("timestamp", 0) // 1000
        if abs(ts - moment_ts_secs) <= window_secs:
            summary = _summarize_event(event, participant_id)
            if summary:
                lines.append(summary)
    return "\n".join(lines) if lines else "No notable events in this window."


class ClaudeClient:
    def __init__(self, api_key: str, db: Session):
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.5-flash"
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

        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=TOOL_DECLARATIONS)],
        )

        # Convert stored messages to Gemini history format (all but the last)
        # Gemini uses "model" instead of "assistant"
        history = []
        for msg in messages[:-1]:
            role = "model" if msg["role"] == "assistant" else "user"
            history.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        chat_session = self.client.chats.create(
            model=self.model_name,
            config=config,
            history=history,
        )
        response = chat_session.send_message(messages[-1]["content"])

        # Tool use loop — keep going until no function calls remain
        while True:
            function_calls = [
                part for part in response.candidates[0].content.parts
                if part.function_call is not None
            ]
            if not function_calls:
                break

            tool_response_parts = []
            for part in function_calls:
                fn = part.function_call
                result = self._handle_tool(fn.name, dict(fn.args))
                tool_response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fn.name,
                            response={"result": result},
                        )
                    )
                )
            response = chat_session.send_message(tool_response_parts)

        return response.text

    def generate_coaching_notes(
        self,
        moments: list,
        game_context: dict,
        timeline: dict,
    ) -> list:
        """
        Generate AI coaching notes for all moments in a single Gemini call.
        Falls back to counterfactual.enrich_moments on failure.
        Mutates and returns the moments list with counterfactual filled in.
        """
        from counterfactual import enrich_moments as fallback_enrich

        if not moments:
            return moments

        participant_id = game_context.get("participant_id", 1)

        # Collect all events from timeline for context window lookups
        all_events: list[dict] = []
        for frame in timeline.get("info", {}).get("frames", []):
            all_events.extend(frame.get("events", []))

        # Build game context header
        champion = game_context.get("champion", "Unknown")
        role = game_context.get("role", "JUNGLE")
        side = game_context.get("side", "blue")
        result = game_context.get("result", "unknown")
        kda = game_context.get("kda", "0/0/0")
        duration_secs = game_context.get("duration_secs", 0)
        dur_mins, dur_secs_r = divmod(duration_secs, 60)
        header = (
            f"Champion: {champion} | Role: {role} | Side: {side} side\n"
            f"Result: {result.upper()} | KDA: {kda} | Duration: {dur_mins}:{dur_secs_r:02d}"
        )

        # Build one block per moment
        moment_blocks = []
        for i, m in enumerate(moments):
            ctx = _build_context_window(all_events, m.timestamp_secs, participant_id)
            moment_blocks.append(
                f"[{i}] {m.moment_type} — {m.description}\n"
                f"Context (±90s):\n{ctx}"
            )

        moments_text = "\n---\n".join(moment_blocks)

        prompt = (
            f"You are coaching a {champion} {role.lower()}. {header}\n\n"
            f"For each moment below, write a 3-4 sentence coaching note. Rules:\n"
            f"- Be specific to the {role.lower()} role\n"
            f"- Reference what was happening in the surrounding context\n"
            f"- Give one concrete, achievable alternative action\n"
            f"- Use encouraging language for positive moments "
            f"(gank_assist, baron_secured, dragon_stack, solo_kill, objective_secured)\n"
            f"- Describe game state for mistakes — don't moralize\n"
            f"- Keep each note to 3-4 sentences maximum\n\n"
            f"{moments_text}\n\n"
            f"Return ONLY valid JSON, no other text: "
            f'[{{"id": 0, "coaching": "..."}}, ...]'
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            raw = response.text.strip()
            # Strip markdown code fences if Gemini wraps with ```json ... ```
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            coaching_list = json.loads(raw)
            coaching_map = {item["id"]: item["coaching"] for item in coaching_list}
            for i, m in enumerate(moments):
                if i in coaching_map:
                    m.counterfactual = coaching_map[i]
        except Exception as e:
            print(f"[coaching] Gemini call failed ({e}). Using static fallback.")
            fallback_enrich(moments)

        return moments
