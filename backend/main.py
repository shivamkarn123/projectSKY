import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from agent import chat, reset_session
from tools import tool_get_data_quality_notes, tool_query_deals, tool_query_work_orders
from monday_client import MondayAPIError

app = FastAPI(title="Skylark Drones BI Agent")


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str


@app.on_event("startup")
def _startup():
    # In mock mode, configuration is optional; in real mode, fail fast with a clear message
    try:
        config.require_config()
        print(f"Backend running in {'MOCK' if config.MOCK_MODE else 'LIVE'} mode")
    except RuntimeError as e:
        if not config.MOCK_MODE:
            raise
        print("Backend running in MOCK mode (credentials not configured)")



@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest) -> ChatResponse:
    session_id = req.session_id or str(uuid.uuid4())
    reply = chat(session_id, req.message)
    return ChatResponse(session_id=session_id, reply=reply)


@app.post("/api/chat/reset")
def reset_endpoint(session_id: str):
    reset_session(session_id)
    return {"status": "reset"}


@app.get("/api/leadership-summary", response_model=ChatResponse)
def leadership_summary() -> ChatResponse:
    session_id = "leadership-summary-" + str(uuid.uuid4())
    reply = chat(
        session_id,
        "Give me a leadership summary covering pipeline health by stage, sector "
        "performance, work orders at risk, and billing/collection gaps.",
    )
    return ChatResponse(session_id=session_id, reply=reply)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/board-stats")
def board_stats():
    """Live connection status + data-completeness numbers for the sidebar gauges.
    Computed fresh from monday.com (via the same cached tool layer the agent uses) —
    never hardcoded, so the UI reflects the real state of the boards."""
    try:
        deals = tool_query_deals(limit=1)
        wos = tool_query_work_orders(limit=1)
        quality = tool_get_data_quality_notes("both")

        def completeness(board_key: str) -> dict:
            report = quality.get(board_key, {})
            if "error" in report or report.get("row_count", 0) == 0:
                return {"row_count": 0, "completeness_pct": 0, "connected": False}
            null_rates = report.get("notable_null_rates", {})
            avg_null = (
                sum(float(v.replace("% empty", "")) for v in null_rates.values()) / len(null_rates)
                if null_rates else 0
            )
            return {
                "row_count": report["row_count"],
                "completeness_pct": round(100 - avg_null, 1),
                "connected": True,
            }

        return {
            "connected": True,
            "deals": completeness("deals"),
            "work_orders": completeness("work_orders"),
        }
    except MondayAPIError as e:
        return {"connected": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"connected": False, "error": str(e)}


# Serve the chat UI at "/" (built after the API, so /api/* routes above take priority)
frontend_dir = str((Path(__file__).resolve().parent.parent / "frontend").resolve())
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
