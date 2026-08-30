# Decision Log — Skylark Drones BI Agent

## Key assumptions
- The two boards join on **Deal Name (Deals) ↔ Deal name masked (Work Orders)**, not on client
  code — verified against the real files (52/58 Work Order deal names match a Deal Name). Deal
  names are codenames, not guaranteed unique, so this join is best-effort and flagged as such in
  agent responses when a match is ambiguous.
- Masked monetary fields are treated as directionally meaningful but explicitly *not* real INR —
  the agent never implies these are actual financial figures.
- "This quarter" / "recently" and similar relative time phrases have no fixed fiscal-year anchor
  in the data, so the agent either asks or states its assumed window rather than guessing silently.
- `Collection status` is 100% empty in the sample — treated as "not tracked" rather than "zero
  collections."

## Trade-offs chosen and why
- **Direct GraphQL API over monday.com's MCP server**: fewer moving parts to host for a single
  demo deployment; still fulfills "MCP or API — your choice." Trade-off: loses the
  standardized-tool-discovery benefit of MCP if this were to scale to many more data sources.
- **Plain HTML/CSS/JS frontend over React/Next.js**: faster to build reliably in the time budget
  and removes a build step from deployment; trade-off is less componentized UI code if the app
  grows.
- **Substring-match filter DSL over full NL→SQL/query language**: lets Claude plan filters in
  plain JSON without needing a query grammar; trade-off is less precise than exact-match/range
  filters, so numeric range questions currently rely on the agent pulling broader data and
  reasoning over it rather than a server-side range filter (see "with more time" below).
- **In-memory cache/session state over Redis/DB**: adequate for a single-process demo; would not
  survive a restart or scale horizontally.

## What I'd do differently with more time
- Add explicit numeric range and date range filter operators (not just substring match) so large
  aggregations don't require pulling full boards into context.
- Persist sessions and the board cache in Redis so the service can scale beyond one instance.
- Add a lightweight eval set (the test questions in MASTER_PROMPT.md section 7) run automatically
  against each deploy to catch regressions in tool-selection quality.
- Improve the Deals↔Work Orders join with a fuzzy-match fallback (e.g. Levenshtein on deal name +
  sector proximity) for the ~10% of names that don't match exactly.
- Add lightweight usage/error logging so failed monday.com calls in production are visible.

## How I interpreted "leadership updates"
Implemented as a dedicated `/api/leadership-summary` endpoint (and a chat suggestion chip) that
runs a fixed battery of BI queries — pipeline by stage, sector performance, work orders at risk
(overdue billing / stuck execution), and billing/collection gaps — and has Claude compose a short,
skimmable summary: one headline, 3-5 bullets, and a caveats line when data quality materially
affects a number. This targets the actual leadership workflow (a recurring, scannable status
update) rather than a generic export/report feature.
