"""
STR (Search Term Report) parser.

Reads Amazon STR Excel/CSV files, normalizes headers and column names,
validates mandatory columns, calculates derived metrics, and returns
normalized row dicts ready for enrichment.

Consolidates logic from:
  - data/audit/scripts/parse_str.py
  - prompts/optimization/01-parse/search-term-report.md
"""

import math
import os
import re
from datetime import datetime

import pandas as pd

from ppc_shared.utils import safe_float, safe_str
from ppc_shared.detection import detect_date_range


# ─── Column mapping with Amazon marketplace variants ─────────

COLUMN_ALIASES = {
    "campaign name": "campaign_name",
    "campaign": "campaign_name",
    "ad group name": "ad_group_name",
    "ad group": "ad_group_name",
    "targeting": "targeting",
    "match type": "match_type",
    "customer search term": "customer_search_term",
    "search term": "customer_search_term",
    "impressions": "impressions",
    "clicks": "clicks",
    "spend": "spend",
    # Orders variants (Amazon changes these by marketplace)
    "7 day total orders (#)": "orders",
    "orders": "orders",
    "purchases": "orders",
    "7 day total purchases": "orders",
    # Sales variants
    "7 day total sales": "sales",
    "sales": "sales",
    "revenue": "sales",
    "7 day total revenue": "sales",
}

MANDATORY_COLUMNS = [
    "campaign_name",
    "ad_group_name",
    "targeting",
    "match_type",
    "customer_search_term",
    "impressions",
    "clicks",
    "spend",
    "orders",
    "sales",
]


def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase and strip all column headers."""
    df.columns = df.columns.str.lower().str.strip()
    return df


def _map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map actual column names to canonical names using aliases.

    Returns a dict of {canonical_name: actual_column_name} for all matched aliases.
    """
    mapping = {}
    for col in df.columns:
        canonical = COLUMN_ALIASES.get(col)
        if canonical:
            mapping[canonical] = col
    return mapping


def _validate_columns(mapping: dict[str, str]) -> list[str]:
    """Return list of missing mandatory columns."""
    return [col for col in MANDATORY_COLUMNS if col not in mapping]


def _detect_period_from_file(filepath: str) -> tuple[str | None, str | None]:
    """Try to detect date period from filename, fall back to detect_date_range."""
    # Try detect_date_range first (works for bulk sheet naming patterns)
    try:
        d1, d2, _days, _label = detect_date_range(filepath)
        if d1 and d2:
            return d1.strftime("%Y-%m-%d"), d2.strftime("%Y-%m-%d")
    except Exception:
        pass

    # Fallback: try to extract dates from filename with regex
    basename = os.path.basename(filepath)
    # Patterns like "STR 60 days.xlsx", "str_01Mar-31Mar2025.xlsx"
    date_match = re.search(
        r"(\d{1,2}[A-Za-z]{3})[^A-Za-z0-9]*(\d{1,2}[A-Za-z]{3}\d{2,4})",
        basename,
    )
    if date_match:
        return None, None  # Detected but can't parse — caller handles

    return None, None


def parse_str(
    filepath: str,
    bulk_campaign_names: set[str] | None = None,
) -> dict:
    """Parse an Amazon STR file into normalized rows.

    Args:
        filepath: Path to xlsx or csv file
        bulk_campaign_names: Optional set of bulk sheet campaign names for coverage check

    Returns:
        {
            "rows": [...],
            "period_start": str | None,
            "period_end": str | None,
            "row_count": int,
            "warnings": [...],
        }
    """
    # Read file
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath, sheet_name=0, engine="openpyxl")

    # Normalize headers
    df = _normalize_headers(df)

    # Map columns to canonical names
    col_map = _map_columns(df)
    missing = _validate_columns(col_map)
    if missing:
        raise ValueError(f"STR file missing mandatory columns: {', '.join(missing)}")

    # Detect period
    period_start, period_end = _detect_period_from_file(filepath)

    # Parse rows
    rows = []
    warnings = []

    for idx, row in df.iterrows():
        campaign = safe_str(row.get(col_map.get("campaign_name", ""), ""))
        ad_group = safe_str(row.get(col_map.get("ad_group_name", ""), ""))
        targeting = safe_str(row.get(col_map.get("targeting", ""), ""))
        match_type = safe_str(row.get(col_map.get("match_type", ""), ""))
        search_term = safe_str(row.get(col_map.get("customer_search_term", ""), ""))
        impressions = int(safe_float(row.get(col_map.get("impressions", ""), 0)))
        clicks = int(safe_float(row.get(col_map.get("clicks", ""), 0)))
        spend = safe_float(row.get(col_map.get("spend", ""), 0))
        orders = int(safe_float(row.get(col_map.get("orders", ""), 0)))
        sales = safe_float(row.get(col_map.get("sales", ""), 0))

        # Validation
        if not search_term:
            warnings.append(f"Row {idx}: empty search term skipped")
            continue
        if spend < 0:
            warnings.append(f"Row {idx}: negative spend {spend}")
            continue

        # Derived metrics
        acos = round(spend / sales * 100, 2) if sales > 0 else None
        ctr = round(clicks / impressions * 100, 4) if impressions > 0 else 0
        cvr = round(orders / clicks * 100, 2) if clicks > 0 else 0
        cpc = round(spend / clicks, 4) if clicks > 0 else 0

        rows.append(
            {
                "campaign_name": campaign,
                "ad_group_name": ad_group or None,
                "targeting": targeting or None,
                "match_type": match_type or None,
                "customer_search_term": search_term,
                "impressions": impressions,
                "clicks": clicks,
                "spend": round(spend, 4),
                "orders": orders,
                "sales": round(sales, 4),
                "acos": acos,
                "ctr": ctr,
                "cvr": cvr,
                "cpc": cpc,
                "bulk_campaign_match": campaign in bulk_campaign_names
                if bulk_campaign_names
                else None,
            }
        )

    return {
        "rows": rows,
        "period_start": period_start,
        "period_end": period_end,
        "row_count": len(rows),
        "warnings": warnings,
    }
