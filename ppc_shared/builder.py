"""Core campaign log builder — pure data in, data out. No I/O, no formatting.

This is the single source of truth for campaign extraction + metric computation.
Both logs_maker.py (CLI/Excel) and process_upload.py (API) call this.
"""
from ppc_shared.parsers import parse_sheet
from ppc_shared.extraction import extract_campaigns, extract_placement_data, extract_base_bids
from ppc_shared.bids import max_bid_text
from ppc_shared.dashboard import read_dashboard_tos, match_tos_is
from ppc_shared.business_report import read_business_report, get_campaign_price


def build_campaigns(bulk_path, portfolio=None, days=7, dashboard_path=None, br_path=None):
    """Process bulk sheet + optional files into campaign records + summary.

    Returns:
        campaigns: list of dicts with snake_case keys (internal format)
        summary: dict with aggregate metrics
        camp_asins: dict {campaign_name: set of ASINs}
        asin_price: dict {ASIN: price}
        br_totals: dict {revenue, orders}
    """
    # Load optional data sources
    asin_price, camp_asins, br_totals, _ = read_business_report(
        br_path, bulk_path, portfolio
    )
    if asin_price:
        print(f"Business report: {len(asin_price)} ASINs with prices loaded")

    dashboard_is = read_dashboard_tos(dashboard_path, portfolio)

    all_campaigns = []

    def _build_log(name, c, tos=None, ros=None, pp=None, ab=None, base=None, ad_type="SP"):
        tos = tos or {}
        ros = ros or {}
        pp = pp or {}
        ab = ab or {}
        strategy = c.get("bidding_strategy", "")

        # Match TOS IS%
        tos_is_val = match_tos_is(name, dashboard_is) if dashboard_is else None

        return {
            "campaign_name": name,
            "ad_type": ad_type,
            "price": get_campaign_price(name, c, camp_asins, asin_price),
            "tos_is_pct": tos_is_val,
            "acos_all": c.get("acos_all"),
            "acos_tos": tos.get("acos_tos"),
            "acos_ros": ros.get("acos_ros"),
            "acos_pp": pp.get("acos_pp"),
            "acos_ab": ab.get("acos_ab"),
            "cr_all": c.get("cr_all"),
            "cr_tos": tos.get("cr_tos"),
            "cr_ros": ros.get("cr_ros"),
            "cr_pp": pp.get("cr_pp"),
            "cr_ab": ab.get("cr_ab"),
            "cpc_all": c.get("cpc_all"),
            "cpc_tos": tos.get("cpc_tos"),
            "cpc_ros": ros.get("cpc_ros"),
            "cpc_pp": pp.get("cpc_pp"),
            "cpc_ab": ab.get("cpc_ab"),
            "ctr_all": c.get("ctr_all"),
            "ctr_tos": tos.get("ctr_tos"),
            "ctr_ros": ros.get("ctr_ros"),
            "ctr_pp": pp.get("ctr_pp"),
            "ctr_ab": ab.get("ctr_ab"),
            "base_bid": base,
            "max_tos": max_bid_text(base, tos.get("pct_tos"), strategy, 2.0),
            "max_ros": max_bid_text(base, ros.get("pct_ros"), strategy, 1.5),
            "max_pp": max_bid_text(base, pp.get("pct_pp"), strategy, 1.5),
            "max_ab": max_bid_text(base, ab.get("pct_ab"), strategy, 2.0),
            "total_spend": round(c.get("spend", 0), 2),
            "daily_spend": round(c["spend"] / days, 2) if days and days > 0 else None,
            "budget": c.get("budget"),
            "ppc_revenue": round(c.get("sales", 0), 2),
            "orders_all": c.get("orders_all"),
            "orders_tos": tos.get("orders_tos"),
            "orders_ros": ros.get("orders_ros"),
            "orders_pp": pp.get("orders_pp"),
            "orders_ab": ab.get("orders_ab"),
            "bidding_strategy": strategy or None,
            "clicks_all": c.get("clicks_all"),
            "clicks_tos": tos.get("clicks_tos"),
            "clicks_ros": ros.get("clicks_ros"),
            "clicks_pp": pp.get("clicks_pp"),
            "clicks_ab": ab.get("clicks_ab"),
            # Rank fields — populated by apply_ranking_data later
            "sp_rank": None,
            "org_rank": None,
        }

    # SP Campaigns
    sp_df = parse_sheet(bulk_path, "Sponsored Products Campaigns")
    if sp_df is not None:
        sp_camps = extract_campaigns(sp_df, portfolio)
        tos_data = extract_placement_data(sp_df, sp_camps, "tos")
        ros_data = extract_placement_data(sp_df, sp_camps, "ros")
        pp_data = extract_placement_data(sp_df, sp_camps, "pp")
        ab_data = extract_placement_data(sp_df, sp_camps, "ab")
        base_bids = extract_base_bids(sp_df, sp_camps)

        for name, c in sp_camps.items():
            all_campaigns.append(_build_log(
                name, c,
                tos=tos_data.get(name, {}), ros=ros_data.get(name, {}),
                pp=pp_data.get(name, {}), ab=ab_data.get(name, {}),
                base=base_bids.get(name), ad_type="SP",
            ))

    if dashboard_is:
        matched = sum(1 for c in all_campaigns if c["tos_is_pct"] is not None)
        print(f"Dashboard: matched TOS IS% for {matched}/{len(all_campaigns)} campaigns")

    # SD Campaigns
    sd_df = parse_sheet(bulk_path, "Sponsored Display Campaigns")
    if sd_df is not None:
        sd_camps = extract_campaigns(sd_df, portfolio)
        for name, c in sd_camps.items():
            all_campaigns.append(_build_log(name, c, ad_type="SD"))

    # SB Campaigns
    sb_df = parse_sheet(bulk_path, "Sponsored Brands Campaigns")
    if sb_df is not None:
        sb_camps = extract_campaigns(sb_df, portfolio)
        for name, c in sb_camps.items():
            all_campaigns.append(_build_log(name, c, ad_type="SB"))

    # Compute ratios and CPA
    total_spend = sum(c.get("total_spend", 0) or 0 for c in all_campaigns)
    total_orders = sum(c.get("orders_all", 0) or 0 for c in all_campaigns)
    total_budget = sum(c.get("budget", 0) or 0 for c in all_campaigns)

    for c in all_campaigns:
        spend = c.get("total_spend", 0) or 0
        orders = c.get("orders_all", 0) or 0
        c["cpa"] = round(spend / orders, 2) if orders > 0 else None
        c["spend_ratio"] = round(spend / total_spend, 4) if total_spend > 0 else 0
        c["order_ratio"] = round(orders / total_orders, 4) if total_orders > 0 else 0
        c["recommended_budget"] = round(c["order_ratio"] * total_budget, 2) if total_budget > 0 else 0

    # Build summary
    total_ppc_revenue = sum(c.get("ppc_revenue", 0) or 0 for c in all_campaigns)
    total_ppc_acos = round(total_spend / total_ppc_revenue, 4) if total_ppc_revenue > 0 else None
    daily_orders = total_orders / days if days and days > 0 else None

    tacos = None
    br_revenue = br_totals.get("revenue")
    br_orders = br_totals.get("orders")
    organic_orders = None
    if br_revenue and br_revenue > 0:
        tacos = round(total_spend / br_revenue, 4)
    if br_orders is not None:
        organic_orders = max(0, br_orders - int(total_orders))

    summary = {
        "tacos": tacos,
        "br_revenue": round(br_revenue, 2) if br_revenue else None,
        "br_orders": br_orders,
        "organic_orders": organic_orders,
        "daily_orders": round(daily_orders, 2) if daily_orders else None,
        "total_spend": round(total_spend, 2),
        "daily_spend": round(total_spend / days, 2) if days and days > 0 else None,
        "budget": round(total_budget, 2),
        "ppc_revenue": round(total_ppc_revenue, 2),
        "cpa": round(total_spend / total_orders, 2) if total_orders > 0 else None,
        "acos_all": total_ppc_acos,
        "orders_all": int(total_orders),
    }

    return all_campaigns, summary, camp_asins, asin_price, br_totals
