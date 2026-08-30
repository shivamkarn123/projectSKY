"""
Tool layer: a small set of typed functions the Claude agent can call, plus their
Anthropic tool-use JSON schemas. Board data is cached in-memory with a TTL so we're
not hitting monday.com on every single tool call within one conversation turn, while
still guaranteeing we query monday.com live (never hardcoded CSVs) per turn/session.
"""

import time
import pandas as pd

import config
from monday_client import fetch_board_items, MondayAPIError
from normalization import (
    normalize_deals,
    normalize_work_orders,
    data_quality_report,
    join_deals_and_work_orders,
)
from mock_data import get_mock_board_data, get_mock_stats

_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def _get_board_df(board: str) -> pd.DataFrame:
    now = time.time()
    if board in _cache:
        ts, df = _cache[board]
        if now - ts < config.CACHE_TTL_SECONDS:
            return df

    if board == "deals":
        if config.MOCK_MODE:
            raw = get_mock_board_data(config.MONDAY_DEALS_BOARD_ID)
        else:
            raw = fetch_board_items(config.MONDAY_DEALS_BOARD_ID)
        df = normalize_deals(raw)
    elif board == "work_orders":
        if config.MOCK_MODE:
            raw = get_mock_board_data(config.MONDAY_WORK_ORDERS_BOARD_ID)
        else:
            raw = fetch_board_items(config.MONDAY_WORK_ORDERS_BOARD_ID)
        df = normalize_work_orders(raw)
    else:
        raise ValueError(f"Unknown board: {board}")

    _cache[board] = (now, df)
    return df


def _apply_filters(df: pd.DataFrame, filters: dict | None) -> pd.DataFrame:
    """Very small filter DSL: {"column": "value"} does case-insensitive substring
    match on that column. Missing columns are ignored (agent may guess wrong names;
    fail soft, not hard)."""
    if not filters:
        return df
    out = df
    for col, val in filters.items():
        if col not in out.columns or val is None:
            continue
        out = out[out[col].astype(str).str.contains(str(val), case=False, na=False)]
    return out


def _summarize(df: pd.DataFrame, group_by: str | None, limit: int) -> dict:
    if df.empty:
        return {"row_count": 0, "rows": [], "grouped": None}

    result = {"row_count": len(df)}
    if group_by and group_by in df.columns:
        result["grouped"] = df.groupby(group_by, dropna=False).size().to_dict()
    else:
        result["grouped"] = None

    result["rows"] = df.head(limit).to_dict(orient="records")
    return result


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_get_board_schema(board: str) -> dict:
    df = _get_board_df(board)
    schema = {}
    for col in df.columns:
        if col.startswith("_"):
            continue
        sample_vals = df[col].dropna().unique()[:8].tolist()
        schema[col] = {"sample_values": sample_vals}
    return {"board": board, "columns": schema}


def tool_query_deals(filters: dict | None = None, group_by: str | None = None, limit: int = 25) -> dict:
    try:
        df = _get_board_df("deals")
    except MondayAPIError as e:
        return {"error": str(e)}
    filtered = _apply_filters(df, filters)
    return _summarize(filtered, group_by, limit)


def tool_query_work_orders(filters: dict | None = None, group_by: str | None = None, limit: int = 25) -> dict:
    try:
        df = _get_board_df("work_orders")
    except MondayAPIError as e:
        return {"error": str(e)}
    filtered = _apply_filters(df, filters)
    return _summarize(filtered, group_by, limit)


def tool_join_deals_and_work_orders(filters: dict | None = None, limit: int = 25) -> dict:
    try:
        deals_df = _get_board_df("deals")
        wo_df = _get_board_df("work_orders")
    except MondayAPIError as e:
        return {"error": str(e)}
    merged = join_deals_and_work_orders(deals_df, wo_df)
    filtered = _apply_filters(merged, filters)
    return _summarize(filtered, None, limit)


def tool_get_data_quality_notes(board: str) -> dict:
    try:
        if board == "both":
            deals_df = _get_board_df("deals")
            wo_df = _get_board_df("work_orders")
            return {
                "deals": data_quality_report(deals_df, "deals"),
                "work_orders": data_quality_report(wo_df, "work_orders"),
            }
        df = _get_board_df(board)
        return data_quality_report(df, board)
    except MondayAPIError as e:
        return {"error": str(e)}


def tool_refresh_cache() -> dict:
    _cache.clear()
    return {"status": "cache cleared, next query will re-fetch from monday.com"}


# ---------------------------------------------------------------------------
# Anthropic tool schemas
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "get_board_schema",
        "description": (
            "Get the column names and sample values for a monday.com board. Call this "
            "before filtering on a column you're not sure exists, to avoid guessing wrong "
            "column names."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "board": {"type": "string", "enum": ["deals", "work_orders"]},
            },
            "required": ["board"],
        },
    },
    {
        "name": "query_deals",
        "description": (
            "Query the Deals (sales pipeline) board with optional filters and grouping. "
            "Filters are case-insensitive substring matches, e.g. "
            "{\"sector_norm\": \"Mining\", \"deal_status_norm\": \"Open\"}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {"type": "object", "description": "column_name -> substring to match"},
                "group_by": {"type": "string", "description": "optional column to group/count by"},
                "limit": {"type": "integer", "default": 25},
            },
        },
    },
    {
        "name": "query_work_orders",
        "description": (
            "Query the Work Orders (execution + billing) board with optional filters and "
            "grouping. Filters are case-insensitive substring matches, e.g. "
            "{\"sector_norm\": \"Renewables\", \"execution_status_norm\": \"Ongoing\"}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {"type": "object"},
                "group_by": {"type": "string"},
                "limit": {"type": "integer", "default": 25},
            },
        },
    },
    {
        "name": "join_deals_and_work_orders",
        "description": (
            "Get a joined view across both boards (matched on deal name) for questions "
            "that span pipeline and execution, e.g. 'which won deals have no work order yet'. "
            "Best-effort join — deal names are codenames and may not be globally unique."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {"type": "object"},
                "limit": {"type": "integer", "default": 25},
            },
        },
    },
    {
        "name": "get_data_quality_notes",
        "description": (
            "Get live-computed data quality stats (null rates, dropped bad rows) for a board "
            "or both boards. Use this to decide whether/how to caveat an answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "board": {"type": "string", "enum": ["deals", "work_orders", "both"]},
            },
            "required": ["board"],
        },
    },
    {
        "name": "refresh_cache",
        "description": "Force a fresh pull from monday.com, bypassing the short in-memory cache.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

TOOL_FUNCTIONS = {
    "get_board_schema": tool_get_board_schema,
    "query_deals": tool_query_deals,
    "query_work_orders": tool_query_work_orders,
    "join_deals_and_work_orders": tool_join_deals_and_work_orders,
    "get_data_quality_notes": tool_get_data_quality_notes,
    "refresh_cache": tool_refresh_cache,
}
