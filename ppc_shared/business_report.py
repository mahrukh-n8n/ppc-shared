"""Business report parsing — CSV (raw Amazon) or JSON (parsed audit format)."""
import json
import os

import pandas as pd

from ppc_shared.utils import safe_float, safe_str
from ppc_shared.extraction import extract_campaign_asins


def read_business_report(br_path, bulk_path=None, portfolio=None):
    """Read product prices and totals from business report.

    Supports: raw Amazon BR CSV or parsed JSON from audit pipeline.

    Returns:
        asin_price: dict {ASIN: price}
        camp_asins: dict {campaign_name: set of ASINs}
        br_totals: dict {revenue, orders}
        br_child_metrics: list of {asin, units, sales} dicts
    """
    asin_price = {}
    camp_asins = {}
    br_totals = {"revenue": None, "orders": None}
    br_rows = []

    if not br_path or not os.path.exists(br_path):
        return asin_price, camp_asins, br_totals, br_rows

    try:
        ext = os.path.splitext(br_path)[1].lower()
        if ext in (".csv", ".xlsx", ".xls"):
            if ext == ".csv":
                br_df = pd.read_csv(br_path, encoding="utf-8-sig")
            else:
                br_df = pd.read_excel(br_path, engine="openpyxl")
            br_df.columns = br_df.columns.str.strip()
            for _, row in br_df.iterrows():
                asin = safe_str(row.get("(Child) ASIN", row.get("asin", "")))
                sales_raw = str(row.get("Ordered Product Sales",
                                        row.get("ordered_product_sales", "0")))
                sales = safe_float(sales_raw.replace("$", "").replace(",", "")) or 0
                units = safe_float(row.get("Units ordered",
                                           row.get("units_ordered", 0))) or 0
                if asin:
                    br_rows.append({"asin": asin, "units": units, "sales": sales})
        elif ext == ".json":
            with open(br_path) as f:
                br_data = json.load(f)
            for cm in br_data.get("child_metrics", []):
                br_rows.append({
                    "asin": cm.get("asin", ""),
                    "units": cm.get("units_ordered", 0),
                    "sales": cm.get("ordered_product_sales", 0),
                })

        # Build price map
        for item in br_rows:
            asin, units, sales = item["asin"], item["units"], item["sales"]
            if asin and units > 0:
                asin_price[asin] = round(sales / units, 2)

    except Exception as e:
        print(f"WARNING: Could not read business report: {e}")
        return asin_price, camp_asins, br_totals, br_rows

    # Build campaign → ASINs from product ads
    if bulk_path:
        camp_asins = extract_campaign_asins(bulk_path, portfolio)

    # Compute BR totals for portfolio ASINs
    portfolio_asins = set()
    for asins in camp_asins.values():
        portfolio_asins.update(asins)
    if portfolio_asins and br_rows:
        br_totals["orders"] = sum(
            item["units"] for item in br_rows if item["asin"] in portfolio_asins
        )
        br_totals["revenue"] = sum(
            item["sales"] for item in br_rows if item["asin"] in portfolio_asins
        )

    return asin_price, camp_asins, br_totals, br_rows


def get_campaign_price(name, campaign_data, camp_asins, asin_price):
    """Derive price for a campaign.

    Priority:
    1. Business report prices for campaign's ASINs
    2. Campaign sales/orders fallback

    Returns: float (single price), string (range like '$29.99-$39.99'), or None
    """
    asins = camp_asins.get(name, set())
    if asins and asin_price:
        prices = sorted(set(asin_price[a] for a in asins if a in asin_price))
        if prices:
            if len(prices) == 1:
                return prices[0]
            return f"${prices[0]:.2f}-${prices[-1]:.2f}"

    sales = campaign_data.get("sales", 0) or 0
    orders = campaign_data.get("orders_all", 0) or 0
    if orders > 0 and sales > 0:
        return round(sales / orders, 2)
    return None
