"""Shared utility functions — safe type conversion, name extraction."""
import math

import pandas as pd


def safe_float(val, default=0.0):
    """Convert to float, handling None, NaN, percentage strings, EU commas, currency symbols."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s in ("-", "--", "N/A"):
        return default
    if s.startswith("<") or s.startswith(">"):
        s = s[1:]
    if s.endswith("%"):
        s = s[:-1].strip()
    s = s.replace("$", "").replace("€", "").replace("£", "")
    if "." in s and "," in s:
        s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def safe_str(val, default=""):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    return str(val).strip()


def get_campaign_name(row):
    """Get campaign name from bulk sheet row."""
    name = row.get("campaign name", "")
    if pd.isna(name) or name == "":
        name = row.get("campaign name (informational only)", "")
    return safe_str(name)


def get_portfolio_name(row):
    """Get portfolio name from a row, checking multiple possible column names."""
    for col in ["portfolio name (informational only)", "Portfolio name",
                "portfolio name", "Portfolio Name"]:
        val = row.get(col, "")
        s = safe_str(val)
        if s:
            return s
    return ""
