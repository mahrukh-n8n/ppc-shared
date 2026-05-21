"""Campaign, placement, and bid extraction from bulk sheet DataFrames."""
from ppc_shared.parsers import parse_sheet
from ppc_shared.utils import (
    get_campaign_name,
    get_portfolio_name,
    normalize_text,
    safe_float,
    safe_str,
)


def _sum_ad_group_metrics(df, portfolio=None):
    """Aggregate ad-group metrics by campaign for SP fallback handling."""
    aggregates = {}
    portfolio_norm = normalize_text(portfolio)

    for _, row in df.iterrows():
        entity = normalize_text(row.get("entity", row.get("Entity", "")))
        if entity != "ad group":
            continue

        state = normalize_text(row.get("ad group state (informational only)", row.get("state", "")))
        if state == "archived":
            continue

        if portfolio and portfolio != "-":
            port_name = get_portfolio_name(row)
            if normalize_text(port_name) != portfolio_norm:
                continue

        name = get_campaign_name(row)
        if not name:
            continue

        agg = aggregates.setdefault(name, {
            "impressions": 0.0,
            "clicks": 0.0,
            "spend": 0.0,
            "sales": 0.0,
            "orders_all": 0.0,
        })
        agg["impressions"] += safe_float(row.get("impressions"))
        agg["clicks"] += safe_float(row.get("clicks"))
        agg["spend"] += safe_float(row.get("spend"))
        agg["sales"] += safe_float(row.get("sales"))
        agg["orders_all"] += safe_float(row.get("units", row.get("orders")))

    return aggregates


def _sum_target_metrics(df, portfolio=None):
    """Aggregate lower-level targeting metrics by campaign for reconciliation."""
    aggregates = {}
    portfolio_norm = normalize_text(portfolio)

    for _, row in df.iterrows():
        entity = normalize_text(row.get("entity", row.get("Entity", "")))
        if entity not in ("keyword", "product targeting", "audience targeting"):
            continue

        state = normalize_text(row.get("state", ""))
        if state == "archived":
            continue

        if portfolio and portfolio != "-":
            port_name = get_portfolio_name(row)
            if normalize_text(port_name) != portfolio_norm:
                continue

        name = get_campaign_name(row)
        if not name:
            continue

        agg = aggregates.setdefault(name, {
            "impressions": 0.0,
            "clicks": 0.0,
            "spend": 0.0,
            "sales": 0.0,
            "orders_all": 0.0,
        })
        agg["impressions"] += safe_float(row.get("impressions"))
        agg["clicks"] += safe_float(row.get("clicks"))
        agg["spend"] += safe_float(row.get("spend"))
        agg["sales"] += safe_float(row.get("sales"))
        agg["orders_all"] += safe_float(row.get("units", row.get("orders")))

    return aggregates


def _close_enough(left, right, rel_tol=0.01, abs_tol=1.0):
    return abs((left or 0.0) - (right or 0.0)) <= max(abs_tol, abs(right or 0.0) * rel_tol)


def _materially_different(left, right, rel_tol=0.02, abs_tol=1.0):
    return not _close_enough(left, right, rel_tol=rel_tol, abs_tol=abs_tol)


def should_use_ad_group_metrics(campaign, ad_group, target=None, orders_key="orders_all"):
    """Return True when campaign-level conversion metrics appear stale.

    Amazon bulk exports can surface two metric bases in SP rows. Campaign and
    placement rows may hold stale/lower sales and orders while ad group,
    keyword/product-targeting, and STR rows reconcile to the current totals.
    """
    if not ad_group:
        return False

    campaign_sales = campaign.get("sales", 0) or 0
    campaign_orders = campaign.get(orders_key, 0) or 0
    ad_group_sales = ad_group.get("sales", 0) or 0
    ad_group_orders = ad_group.get("orders_all", 0) or 0

    if ad_group_sales <= 0 and ad_group_orders <= 0:
        return False

    # Existing safety net: campaign rows with zero conversions can be stale.
    if campaign_sales <= 0 and campaign_orders <= 0:
        return True

    differs_from_campaign = (
        _materially_different(campaign_sales, ad_group_sales)
        or _materially_different(campaign_orders, ad_group_orders)
    )
    if not differs_from_campaign:
        return False

    # Stronger rule: only replace non-zero campaign rows when the ad-group
    # aggregate is independently supported by target-level rows in the bulk.
    if not target:
        return False

    target_sales = target.get("sales", 0) or 0
    target_orders = target.get("orders_all", 0) or 0
    if target_sales <= 0 and target_orders <= 0:
        return False

    return (
        _close_enough(ad_group_sales, target_sales)
        and _close_enough(ad_group_orders, target_orders)
    )


def _target_supports_ad_group(ad_group, target):
    if not ad_group or not target:
        return False
    ad_group_sales = ad_group.get("sales", 0) or 0
    ad_group_orders = ad_group.get("orders_all", 0) or 0
    target_sales = target.get("sales", 0) or 0
    target_orders = target.get("orders_all", 0) or 0
    if ad_group_sales <= 0 and ad_group_orders <= 0:
        return False
    if target_sales <= 0 and target_orders <= 0:
        return False
    return (
        _close_enough(ad_group_sales, target_sales)
        and _close_enough(ad_group_orders, target_orders)
    )


def campaign_layer_is_stale(campaigns, ad_group_metrics, target_metrics=None, orders_key="orders_all"):
    """Detect account-level stale Campaign rows against ad-group/target totals."""
    target_metrics = target_metrics or {}
    campaign_sales = campaign_orders = 0.0
    ad_group_sales = ad_group_orders = 0.0
    target_sales = target_orders = 0.0

    for name, camp in campaigns.items():
        ad_group = ad_group_metrics.get(name)
        target = target_metrics.get(name)
        if not _target_supports_ad_group(ad_group, target):
            continue
        campaign_sales += camp.get("sales", 0) or 0
        campaign_orders += camp.get(orders_key, 0) or 0
        ad_group_sales += ad_group.get("sales", 0) or 0
        ad_group_orders += ad_group.get("orders_all", 0) or 0
        target_sales += target.get("sales", 0) or 0
        target_orders += target.get("orders_all", 0) or 0

    if ad_group_sales <= 0 and ad_group_orders <= 0:
        return False

    ad_group_matches_target = (
        _close_enough(ad_group_sales, target_sales)
        and _close_enough(ad_group_orders, target_orders)
    )
    campaign_differs = (
        _materially_different(campaign_sales, ad_group_sales)
        or _materially_different(campaign_orders, ad_group_orders)
    )
    return ad_group_matches_target and campaign_differs


def apply_ad_group_metric_reconciliation(
    campaigns,
    ad_group_metrics,
    target_metrics=None,
    orders_key="orders_all",
    clicks_key="clicks_all",
    ctr_key="ctr_all",
    cpc_key="cpc_all",
    conversion_rate_key="cr_all",
    acos_key="acos_all",
    units_key=None,
):
    """Mutate campaign metrics to ad-group totals when campaign rows are stale."""
    target_metrics = target_metrics or {}
    whole_layer_stale = campaign_layer_is_stale(
        campaigns,
        ad_group_metrics,
        target_metrics,
        orders_key=orders_key,
    )
    for name, agg in ad_group_metrics.items():
        camp = campaigns.get(name)
        if not camp:
            continue
        use_ad_group = (
            whole_layer_stale and _target_supports_ad_group(agg, target_metrics.get(name))
        ) or should_use_ad_group_metrics(
            camp,
            agg,
            target_metrics.get(name),
            orders_key=orders_key,
        )
        if not use_ad_group:
            camp.setdefault("metric_source", "campaign")
            continue

        impressions = agg["impressions"]
        clicks = agg["clicks"]
        spend = agg["spend"]
        sales = agg["sales"]
        orders = agg["orders_all"]

        camp["impressions"] = impressions
        camp[clicks_key] = clicks
        camp["spend"] = spend
        camp["sales"] = sales
        camp[orders_key] = orders
        if units_key:
            camp[units_key] = orders
        camp[ctr_key] = (clicks / impressions) if impressions > 0 else 0.0
        camp[cpc_key] = (spend / clicks) if clicks > 0 else 0.0
        camp[conversion_rate_key] = (orders / clicks) if clicks > 0 else 0.0
        camp[acos_key] = (spend / sales) if sales > 0 else 0.0
        camp["metric_source"] = "ad_group_reconciled"

    return campaigns


def extract_campaigns(df, portfolio=None):
    """Extract campaign-level rows from a sheet DataFrame, optionally filtered by portfolio."""
    camps = {}
    portfolio_norm = normalize_text(portfolio)

    for _, row in df.iterrows():
        entity = normalize_text(row.get("entity", row.get("Entity", "")))
        if entity != "campaign":
            continue

        name = get_campaign_name(row)
        if not name:
            continue

        state = normalize_text(
            row.get("campaign state (informational only)", row.get("state", row.get("State", "")))
        )
        if state == "archived":
            continue

        if portfolio and portfolio != "-":
            port_name = get_portfolio_name(row)
            if normalize_text(port_name) != portfolio_norm:
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

    ad_group_metrics = _sum_ad_group_metrics(df, portfolio)
    target_metrics = _sum_target_metrics(df, portfolio)
    apply_ad_group_metric_reconciliation(camps, ad_group_metrics, target_metrics)

    return camps


def extract_placement_data(df, portfolio_camps, placement_name):
    """Extract placement-level metrics for campaigns in portfolio_camps dict."""
    placement_map = {
        "tos": "placement top",
        "ros": "placement rest of search",
        "pp": "placement product page",
        "ab": "placement amazon business",
    }
    target_placement = normalize_text(placement_map.get(placement_name, placement_name))
    data = {}

    for _, row in df.iterrows():
        entity = normalize_text(row.get("entity", ""))
        if entity != "bidding adjustment":
            continue

        placement = normalize_text(row.get("placement", ""))
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
        entity = normalize_text(row.get("entity", ""))
        if entity not in ("keyword", "product targeting"):
            continue

        state = normalize_text(row.get("state", ""))
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
    """Build campaign -> set of ASINs map from product ads in bulk sheet."""
    sp_df = parse_sheet(bulk_path, "Sponsored Products Campaigns")
    camp_asins = {}
    if sp_df is None:
        return camp_asins

    portfolio_norm = normalize_text(portfolio)
    for _, row in sp_df.iterrows():
        entity = normalize_text(row.get("entity", ""))
        if entity != "product ad":
            continue

        state = normalize_text(row.get("state", ""))
        if state == "archived":
            continue

        if portfolio and portfolio != "-":
            port = get_portfolio_name(row)
            if normalize_text(port) != portfolio_norm:
                continue

        camp = safe_str(
            row.get("campaign name (informational only)", row.get("campaign name", ""))
        )
        asin = safe_str(row.get("asin (informational only)", ""))
        if camp and asin:
            camp_asins.setdefault(camp, set()).add(asin)
    return camp_asins
