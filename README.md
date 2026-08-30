# Skylark Drones — Monday.com Business Intelligence Agent

A conversational agent that answers founder-level business questions by querying two live
monday.com boards (Deals pipeline + Work Orders execution/billing), handling real-world messy
data along the way. See `MASTER_PROMPT.md` for the full problem/architecture spec this was built
from, and `DECISION_LOG.md` for assumptions and trade-offs.

## Architecture

```
frontend/index.html  --fetch-->  FastAPI (backend/main.py)
                                     |
                                     v
                              agent.py (Claude tool-use loop)
                                     |
                                     v
                              tools.py (typed tool functions)
                                     |
                                     v
                        normalization.py (cleans raw rows)
                                     |
                                     v
                      monday_client.py (GraphQL, read-only)
                                     |
                                     v
                              monday.com API v2
```

- **Backend**: Python 3.11 + FastAPI. Single process serves both the `/api/chat` endpoint and
  the static chat UI.
- **Agent**: Anthropic Claude with tool use. Given 6 tools (schema lookup, query each board,
  cross-board join, data-quality report, cache refresh) and left to plan multi-step queries
  itself rather than a fixed NL→SQL translator.
- **Data**: never hardcoded. Every session pulls board data from monday.com's GraphQL API
  (cached in-memory for `CACHE_TTL_SECONDS` to keep responses snappy), normalizes it, then
  answers from that.

## Setup

### 1. monday.com boards
1. Create a board called **Deals** and import `Deal_funnel_Data.xlsx` via
   Board → `...` → Import data.
2. Create a board called **Work Orders** and import `Work_Order_Tracker_Data.xlsx` the same way.
3. Set column types: Status/Dropdown for status-like columns, Date for dates, Numbers for
   money/quantity fields.
4. Copy each board's ID from its URL: `monday.com/boards/<BOARD_ID>`.
5. Generate a personal API token (Profile → Developers → My Access Tokens).

### 2. Environment
```bash
cp .env.example backend/.env
# fill in MONDAY_API_TOKEN, MONDAY_DEALS_BOARD_ID, MONDAY_WORK_ORDERS_BOARD_ID, ANTHROPIC_API_KEY
```

### 3. Run locally
```bash
cd backend
python -m venv venv && source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python import_csv_to_monday.py   # optional: sanity-check the import worked
uvicorn main:app --reload --port 8000
```
Open http://localhost:8000

### 4. Deploy (Render.com example)
- New Web Service → connect this repo.
- Root directory: `backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Add the same env vars from `.env` in Render's dashboard.
- Render serves `frontend/` automatically since `main.py` mounts it as static files relative
  to `backend/`.

## API

- `POST /api/chat` `{ "session_id": "<optional>", "message": "..." }` → `{ session_id, reply }`
- `POST /api/chat/reset?session_id=...` → clears that session's conversation memory
- `GET /api/leadership-summary` → runs a fixed BI battery and returns a composed summary
- `GET /api/health` → liveness check

## Known limitations (see DECISION_LOG.md for the full list)

- Cross-board join is on deal codename, not a hard foreign key — approximate by design.
- Single shared API token / no multi-user auth (out of scope per assignment: read-only, no
  write access needed).
- In-memory session + cache state — fine for a demo, would move to Redis for multi-instance
  production use.
