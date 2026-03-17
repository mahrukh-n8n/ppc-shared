"""Sheet-level parsers for Amazon bulk sheet (SP, SB, SD)."""
import pandas as pd

from ppc_shared.utils import safe_float, safe_str


def parse_sheet(file_path, sheet_name):
    """Read a single sheet from bulk file. Returns DataFrame with lowercase columns, or None."""
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
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
        name = row.get("Ad group name", "")
        if pd.isna(name) or name == "":
            name = row.get("ad group name (informational only)", "")
        return safe_str(name)

    for idx, row in df.iterrows():
        entity = safe_str(row.get("entity", "Unknown")).lower()
        try:
            if entity == "campaign":
                campaign_name = get_campaign_name(row)
                if not campaign_name:
                    validation_warnings.append(f"Row {idx}: Missing Campaign Name")
                    continue
                state = safe_str(row.get("campaign state (informational only)", ""))
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
                state = safe_str(row.get("ad group state (informational only)", ""))
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
                state = safe_str(row.get("state", ""))
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
                state = safe_str(row.get("state", ""))
                if state == "archived":
                    continue
                product_ads.append({
                    "campaign_name": get_campaign_name(row),
                    "ad_group_name": _get_ad_group_name(row),
                    "sku": safe_str(row.get("sku")),
                    "asin": safe_str(row.get("asin (informational only)")),
                    "state": state,
                })
            elif entity in ("product targeting", "negative product targeting"):
                state = safe_str(row.get("state", ""))
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
                state = safe_str(row.get("state", ""))
                if not keyword_text or state == "archived":
                    continue
                negative_keywords.append({
                    "campaign_name": get_campaign_name(row),
                    "ad_group_name": _get_ad_group_name(row) if entity == "negative keyword" else "",
                    "keyword_text": keyword_text.lower(),
                    "match_type": safe_str(row.get("match type")).lower(),
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
        entity = safe_str(row.get("entity", "")).lower()
        if entity == "campaign":
            name = safe_str(row.get("campaign name"))
            state = safe_str(row.get("campaign state (informational only)", row.get("state", "")))
            if state == "archived" or not name:
                continue
            is_video = any(v in name.lower() for v in ["video", "sbv"])
            sb_campaigns.append({
                "campaign_name": name, "ad_type": "SBV" if is_video else "SB",
                "state": state, "budget": safe_float(row.get("budget")),
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
            state = safe_str(row.get("state", ""))
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
    return {"sb_campaigns": sb_campaigns, "sb_keywords": sb_keywords}


def parse_sd_sheet(file_path):
    """Parse Sponsored Display Campaigns sheet."""
    df = parse_sheet(file_path, "Sponsored Display Campaigns")
    if df is None:
        return {"sd_campaigns": [], "sd_targets": []}
    sd_campaigns, sd_targets = [], []
    for _, row in df.iterrows():
        entity = safe_str(row.get("entity", "")).lower()
        if entity == "campaign":
            name = safe_str(row.get("campaign name"))
            state = safe_str(row.get("campaign state (informational only)", row.get("state", "")))
            if state == "archived" or not name:
                continue
            sd_campaigns.append({
                "campaign_name": name, "ad_type": "SD", "state": state,
                "budget": safe_float(row.get("budget")),
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
            })
        elif entity == "audience targeting":
            state = safe_str(row.get("state", ""))
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
    return {"sd_campaigns": sd_campaigns, "sd_targets": sd_targets}


def parse_all(file_path):
    """Parse all sheets (SP + SB + SD) and return combined dict."""
    output = parse_sp_sheet(file_path)
    output.update(parse_sb_sheet(file_path))
    output.update(parse_sd_sheet(file_path))
    return output
