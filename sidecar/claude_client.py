from sqlalchemy.orm import Session
from google import genai
from google.genai import types
from database import get_matches, get_pivotal_moments

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


class ClaudeClient:
    def __init__(self, api_key: str, db: Session):
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-1.5-flash"
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
