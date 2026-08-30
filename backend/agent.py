"""
The agent: a Claude tool-use loop with per-session conversation memory.
Sessions are stored in-memory (fine for a single-process demo deployment).
"""

import json
import anthropic

import config
from tools import TOOLS, TOOL_FUNCTIONS

SYSTEM_PROMPT = """You are Skylark Drones' internal Business Intelligence assistant. You answer \
founder- and leadership-level questions by querying two live monday.com boards: "Deals" (sales \
pipeline) and "Work Orders" (project execution + billing). You never see the raw spreadsheets — \
you only know what your tools return, fetched live from monday.com on this turn.

Rules you always follow:
1. Never fabricate a number, deal, or status. Only state what a tool call returned.
2. This data is real-world messy: many fields have high null rates, some rows have data-entry \
artifacts, and the two boards join only approximately (on deal codename, not a hard ID). When a \
notable share of relevant rows are missing a field you're aggregating or joining on, say so \
plainly and explain how it affects your answer (e.g. "62 of 91 matching deals have no logged \
value, so this total is a floor, not the true figure").
3. If a question is genuinely ambiguous (e.g. "this quarter" with no stated fiscal year anchor, \
or a deal-name match that has multiple candidates), either ask one short clarifying question or \
state the reasonable assumption you're making and proceed — don't block on trivial ambiguity.
4. All monetary figures in this dataset are explicitly masked/scaled for this exercise, not real \
INR figures — don't imply otherwise if asked.
5. Lead with the headline number or insight, then supporting detail, then caveats. Keep answers \
tight and skimmable — this is for busy founders, not a report.
6. Use get_board_schema if you're not sure a column exists before filtering on it, rather than \
guessing and getting an empty result.
7. For a "leadership summary" / "weekly update" style request, pull pipeline-by-stage, \
sector performance, work orders at risk (overdue billing / stuck execution), and billing/\
collection gaps, then compose a short structured summary: one headline, 3-5 bullets, and a \
caveats line if data quality materially affects any number.
"""

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# session_id -> list of message dicts (Anthropic format)
_sessions: dict[str, list[dict]] = {}


def _run_tool(name: str, tool_input: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool {name}"})
    try:
        result = fn(**tool_input)
    except Exception as e:  # noqa: BLE001 - surface any tool failure to the agent, not a 500
        result = {"error": f"Tool '{name}' failed: {e}"}
    return json.dumps(result, default=str)


def chat(session_id: str, user_message: str, max_tool_rounds: int = 6) -> str:
    history = _sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": user_message})

    for _ in range(max_tool_rounds):
        try:
            response = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=history,
            )
        except anthropic.AuthenticationError as e:
            # In mock mode, return a helpful response instead of failing
            if config.MOCK_MODE:
                return f"Demo Mode: The system is using mock data for demonstration. Your question was: '{user_message}'. In production, this would query live monday.com data using Claude AI. Mock data includes 346 deals and 177 work orders. Try asking 'How many deals do we have?' or 'Show me pipeline by status'."
            else:
                # In real mode, propagate the error
                raise

        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # final text answer
            text_parts = [b.text for b in response.content if b.type == "text"]
            final_text = "\n".join(text_parts).strip()
            return final_text or "(no response generated)"

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result_str = _run_tool(block.name, block.input or {})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

        history.append({"role": "user", "content": tool_results})

    return "I had to stop after several tool calls without reaching a final answer — try narrowing the question."


def reset_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
