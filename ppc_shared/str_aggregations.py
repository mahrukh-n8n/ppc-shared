"""
STR aggregations — pure functions for grouping, filtering, and merging STR rows.

All functions preserve n_spent/c_spent split for ACoS Power calculation.
No DB logic — accepts rows, returns aggregated datasets.
"""

from collections import defaultdict


def aggregate_by_term(rows: list[dict]) -> list[dict]:
    """Group rows by customer_search_term, sum metrics, collect campaigns/match_types."""
    agg = defaultdict(
        lambda: {
            "impressions": 0,
            "clicks": 0,
            "spend": 0.0,
            "orders": 0,
            "sales": 0.0,
            "n_spent": 0.0,
            "c_spent": 0.0,
            "campaigns": set(),
            "match_types": set(),
            "targetings": set(),
            "row_count": 0,
        }
    )

    for r in rows:
        key = r["customer_search_term"].lower().strip()
        a = agg[key]
        a["impressions"] += r.get("impressions", 0)
        a["clicks"] += r.get("clicks", 0)
        a["spend"] += r.get("spend", 0)
        a["orders"] += r.get("orders", 0)
        a["sales"] += r.get("sales", 0)
        a["n_spent"] += r.get("n_spent", 0)
        a["c_spent"] += r.get("c_spent", 0)
        a["campaigns"].add(r.get("campaign_name", ""))
        if r.get("match_type"):
            a["match_types"].add(r["match_type"])
        if r.get("targeting"):
            a["targetings"].add(r["targeting"])
        a["row_count"] += 1

    results = []
    for term, a in agg.items():
        spend = a["spend"]
        sales = a["sales"]
        clicks = a["clicks"]
        orders = a["orders"]

        acos = round(spend / sales * 100, 2) if sales > 0 else None
        cvr = round(orders / clicks * 100, 2) if clicks > 0 else 0
        cpc = round(spend / clicks, 4) if clicks > 0 else 0
        ctr = round(clicks / a["impressions"] * 100, 4) if a["impressions"] > 0 else 0

        n_spent = a["n_spent"]
        c_spent = a["c_spent"]
        c_spent_acos = (c_spent / sales * 100) if c_spent > 0 and sales > 0 else None
        acos_power = None
        if acos is not None and c_spent_acos is not None and c_spent_acos > 0:
            acos_power = round(acos / c_spent_acos, 4)

        rpc = round(sales / clicks, 4) if clicks > 0 else 0
        target_cpc = (
            round(rpc * acos / 100, 4) if clicks > 0 and acos is not None else 0
        )
        cpa = round(spend / orders, 2) if orders > 0 else None

        converting_spend_ratio = round(n_spent / spend, 4) if spend > 0 else 0
        waste_ratio = round(c_spent / spend, 4) if spend > 0 else 0

        is_branded = any(
            r.get("is_branded", False)
            for r in rows
            if r["customer_search_term"].lower().strip() == term
        )
        is_converting = orders >= 1

        results.append(
            {
                "customer_search_term": term,
                "impressions": a["impressions"],
                "clicks": clicks,
                "spend": round(spend, 4),
                "orders": orders,
                "sales": round(sales, 4),
                "acos": acos,
                "cvr": cvr,
                "cpc": cpc,
                "ctr": ctr,
                "n_spent": round(n_spent, 4),
                "c_spent": round(c_spent, 4),
                "rpc": rpc,
                "target_cpc": target_cpc,
                "cpa": cpa,
                "acos_power": acos_power,
                "converting_spend_ratio": converting_spend_ratio,
                "waste_ratio": waste_ratio,
                "is_branded": is_branded,
                "is_converting": is_converting,
                "campaigns": sorted(a["campaigns"]),
                "match_types": sorted(a["match_types"]),
                "targetings": sorted(a["targetings"]),
                "row_count": a["row_count"],
            }
        )

    return results


def aggregate_by_campaign(rows: list[dict]) -> list[dict]:
    """Group rows by campaign_name, sum metrics, compute n_spent/c_spent ratios."""
    agg = defaultdict(
        lambda: {
            "impressions": 0,
            "clicks": 0,
            "spend": 0.0,
            "orders": 0,
            "sales": 0.0,
            "n_spent": 0.0,
            "c_spent": 0.0,
            "unique_terms": set(),
            "match_types": set(),
        }
    )

    for r in rows:
        cn = r.get("campaign_name", "Unknown")
        a = agg[cn]
        a["impressions"] += r.get("impressions", 0)
        a["clicks"] += r.get("clicks", 0)
        a["spend"] += r.get("spend", 0)
        a["orders"] += r.get("orders", 0)
        a["sales"] += r.get("sales", 0)
        a["n_spent"] += r.get("n_spent", 0)
        a["c_spent"] += r.get("c_spent", 0)
        a["unique_terms"].add(r.get("customer_search_term", "").lower())
        if r.get("match_type"):
            a["match_types"].add(r["match_type"])

    total_spend = sum(a["spend"] for a in agg.values())
    total_orders = sum(a["orders"] for a in agg.values())

    results = []
    for cn, a in agg.items():
        spend = a["spend"]
        sales = a["sales"]
        clicks = a["clicks"]
        orders = a["orders"]
        n_spent = a["n_spent"]
        c_spent = a["c_spent"]

        acos = round(spend / sales * 100, 2) if sales > 0 else None
        cvr = round(orders / clicks * 100, 2) if clicks > 0 else 0
        cpc = round(spend / clicks, 4) if clicks > 0 else 0
        ctr = round(clicks / a["impressions"] * 100, 4) if a["impressions"] > 0 else 0

        c_spent_acos = (c_spent / sales * 100) if c_spent > 0 and sales > 0 else None
        acos_power = None
        if acos is not None and c_spent_acos is not None and c_spent_acos > 0:
            acos_power = round(acos / c_spent_acos, 4)

        rpc = round(sales / clicks, 4) if clicks > 0 else 0
        cpa = round(spend / orders, 2) if orders > 0 else None

        spend_ratio = round(spend / total_spend, 4) if total_spend > 0 else 0
        order_ratio = round(orders / total_orders, 4) if total_orders > 0 else 0
        clicks_per_order = round(clicks / orders, 2) if orders > 0 else None

        results.append(
            {
                "campaign_name": cn,
                "impressions": a["impressions"],
                "clicks": clicks,
                "spend": round(spend, 4),
                "orders": orders,
                "sales": round(sales, 4),
                "acos": acos,
                "cvr": cvr,
                "cpc": cpc,
                "ctr": ctr,
                "n_spent": round(n_spent, 4),
                "c_spent": round(c_spent, 4),
                "rpc": rpc,
                "cpa": cpa,
                "acos_power": acos_power,
                "converting_spend_ratio": round(n_spent / spend, 4) if spend > 0 else 0,
                "waste_ratio": round(c_spent / spend, 4) if spend > 0 else 0,
                "spend_ratio": spend_ratio,
                "order_ratio": order_ratio,
                "clicks_per_order": clicks_per_order,
                "unique_terms": len(a["unique_terms"]),
                "match_types": sorted(a["match_types"]),
            }
        )

    return results


def aggregate_by_portfolio(rows: list[dict]) -> dict:
    """Total rollup of all rows."""
    total_spend = sum(r.get("spend", 0) for r in rows)
    total_sales = sum(r.get("sales", 0) for r in rows)
    total_orders = sum(r.get("orders", 0) for r in rows)
    total_clicks = sum(r.get("clicks", 0) for r in rows)
    total_impressions = sum(r.get("impressions", 0) for r in rows)
    total_n_spent = sum(r.get("n_spent", 0) for r in rows)
    total_c_spent = sum(r.get("c_spent", 0) for r in rows)

    acos = round(total_spend / total_sales * 100, 2) if total_sales > 0 else None
    cvr = round(total_orders / total_clicks * 100, 2) if total_clicks > 0 else 0
    cpc = round(total_spend / total_clicks, 4) if total_clicks > 0 else 0
    ctr = (
        round(total_clicks / total_impressions * 100, 4) if total_impressions > 0 else 0
    )
    cpa = round(total_spend / total_orders, 2) if total_orders > 0 else None

    return {
        "impressions": total_impressions,
        "clicks": total_clicks,
        "spend": round(total_spend, 2),
        "orders": total_orders,
        "sales": round(total_sales, 2),
        "acos": acos,
        "cvr": cvr,
        "cpc": cpc,
        "ctr": ctr,
        "cpa": cpa,
        "n_spent": round(total_n_spent, 2),
        "c_spent": round(total_c_spent, 2),
        "converting_spend_ratio": round(total_n_spent / total_spend, 4)
        if total_spend > 0
        else 0,
        "waste_ratio": round(total_c_spent / total_spend, 4) if total_spend > 0 else 0,
        "unique_terms": len(set(r["customer_search_term"].lower() for r in rows)),
        "unique_campaigns": len(set(r.get("campaign_name", "") for r in rows)),
        "row_count": len(rows),
    }


def apply_filters(rows: list[dict], filters: dict) -> list[dict]:
    """Filter rows by any combination of criteria."""
    result = rows

    if filters.get("campaigns"):
        campaigns = set(c.lower() for c in filters["campaigns"])
        result = [r for r in result if r.get("campaign_name", "").lower() in campaigns]

    if filters.get("ad_group"):
        ag = filters["ad_group"].lower()
        result = [r for r in result if (r.get("ad_group_name") or "").lower() == ag]

    if filters.get("targeting"):
        t = filters["targeting"].lower()
        result = [r for r in result if (r.get("targeting") or "").lower() == t]

    if filters.get("match_type"):
        mt = set(m.lower() for m in filters["match_type"])
        result = [r for r in result if (r.get("match_type") or "").lower() in mt]

    if filters.get("branded") == "branded":
        result = [r for r in result if r.get("is_branded", False)]
    elif filters.get("branded") == "non-branded":
        result = [r for r in result if not r.get("is_branded", False)]

    if filters.get("search_term"):
        st = filters["search_term"].lower()
        result = [r for r in result if st in r.get("customer_search_term", "").lower()]

    if filters.get("order_bucket"):
        bucket = filters["order_bucket"]
        if bucket == "0":
            result = [r for r in result if r.get("orders", 0) == 0]
        elif bucket == "1":
            result = [r for r in result if r.get("orders", 0) == 1]
        elif bucket == "2-4":
            result = [r for r in result if 2 <= r.get("orders", 0) <= 4]
        elif bucket == "5+":
            result = [r for r in result if r.get("orders", 0) >= 5]

    if filters.get("min_spend") is not None:
        result = [r for r in result if r.get("spend", 0) >= filters["min_spend"]]

    if filters.get("max_spend") is not None:
        result = [r for r in result if r.get("spend", 0) <= filters["max_spend"]]

    return result


def merge_periods(period_data_list: list[list[dict]]) -> list[dict]:
    """Merge rows from multiple periods. Simple concatenation — aggregation happens downstream."""
    merged = []
    for data in period_data_list:
        merged.extend(data)
    return merged
