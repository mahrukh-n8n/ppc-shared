"""Dashboard TOS IS% reading and matching."""
import os

import pandas as pd

from ppc_shared.utils import safe_str


def read_dashboard_tos(dashboard_path, portfolio=None):
    """Read TOS IS% values from dashboard file (CSV or Excel).

    Returns dict: {campaign_name: tos_is_value}
    Values are stored as decimals (0.1862 = 18.62%) for the app,
    or as text strings ("<5%", "18.6%") depending on caller's needs.
    Use format_tos_is() to convert.
    """
    if not dashboard_path or not os.path.exists(dashboard_path):
        return {}
    try:
        ext = os.path.splitext(dashboard_path)[1].lower()
        if ext == ".csv":
            dash_df = pd.read_csv(dashboard_path, encoding="utf-8-sig")
        else:
            dash_df = pd.read_excel(dashboard_path, engine="openpyxl")
        dash_df.columns = dash_df.columns.str.lower()

        is_map = {}
        for _, row in dash_df.iterrows():
            camp = safe_str(row.get("campaigns", ""))
            tos_is = safe_str(row.get("top-of-search is", ""))
            if not camp or not tos_is:
                continue

            # Parse to decimal
            if tos_is.startswith("<") or tos_is.startswith(">"):
                num_part = tos_is[1:].rstrip("%").strip()
                try:
                    is_map[camp] = round(float(num_part) / 100, 4)
                except ValueError:
                    pass
            elif tos_is.endswith("%"):
                try:
                    is_map[camp] = round(float(tos_is.rstrip("%")) / 100, 4)
                except ValueError:
                    pass
            else:
                try:
                    val = float(tos_is)
                    is_map[camp] = round(val if val < 1 else val / 100, 4)
                except ValueError:
                    pass

        # Portfolio filter
        if portfolio and portfolio != "-" and "portfolio" in dash_df.columns:
            port_camps = set(
                safe_str(r.get("campaigns", ""))
                for _, r in dash_df.iterrows()
                if safe_str(r.get("portfolio", "")).lower() == portfolio.lower()
            )
            is_map = {k: v for k, v in is_map.items() if k in port_camps}

        return is_map
    except Exception as e:
        print(f"WARNING: Could not read dashboard data: {e}")
        return {}


def match_tos_is(campaign_name, is_map):
    """Match a campaign name to TOS IS% value. Tries exact then substring match.
    Returns the matched value or None.
    """
    if campaign_name in is_map:
        return is_map[campaign_name]
    for dash_name, val in is_map.items():
        if dash_name in campaign_name or campaign_name in dash_name:
            return val
    return None


def format_tos_is_text(decimal_val):
    """Convert decimal TOS IS% to display text: 0.1862 → '18.6%', 0.05 → '<5%'."""
    if decimal_val is None:
        return None
    pct = decimal_val * 100
    if pct < 5:
        return "<5%"
    return f"{pct:.1f}%"
