"""Sheet-level parsers for Amazon bulk sheet (SP, SB, SD)."""
import pandas as pd

from ppc_shared.utils import normalize_text, safe_float, safe_str


SHEET_NAME_ALIASES = {
    "Sponsored Products Campaigns": [
        "Sponsored Products Campaigns",
    ],
    "Sponsored Brands Campaigns": [
        "Sponsored Brands Campaigns",
        "Sponsored Brands campaigns",
    ],
    "Sponsored Display Campaigns": [
        "Sponsored Display Campaigns",
        "Sponsored Display campaigns",
    ],
    "Portfolios": [
        "Portfolios",
    ],
}


def resolve_sheet_name(file_path, sheet_name):
    """Resolve a sheet name case-insensitively using known aliases first."""
    try:
        with pd.ExcelFile(file_path, engine="openpyxl") as excel:
            sheet_names = list(excel.sheet_names)
    except Exception:
        return None

    normalized_to_actual = {
        normalize_text(actual): actual
        for actual in sheet_names
    }

    candidates = SHEET_NAME_ALIASES.get(sheet_name, [sheet_name])
    for candidate in candidates:
        actual = normalized_to_actual.get(normalize_text(candidate))
        if actual:
            return actual

    requested = normalize_text(sheet_name)
    for normalized, actual in normalized_to_actual.items():
        if normalized == requested:
            return actual

    return None


def parse_sheet(file_path, sheet_name):
    """Read a single sheet from bulk file. Returns DataFrame with lowercase columns, or None."""
    try:
        resolved_sheet_name = resolve_sheet_name(file_path, sheet_name)
        if resolved_sheet_name is None:
            return None
        df = pd.read_excel(file_path, sheet_name=resolved_sheet_name, engine="openpyxl")
        df.columns = df.columns.str.lower()
        return df
    except Exception:
        return None


def parse_sp_sheet(file_path):
    """Parse Sponsored Products Campaigns sheet into structured dicts.
    Returns dict with: campaigns, ad_groups, keywords, product_ads,
    product_targets, placements, negative_keywords, summary, validation_warnings.
    """
    df = parse_sheet(file_path, "Sponsored Products Campaigns")
    if df is None:
        return {
            "campaigns": [], "ad_groups": [], "keywords": [],
            "product_ads": [], "product_targets": [], "placements": [],
            "negative_keywords": [], "summary": "SP sheet not found",
            "validation_warnings": [],
        }

    from ppc_shared.utils import get_campaign_name

    campaigns, ad_groups, keywords = [], [], []
    product_ads, product_targets, placements = [], [], []
    negative_keywords, validation_warnings = [], []

    def _get_ad_group_name(row):
        name = row.get("ad group name", "")
        if pd.isna(name) or name == "":
            name = row.get("ad group name (informational only)", "")
        return safe_str(name)

    for idx, row in df.iterrows():
        entity = normalize_text(row.get("entity", "Unknown"))
        try:
            if entity == "campaign":
                campaign_name = get_campaign_name(row)
                if not campaign_name:
                    validation_warnings.append(f"Row {idx}: Missing Campaign Name")
                    continue
                state = normalize_text(row.get("campaign state (informational only)", ""))
                if state == "archived":
                    continue
                campaigns.append({
                    "campaign_name": campaign_name,
                    "campaign_id": row.get("campaign id", ""),
                    "state": state,
                    "daily_budget": safe_float(row.get("daily budget")),
                    "bidding_strategy": safe_str(row.get("bidding strategy")),
                    "portfolio_name": safe_str(row.get("portfolio name (informational only)")),
                    "impressions": safe_float(row.get("impressions")),
                    "clicks": safe_float(row.get("clicks")),
                    "spend": safe_float(row.get("spend")),
                    "sales": safe_float(row.get("sales")),
                    "orders": safe_float(row.get("orders")),
                    "acos": safe_float(row.get("acos")),
                    "cpc": safe_float(row.get("cpc")),
                    "roas": safe_float(row.get("roas")),
                    "conversion_rate": safe_float(row.get("conversion rate")),
                    "ctr": safe_float(row.get("click-through rate")),
                    "units": safe_float(row.get("units")),
                    "status": "paused" if state == "paused" else "active",
                    "zero_spend": safe_float(row.get("spend")) == 0,
                })
            elif entity == "ad group":
                state = normalize_text(row.get("ad group state (informational only)", ""))
                if state == "archived":
                    continue
                ad_groups.append({
                    "campaign_name": get_campaign_name(row),
                    "ad_group_name": _get_ad_group_name(row),
                    "state": state,
                    "default_bid": safe_float(row.get("ad group default bid")),
                    "impressions": safe_float(row.get("impressions")),
                    "clicks": safe_float(row.get("clicks")),
                    "spend": safe_float(row.get("spend")),
                    "sales": safe_float(row.get("sales")),
                    "orders": safe_float(row.get("orders")),
                    "acos": safe_float(row.get("acos")),
                    "cpc": safe_float(row.get("cpc")),
                    "roas": safe_float(row.get("roas")),
                    "status": "paused" if state == "paused" else "active",
                })
            elif entity == "keyword":
                state = normalize_text(row.get("state", ""))
                if state == "archived":
                    continue
                keywords.append({
                    "campaign_name": get_campaign_name(row),
                    "ad_group_name": _get_ad_group_name(row),
                    "keyword_text": safe_str(row.get("keyword text")),
                    "match_type": safe_str(row.get("match type")),
                    "state": state,
                    "keyword_bid": safe_float(row.get("bid")),
                    "impressions": safe_float(row.get("impressions")),
                    "clicks": safe_float(row.get("clicks")),
                    "spend": safe_float(row.get("spend")),
                    "sales": safe_float(row.get("sales")),
                    "orders": safe_float(row.get("orders")),
                    "acos": safe_float(row.get("acos")),
                    "cpc": safe_float(row.get("cpc")),
                    "roas": safe_float(row.get("roas")),
                    "status": "paused" if state == "paused" else "active",
                })
            elif entity == "product ad":
                state = normalize_text(row.get("state", ""))
                if state == "archived":
                    continue
                product_ads.append({
                    "campaign_name": get_campaign_name(row),
                    "ad_group_name": _get_ad_group_name(row),
                    "sku": safe_str(row.get("sku")),
                    "asin": safe_str(row.get("asin (informational only)")),
                    "state": state,
                    "impressions": safe_float(row.get("impressions")),
                    "clicks": safe_float(row.get("clicks")),
                    "spend": safe_float(row.get("spend")),
                    "sales": safe_float(row.get("sales")),
                    "orders": safe_float(row.get("orders")),
                    "units": safe_float(row.get("units")),
                    "acos": safe_float(row.get("acos")),
                    "cpc": safe_float(row.get("cpc")),
                    "roas": safe_float(row.get("roas")),
                    "conversion_rate": safe_float(row.get("conversion rate")),
                    "ctr": safe_float(row.get("click-through rate")),
                    "metric_source": "native_product_ad",
                })
            elif entity in ("product targeting", "negative product targeting"):
                state = normalize_text(row.get("state", ""))
                if state == "archived":
                    continue
                is_negative = entity == "negative product targeting"
                targeting_expression = safe_str(
                    row.get("product targeting expression",
                            row.get("resolved product targeting expression (informational only)", ""))
                )
                product_targets.append({
                    "campaign_name": get_campaign_name(row),
                    "ad_group_name": _get_ad_group_name(row),
                    "targeting_expression": targeting_expression,
                    "bid": safe_float(row.get("bid")),
                    "state": state, "is_negative": is_negative,
                    "impressions": safe_float(row.get("impressions")),
                    "clicks": safe_float(row.get("clicks")),
                    "spend": safe_float(row.get("spend")),
                    "sales": safe_float(row.get("sales")),
                    "orders": safe_float(row.get("orders")),
                    "acos": safe_float(row.get("acos")),
                    "status": "paused" if state == "paused" else "active",
                })
            elif entity in ("negative keyword", "campaign negative keyword"):
                keyword_text = safe_str(row.get("keyword text"))
                state = normalize_text(row.get("state", ""))
                if not keyword_text or state == "archived":
                    continue
                negative_keywords.append({
                    "campaign_name": get_campaign_name(row),
                    "ad_group_name": _get_ad_group_name(row) if entity == "negative keyword" else "",
                    "keyword_text": normalize_text(keyword_text),
                    "match_type": normalize_text(row.get("match type")),
                    "level": "campaign" if entity == "campaign negative keyword" else "ad_group",
                    "state": state,
                })
            elif entity == "bidding adjustment":
                placements.append({
                    "campaign_name": get_campaign_name(row),
                    "placement": safe_str(row.get("placement")),
                    "percentage": safe_float(row.get("percentage")),
                    "impressions": safe_float(row.get("impressions")),
                    "clicks": safe_float(row.get("clicks")),
                    "spend": safe_float(row.get("spend")),
                    "sales": safe_float(row.get("sales")),
                    "orders": safe_float(row.get("orders")),
                    "conversion_rate": safe_float(row.get("conversion rate")),
                    "cpc": safe_float(row.get("cpc")),
                    "ctr": safe_float(row.get("click-through rate")),
                    "acos": safe_float(row.get("acos")),
                    "units": safe_float(row.get("units")),
                })
        except Exception as e:
            validation_warnings.append(f"Row {idx}: Error processing entity {entity} - {e}")

    if campaigns:
        from ppc_shared.extraction import (
            _sum_ad_group_metrics,
            _sum_target_metrics,
            apply_ad_group_metric_reconciliation,
        )

        campaign_map = {c["campaign_name"]: c for c in campaigns}
        apply_ad_group_metric_reconciliation(
            campaign_map,
            _sum_ad_group_metrics(df),
            _sum_target_metrics(df),
            orders_key="orders",
            clicks_key="clicks",
            ctr_key="ctr",
            cpc_key="cpc",
            conversion_rate_key="conversion_rate",
            acos_key="acos",
            units_key="units",
        )
        reconciled = sum(1 for c in campaigns if c.get("metric_source") == "ad_group_reconciled")
        if reconciled:
            validation_warnings.append(
                f"Reconciled {reconciled} SP campaign row(s) from ad group totals because the Campaign metric layer was stale or differed from target-supported Ad group totals."
            )

    total_spend = sum(c.get("spend", 0) for c in campaigns)
    total_sales = sum(c.get("sales", 0) for c in campaigns)
    overall_acos = total_spend / total_sales if total_sales > 0 else 0
    summary = f"Campaigns: {len(campaigns)}, Keywords: {len(keywords)}, Spend: ${total_spend:.2f}, ACoS: {overall_acos:.2%}"

    return {
        "campaigns": campaigns, "ad_groups": ad_groups, "keywords": keywords,
        "product_ads": product_ads, "product_targets": product_targets,
        "placements": placements, "negative_keywords": negative_keywords,
        "summary": summary, "validation_warnings": validation_warnings,
    }


def parse_sb_sheet(file_path):
    """Parse Sponsored Brands Campaigns sheet."""
    df = parse_sheet(file_path, "Sponsored Brands Campaigns")
    if df is None:
        return {"sb_campaigns": [], "sb_keywords": []}
    sb_campaigns, sb_keywords = [], []
    for _, row in df.iterrows():
        entity = normalize_text(row.get("entity", ""))
        if entity == "campaign":
            name = safe_str(row.get("campaign name"))
            state = normalize_text(row.get("campaign state (informational only)", row.get("state", "")))
            if state == "archived" or not name:
                continue
            is_video = any(v in normalize_text(name) for v in ["video", "sbv"])
            sb_campaigns.append({
                "campaign_name": name, "ad_type": "SBV" if is_video else "SB",
                "state": state, "budget": safe_float(row.get("budget")),
                "bid_optimisation": safe_str(row.get("bid optimisation", row.get("bid optimization", ""))),
                "portfolio_name": safe_str(row.get("portfolio name (informational only)")),
                "impressions": safe_float(row.get("impressions")),
                "clicks": safe_float(row.get("clicks")),
                "spend": safe_float(row.get("spend")),
                "sales": safe_float(row.get("sales")),
                "orders": safe_float(row.get("orders")),
                "acos": safe_float(row.get("acos")),
                "cpc": safe_float(row.get("cpc")),
                "roas": safe_float(row.get("roas")),
                "conversion_rate": safe_float(row.get("conversion rate")),
                "ctr": safe_float(row.get("click-through rate")),
                "units": safe_float(row.get("units")),
            })
        elif entity == "keyword":
            state = normalize_text(row.get("state", ""))
            if state == "archived":
                continue
            sb_keywords.append({
                "campaign_name": safe_str(row.get("campaign name (informational only)", row.get("campaign name", ""))),
                "keyword_text": safe_str(row.get("keyword text")),
                "match_type": safe_str(row.get("match type")),
                "state": state, "bid": safe_float(row.get("bid")),
                "impressions": safe_float(row.get("impressions")),
                "clicks": safe_float(row.get("clicks")),
                "spend": safe_float(row.get("spend")),
                "sales": safe_float(row.get("sales")),
                "orders": safe_float(row.get("orders")),
                "acos": safe_float(row.get("acos")),
            })
    if sb_campaigns:
        from ppc_shared.extraction import (
            _sum_ad_group_metrics,
            _sum_target_metrics,
            apply_ad_group_metric_reconciliation,
        )

        campaign_map = {c["campaign_name"]: c for c in sb_campaigns}
        apply_ad_group_metric_reconciliation(
            campaign_map,
            _sum_ad_group_metrics(df),
            _sum_target_metrics(df),
            orders_key="orders",
            clicks_key="clicks",
            ctr_key="ctr",
            cpc_key="cpc",
            conversion_rate_key="conversion_rate",
            acos_key="acos",
            units_key="units",
        )
    return {"sb_campaigns": sb_campaigns, "sb_keywords": sb_keywords}


def parse_sd_sheet(file_path):
    """Parse Sponsored Display Campaigns sheet."""
    df = parse_sheet(file_path, "Sponsored Display Campaigns")
    if df is None:
        return {"sd_campaigns": [], "sd_targets": []}
    sd_campaigns, sd_targets = [], []
    for _, row in df.iterrows():
        entity = normalize_text(row.get("entity", ""))
        if entity == "campaign":
            name = safe_str(row.get("campaign name"))
            state = normalize_text(row.get("campaign state (informational only)", row.get("state", "")))
            if state == "archived" or not name:
                continue
            sd_campaigns.append({
                "campaign_name": name, "ad_type": "SD", "state": state,
                "budget": safe_float(row.get("budget")),
                "bid_optimisation": safe_str(row.get("bid optimisation", row.get("bid optimization", ""))),
                "portfolio_name": safe_str(row.get("portfolio name (informational only)")),
                "tactic": safe_str(row.get("tactic")),
                "cost_type": safe_str(row.get("cost type")),
                "impressions": safe_float(row.get("impressions")),
                "clicks": safe_float(row.get("clicks")),
                "spend": safe_float(row.get("spend")),
                "sales": safe_float(row.get("sales")),
                "orders": safe_float(row.get("orders")),
                "acos": safe_float(row.get("acos")),
                "cpc": safe_float(row.get("cpc")),
                "roas": safe_float(row.get("roas")),
                "conversion_rate": safe_float(row.get("conversion rate")),
                "ctr": safe_float(row.get("click-through rate")),
                "units": safe_float(row.get("units")),
                "viewable_impressions": safe_float(row.get("viewable impressions")),
                "sales_views_clicks": safe_float(row.get("sales (views & clicks)", row.get("sales (views and clicks)"))),
                "orders_views_clicks": safe_float(row.get("orders (views & clicks)", row.get("orders (views and clicks)"))),
                "units_views_clicks": safe_float(row.get("units (views & clicks)", row.get("units (views and clicks)"))),
                "acos_views_clicks": safe_float(row.get("acos (views & clicks)", row.get("acos (views and clicks)"))),
                "roas_views_clicks": safe_float(row.get("roas (views & clicks)", row.get("roas (views and clicks)"))),
            })
        elif entity == "audience targeting":
            state = normalize_text(row.get("state", ""))
            if state == "archived":
                continue
            sd_targets.append({
                "campaign_name": safe_str(row.get("campaign name (informational only)", row.get("campaign name", ""))),
                "targeting_expression": safe_str(row.get("targeting expression")),
                "state": state, "bid": safe_float(row.get("bid")),
                "impressions": safe_float(row.get("impressions")),
                "clicks": safe_float(row.get("clicks")),
                "spend": safe_float(row.get("spend")),
                "sales": safe_float(row.get("sales")),
                "orders": safe_float(row.get("orders")),
                "acos": safe_float(row.get("acos")),
            })
    if sd_campaigns:
        from ppc_shared.extraction import (
            _sum_ad_group_metrics,
            _sum_target_metrics,
            apply_ad_group_metric_reconciliation,
        )

        campaign_map = {c["campaign_name"]: c for c in sd_campaigns}
        apply_ad_group_metric_reconciliation(
            campaign_map,
            _sum_ad_group_metrics(df),
            _sum_target_metrics(df),
            orders_key="orders",
            clicks_key="clicks",
            ctr_key="ctr",
            cpc_key="cpc",
            conversion_rate_key="conversion_rate",
            acos_key="acos",
            units_key="units",
        )
    return {"sd_campaigns": sd_campaigns, "sd_targets": sd_targets}


def parse_all(file_path):
    """Parse all sheets (SP + SB + SD) and return combined dict."""
    output = parse_sp_sheet(file_path)
    output.update(parse_sb_sheet(file_path))
    output.update(parse_sd_sheet(file_path))
    return output
