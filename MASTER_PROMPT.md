# MASTER PROMPT — Skylark Drones: Monday.com Business Intelligence Agent

Paste this entire document as the first message to Claude Code (or any coding agent) in VS Code.
It is self-contained: problem, data, architecture, tech stack, and build order are all specified.

---

## 1. WHO YOU ARE BUILDING THIS FOR

I'm completing a 6-hour take-home assignment for Skylark Drones (Full-stack Assignment — RVU track).
Grading criteria emphasize: correctness on messy real data, clean architecture, sensible ambiguity
handling (documented, not asked about), a working hosted demo, and a 2-page decision log. Build for
these criteria, not for maximal feature count.

## 2. PROBLEM STATEMENT (verbatim intent, condensed)

Founders currently get business answers ("How's our pipeline in the energy sector this quarter?")
by manually pulling data from monday.com boards, cleaning it, cross-referencing boards, and
building ad-hoc analysis. Build a conversational AI agent that:

1. **Connects to monday.com** (two boards: Work Orders, Deals) via API or MCP — read-only.
2. **Handles messy data gracefully**: nulls, inconsistent dates/text/naming, and communicates data
   quality caveats to the user instead of silently guessing.
3. **Understands founder-level questions**, asks clarifying questions when a query is genuinely
   ambiguous, and answers using data from one or both boards as needed.
4. **Delivers business intelligence**: revenue, pipeline health, sector performance, ops metrics —
   with context/insight, not just raw numbers.
5. **(Optional) Helps prepare leadership updates** — e.g., a one-click "weekly/monthly summary"
   the agent can generate on request.

Hard constraint: **do not hardcode the CSV data into the agent.** The agent must query monday.com
live at request time. CSVs are only the seed data imported into monday.com boards.

Deliverables required: (1) hosted, link-accessible prototype, (2) a ≤2-page Decision Log
(assumptions, trade-offs, what you'd do with more time, how you interpreted "leadership updates"),
(3) source code as a ZIP with a README covering architecture + monday.com setup.

## 3. THE ACTUAL DATA (already profiled — use this, don't re-derive it)

### Board A: "Work Orders" (from Work_Order_Tracker_Data.xlsx, sheet "work order tracker")
~177 data rows, header on row 2. Columns include:
`Deal name masked, Customer Name Code, Serial# (SDPLDEAL-xxx), Nature of Work,
Last executed month of recurring project, Execution Status, Data Delivery Date, Date of PO/LOI,
Document Type, Probable Start Date, Probable End Date, BD/KAM Personnel code, Sector, Type of Work,
Is any Skylark software platform part of deliverables, Last invoice date, latest invoice no.,
Amount in Rupees (Excl of GST) (Masked), Amount in Rupees (Incl of GST) (Masked),
Billed Value (Excl/Incl GST), Collected Amount (Incl GST), Amount to be billed (Excl/Incl GST),
Amount Receivable, AR Priority account, Quantity by Ops, Quantities as per PO,
Quantity billed (till date), Balance in quantity, Invoice Status, Expected Billing Month,
Actual Billing Month, Actual Collection Month, WO Status (billed), Collection status,
Collection Date, Billing Status`

Known data-quality issues:
- `Collection status` is 100% empty — treat as "not tracked," never report as 0.
- `Execution Status` free text includes near-duplicates (`Executed until current month`,
  `Partial Completed`, `Pause / struck`, `Details pending from Client`) — normalize into a small
  canonical set (e.g. Not Started / Ongoing / Completed / On Hold / Blocked) but keep the raw value
  available for drill-down.
- `Invoice Status` mixes clean states (`Fully Billed`, `Partially Billed`, `Not billed yet`) with
  one-off strings (`Billed- Visit 7`, `Stuck`) — normalize with a fallback "Other (see raw value)".
- Dates arrive as real datetimes in most rows but as blank strings in others — never assume a date
  exists.
- Monetary fields are explicitly labeled "(Masked)" — treat as directionally correct scaled values,
  not real INR; never claim these are actual financials in agent output, just say "amount" or add
  a footnote that figures are masked/scaled for this exercise if the user asks.

### Board B: "Deals" (from Deal_funnel_Data.xlsx, sheet "Deal tracker")
~346 data rows. Columns:
`Deal Name, Owner code, Client Code, Deal Status, Close Date (A), Closure Probability,
Masked Deal value, Tentative Close Date, Deal Stage, Product deal, Sector/service, Created Date`

Known data-quality issues:
- `Deal Status` has 3 clean values (Won / Dead / Open) plus a rare `On Hold`.
- `Deal Stage` is a 15-step funnel from `A. Lead Generated` through `H. Work Order Received`,
  `G. Project Won`, `L. Project Lost`, `O. Not Relevant at all`, etc. — build a stage-order lookup
  so "how far along" queries can be answered numerically, not just as strings.
- **CRITICAL BUG TO HANDLE:** literal header-row values (`"Deal Status"`, `"Closure Probability"`,
  `"Deal Stage"`, `"Product deal"`, `"Sector/service"`) appear as *data* in a few rows — this is a
  copy-paste artifact in the source sheet. The normalization layer MUST detect and drop/flag rows
  where a column's value equals that column's own header string.
- `Masked Deal value` is null in ~52% of rows and `Closure Probability` is null in ~75% — any
  pipeline-value aggregation must explicitly state what % of rows had no value, not silently sum
  only the populated ones without saying so.
- `Sector/service` has inconsistent free text (`Others`, `Tender`, `DSP` alongside real sectors)
  and ~2% blank.

### Cross-board join (verified against the real files, not assumed)
The two boards share deals via **`Deal Name` (Deals board) ↔ `Deal name masked` (Work Orders
board)** — 52 of 58 distinct Work Order deal names match a Deal Name (fuzzy/exact match with
normalization for casing/whitespace). This is the join key for any question that spans pipeline
→ execution → billing (e.g., "which won deals haven't started execution yet", "average time from
deal-won to first invoice"). Note: `Deal Name` is a nickname/codename, not guaranteed globally
unique — when ambiguous, disambiguate using `Sector` + approximate `Created Date`/`Date of PO`
proximity, and say so to the user if you had to guess.

## 4. ARCHITECTURE

```
┌─────────────┐      chat/http       ┌──────────────────────┐      GraphQL       ┌──────────────┐
│  Frontend   │ ───────────────────▶ │   FastAPI backend     │ ─────────────────▶ │  monday.com   │
│  (chat UI)  │ ◀─────────────────── │  - Claude agent loop   │ ◀───────────────── │  API (v2)     │
└─────────────┘      streamed reply  │  - tool router          │    JSON            └──────────────┘
                                      │  - normalization layer │
                                      │  - conversation memory │
                                      └──────────────────────┘
```

**Agent pattern**: Claude with **tool use / function calling**, not a rigid NL→SQL translator.
Give Claude a small set of well-typed tools; let it plan multi-step queries (e.g., "pull deals in
Renewables that are Open, then check which have matching work orders") across multiple tool calls
per turn. This directly satisfies "query across multiple boards" and "ask clarifying questions
when needed" (Claude can just ask, using its own judgment, before calling tools if the request is
ambiguous — e.g. "this quarter" is undefined without a fiscal-year anchor, so it should ask or
state its assumption).

**Tools to expose to the agent** (implement as typed Python functions + JSON schemas):
1. `get_board_schema(board: "deals" | "work_orders")` → column names/types/known enum values.
   Lets the agent ground itself instead of hallucinating column names.
2. `query_deals(filters: dict, group_by: str|null, limit: int)` → filtered/aggregated rows from
   the Deals board (server-side pandas filtering after pulling board items via monday GraphQL).
3. `query_work_orders(filters: dict, group_by: str|null, limit: int)` → same for Work Orders.
4. `join_deals_and_work_orders(filters: dict)` → pre-joined view on the Deal Name key described
   above, for cross-board questions.
5. `get_data_quality_notes(board: str)` → returns the known null-rates / anomalies for that board
   at query time (computed live, not hardcoded) so the agent can proactively caveat answers.
6. `refresh_cache()` → force-refetch from monday.com (boards are cached in-memory with a short TTL
   to keep responses fast without hardcoding data).

**Normalization layer** (`normalization.py`, runs on every fetch, never on import only):
- Drops/flags leaked-header rows (value == own column header).
- Canonicalizes `Execution Status`, `Invoice Status`, `Deal Status`, `Sector` into controlled
  vocabularies with a `raw_value` field preserved.
- Parses dates defensively (blank/garbage → `None`, never today's date or 0).
- Adds a `stage_order` numeric column derived from the `Deal Stage` letter prefix (A→1 … O→15) so
  "how far along" and funnel-conversion questions are computable.
- Computes and exposes per-board null-rate stats used by `get_data_quality_notes`.

**System prompt for the agent** must instruct it to:
- Never fabricate numbers; only report what tools return.
- State data-quality caveats inline when relevant (e.g., "42% of these deals have no logged
  value, so this total is a floor, not the true pipeline value").
- Ask one clarifying question when a query is genuinely ambiguous (undefined time window, unclear
  metric, ambiguous deal name match) — but make a stated, reasonable assumption and proceed rather
  than blocking on trivial ambiguity.
- Prefer concise, founder-readable answers: headline number/insight first, supporting detail after.

## 5. TECH STACK (use exactly this — optimized for a 6-hour build + free/cheap hosting)

| Layer | Choice | Why |
|---|---|---|
| LLM / agent runtime | **Anthropic Claude (Messages API, tool use)**, model `claude-sonnet-4-6` | Best tool-use reliability for this scope; single API key, no separate agent framework needed |
| Backend | **Python 3.11 + FastAPI** | Fast to write, native async, easy GraphQL calls, easy to host |
| Data handling | **pandas** inside tool functions | Simplest way to filter/aggregate/join two small in-memory tables |
| monday.com access | **Direct GraphQL API v2** (`https://api.monday.com/v2`), read-only token | Fewer moving parts than running a separate MCP server process for a single hosted demo; still satisfies "MCP or API — your choice" |
| Frontend | **Single-page chat UI** (plain HTML/CSS/JS, `fetch` + `EventSource`/streaming, served as static files by FastAPI) | Fastest to build reliably in the time budget; still fully "full-stack" (separate concerns, real HTTP API); upgrade path to React/Next.js later if time allows |
| Hosting | **Render.com (or Railway) — single web service** running FastAPI + static frontend | One deploy, one public URL, free/cheap tier, no CORS complexity since frontend is served by the same origin |
| Config/secrets | `.env` (`MONDAY_API_TOKEN`, `MONDAY_DEALS_BOARD_ID`, `MONDAY_WORK_ORDERS_BOARD_ID`, `ANTHROPIC_API_KEY`) | Never commit secrets; README documents how to obtain the monday.com token and board IDs |

## 6. BUILD ORDER (do this in sequence, verify each step before moving on)

1. **Monday.com setup (manual, documented in README)**: create two boards, import the two CSVs,
   set sensible column types (Status/Dropdown for status-like fields, Date for date fields,
   Numbers for money/qty). Grab board IDs + a read-only personal API token.
2. `backend/monday_client.py` — thin GraphQL client: `fetch_board_items(board_id)` returning raw
   items+column_values as list[dict]. Add retry/backoff and clear error surfacing for auth/rate
   limit failures (required: "graceful handling of... API failures").
3. `backend/normalization.py` — turn raw monday items into clean pandas DataFrames per the rules
   in section 3/4 above. Unit-test against the two real files' known quirks (leaked headers, empty
   Collection status, etc.).
4. `backend/tools.py` — implement the 6 tools as plain functions + Anthropic tool JSON schemas.
5. `backend/agent.py` — the Claude tool-use loop: send message + tool defs → execute any
   `tool_use` blocks → feed `tool_result`s back → repeat until Claude returns a final text answer.
   Keep per-session conversation history in memory (dict keyed by session id) for follow-ups.
6. `backend/main.py` — FastAPI app: `POST /api/chat {session_id, message}` → agent reply; serves
   `frontend/` as static files at `/`.
7. `frontend/index.html` — minimal chat UI: message list, input box, calls `/api/chat`, renders
   markdown-ish text and any caveats distinctly (e.g., small "data quality note" styling).
8. **Leadership update feature**: add a 7th tool or a `/api/leadership-summary` endpoint that runs
   a fixed battery of BI queries (pipeline by stage, sector performance, overdue/at-risk work
   orders, billing/collection gaps) and has Claude compose a short structured summary (headline +
   3–5 bullets + caveats) — this is the concrete interpretation of the optional "leadership
   updates" requirement; document this interpretation in the Decision Log.
9. Manually test 8–10 founder-style questions (see section 7) before considering it done.
10. Deploy to Render, confirm the public link works from a clean browser session.
11. Write `DECISION_LOG.md` (≤2 pages) and `README.md` (architecture + monday.com setup + how to
    run locally + env vars).

## 7. TEST QUESTIONS TO VALIDATE AGAINST BEFORE CALLING IT DONE

- "How's our pipeline looking for the mining sector right now?"
- "Which deals are Won but don't have a matching work order yet?"
- "What % of our deal values are actually populated, and what's the total for what we have?"
- "Show me work orders that are overdue on billing."
- "Give me a leadership summary for this week."
- A deliberately ambiguous one: "How are we doing this quarter?" (should trigger a clarifying
  question or a clearly stated assumption about the time window).

## 8. OUT OF SCOPE FOR THIS BUILD (say so if asked, don't silently build these)

- Write access to monday.com (assignment is read-only).
- Real authentication/multi-tenant user accounts (single-token demo is fine).
- Perfect entity resolution for the Deal Name join — approximate + transparent is acceptable and
  should be documented as a trade-off in the Decision Log.

---

Now: scaffold the repository exactly per section 6, working file by file, and stop to show me the
`monday_client.py` + `normalization.py` output before continuing to the agent loop, since those two
are the highest-risk pieces given how messy the source data is.
