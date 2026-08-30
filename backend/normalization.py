"""
Turns raw monday.com board rows (list[dict], text-rendered column values) into clean
pandas DataFrames, and computes data-quality stats the agent can surface to the user.

This is deliberately conservative: we NEVER invent a value. Blank/garbage becomes None/NaN,
never "0", "Unknown deal", or today's date.
"""

from __future__ import annotations
import re
import pandas as pd

# ---------------------------------------------------------------------------
# Canonical vocabularies (raw value is always preserved alongside the normalized one)
# ---------------------------------------------------------------------------

EXECUTION_STATUS_MAP = {
    "not started": "Not Started",
    "ongoing": "Ongoing",
    "executed until current month": "Ongoing",
    "completed": "Completed",
    "partial completed": "Partially Completed",
    "pause / struck": "On Hold / Stuck",
    "details pending from client": "Blocked (client)",
}

INVOICE_STATUS_MAP = {
    "fully billed": "Fully Billed",
    "partially billed": "Partially Billed",
    "not billed yet": "Not Billed",
    "stuck": "Stuck",
}

DEAL_STAGE_ORDER = {
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "I": 9, "J": 10, "K": 11, "L": 12, "M": 13, "N": 14, "O": 15,
}


def _blank_to_none(v):
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _drop_leaked_header_rows(df: pd.DataFrame) -> pd.DataFrame:
    """The Deals sheet has rows where a column's value literally equals that column's
    own header text (a copy-paste artifact from the source spreadsheet). Drop those rows."""
    if df.empty:
        return df
    mask = pd.Series(False, index=df.index)
    for col in df.columns:
        if col.startswith("_"):
            continue
        mask = mask | (df[col].astype(str).str.strip() == col.strip())
    dropped = int(mask.sum())
    if dropped:
        df = df.loc[~mask].copy()
        df.attrs["leaked_header_rows_dropped"] = dropped
    return df


def _parse_date(v):
    v = _blank_to_none(v)
    if v is None:
        return None
    dt = pd.to_datetime(v, errors="coerce")
    return dt if not pd.isna(dt) else None


def _parse_number(v):
    v = _blank_to_none(v)
    if v is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", v)
    if cleaned in ("", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_deals(raw_rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(raw_rows)
    if df.empty:
        return df
    df = _drop_leaked_header_rows(df)

    for col in df.columns:
        if col.startswith("_"):
            continue
        df[col] = df[col].map(_blank_to_none)

    df["deal_status_norm"] = df.get("Deal Status")
    df["sector_norm"] = df.get("Sector/service").map(
        lambda x: x.strip().title() if x else None
    ) if "Sector/service" in df else None

    if "Deal Stage" in df:
        df["deal_stage_letter"] = df["Deal Stage"].map(
            lambda x: x.strip()[0] if x else None
        )
        df["deal_stage_order"] = df["deal_stage_letter"].map(DEAL_STAGE_ORDER)

    for date_col in ["Close Date (A)", "Tentative Close Date", "Created Date"]:
        if date_col in df:
            df[date_col + " (parsed)"] = df[date_col].map(_parse_date)

    if "Masked Deal value" in df:
        df["deal_value_num"] = df["Masked Deal value"].map(_parse_number)

    return df


def normalize_work_orders(raw_rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(raw_rows)
    if df.empty:
        return df
    df = _drop_leaked_header_rows(df)

    for col in df.columns:
        if col.startswith("_"):
            continue
        df[col] = df[col].map(_blank_to_none)

    if "Execution Status" in df:
        df["execution_status_norm"] = df["Execution Status"].map(
            lambda x: EXECUTION_STATUS_MAP.get(x.strip().lower(), f"Other: {x}") if x else None
        )
    if "Invoice Status" in df:
        df["invoice_status_norm"] = df["Invoice Status"].map(
            lambda x: INVOICE_STATUS_MAP.get(x.strip().lower(), f"Other: {x}") if x else None
        )
    if "Sector" in df:
        df["sector_norm"] = df["Sector"].map(lambda x: x.strip().title() if x else None)

    for date_col in ["Data Delivery Date", "Date of PO/LOI", "Probable Start Date",
                      "Probable End Date", "Last invoice date", "Collection Date"]:
        if date_col in df:
            df[date_col + " (parsed)"] = df[date_col].map(_parse_date)

    for amt_col in [
        "Amount in Rupees (Excl of GST) (Masked)",
        "Amount in Rupees (Incl of GST) (Masked)",
        "Amount Receivable (Masked)",
    ]:
        if amt_col in df:
            df[amt_col + " (num)"] = df[amt_col].map(_parse_number)

    return df


def data_quality_report(df: pd.DataFrame, board_label: str) -> dict:
    """Live-computed (not hardcoded) null-rate + anomaly stats for a board's dataframe."""
    if df.empty:
        return {"board": board_label, "row_count": 0, "note": "No data returned from monday.com."}

    total = len(df)
    null_rates = {}
    for col in df.columns:
        if col.startswith("_"):
            continue
        nulls = df[col].isna().sum() if df[col].dtype != object else df[col].isna().sum()
        rate = round(100 * nulls / total, 1)
        if rate > 0:
            null_rates[col] = f"{rate}% empty"

    return {
        "board": board_label,
        "row_count": total,
        "leaked_header_rows_dropped": df.attrs.get("leaked_header_rows_dropped", 0),
        "notable_null_rates": null_rates,
    }


def join_deals_and_work_orders(deals_df: pd.DataFrame, wo_df: pd.DataFrame) -> pd.DataFrame:
    """Join on Deal Name (Deals) <-> Deal name masked (Work Orders), case/whitespace
    normalized. Deal names are codenames, not guaranteed unique, so this is a best-effort
    join — callers should treat multi-match rows as ambiguous."""
    if deals_df.empty or wo_df.empty:
        return pd.DataFrame()

    d = deals_df.copy()
    w = wo_df.copy()
    d["_join_key"] = d.get("Deal Name", pd.Series(dtype=str)).map(
        lambda x: x.strip().lower() if x else None
    )
    w["_join_key"] = w.get("Deal name masked", pd.Series(dtype=str)).map(
        lambda x: x.strip().lower() if x else None
    )

    merged = d.merge(w, on="_join_key", how="inner", suffixes=("_deal", "_wo"))
    return merged
