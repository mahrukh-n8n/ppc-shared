"""Campaign, placement, and bid extraction from bulk sheet DataFrames."""
from ppc_shared.utils import safe_float, safe_str, get_campaign_name, get_portfolio_name
from ppc_shared.parsers import parse_sheet


def extract_campaigns(df, portfolio=None):
    """Extract campaign-level rows from a sheet DataFrame, optionally filtered by portfolio."""
    camps = {}
    for _, row in df.iterrows():
        entity = safe_str(row.get("entity", row.get("Entity", ""))).lower()
        if entity != "campaign":
            continue
        name = get_campaign_name(row)
        if not name:
            continue
        state = safe_str(row.get("campaign state (informational only)",
                                  row.get("state", row.get("State", ""))))
        if state == "archived":
            continue
        if portfolio and portfolio != "-":
            port_name = get_portfolio_name(row)
            if port_name.lower() != portfolio.lower():
                continue

        camps[name] = {
            "campaign_name": name,
            "acos_all": safe_float(row.get("acos")),
            "cr_all": safe_float(row.get("conversion rate")),
            "cpc_all": safe_float(row.get("cpc")),
            "ctr_all": safe_float(row.get("click-through rate")),
            "spend": safe_float(row.get("spend")),
            "sales": safe_float(row.get("sales")),
            "budget": safe_float(row.get("daily budget", row.get("budget"))),
            "orders_all": safe_float(row.get("units", row.get("orders"))),
            "clicks_all": safe_float(row.get("clicks")),
            "bidding_strategy": safe_str(row.get("bidding strategy")),
        }
    return camps


def extract_placement_data(df, portfolio_camps, placement_name):
    """Extract placement-level metrics for campaigns in portfolio_camps dict."""
    placement_map = {
        "tos": "placement top",
        "ros": "placement rest of search",
        "pp": "placement product page",
        "ab": "placement amazon business",
    }
    target_placement = placement_map.get(placement_name, placement_name)
    data = {}
    for _, row in df.iterrows():
        entity = safe_str(row.get("entity", "")).lower()
        if entity != "bidding adjustment":
            continue
        placement = safe_str(row.get("placement", "")).lower()
        if placement != target_placement:
            continue
        camp_name = safe_str(
            row.get("campaign name (informational only)", row.get("campaign name", ""))
        )
        if camp_name not in portfolio_camps:
            continue
        data[camp_name] = {
            f"acos_{placement_name}": safe_float(row.get("acos")),
            f"cr_{placement_name}": safe_float(row.get("conversion rate")),
            f"cpc_{placement_name}": safe_float(row.get("cpc")),
            f"ctr_{placement_name}": safe_float(row.get("click-through rate")),
            f"orders_{placement_name}": safe_float(row.get("units", row.get("orders"))),
            f"clicks_{placement_name}": safe_float(row.get("clicks")),
            f"pct_{placement_name}": safe_float(row.get("percentage")),
        }
    return data


def extract_base_bids(df, portfolio_camps):
    """Extract base bid per campaign from keyword/product targeting rows (enabled only)."""
    bids = {}
    for _, row in df.iterrows():
        entity = safe_str(row.get("entity", "")).lower()
        if entity not in ("keyword", "product targeting"):
            continue
        state = safe_str(row.get("state", "")).lower()
        if state != "enabled":
            continue
        camp_name = safe_str(
            row.get("campaign name (informational only)", row.get("campaign name", ""))
        )
        if camp_name not in portfolio_camps or camp_name in bids:
            continue
        bid = safe_float(row.get("bid"))
        if bid > 0:
            bids[camp_name] = bid
    return bids


def extract_campaign_asins(bulk_path, portfolio=None):
    """Build campaign → set of ASINs map from product ads in bulk sheet."""
    sp_df = parse_sheet(bulk_path, "Sponsored Products Campaigns")
    camp_asins = {}
    if sp_df is None:
        return camp_asins
    for _, row in sp_df.iterrows():
        entity = safe_str(row.get("entity", "")).lower()
        if entity != "product ad":
            continue
        state = safe_str(row.get("state", "")).lower()
        if state == "archived":
            continue
        if portfolio and portfolio != "-":
            port = get_portfolio_name(row)
            if port.lower() != portfolio.lower():
                continue
        camp = safe_str(
            row.get("campaign name (informational only)", row.get("campaign name", ""))
        )
        asin = safe_str(row.get("asin (informational only)", ""))
        if camp and asin:
            camp_asins.setdefault(camp, set()).add(asin)
    return camp_asins
