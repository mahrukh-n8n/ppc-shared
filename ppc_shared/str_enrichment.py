"""
STR enrichment — classify rows and calculate macro-derived metrics.

Tags each row (brand, ranking_kw, converting, non_converting, exact_match_already,
appears_in_multiple_campaigns, high_acos) and calculates macro-derived metrics
at row level FIRST (n_spent, c_spent, rpc, target_cpc, cpa, etc.).

Consolidates logic from:
  - data/audit/scripts/parse_str.py (waste_flag, promote_candidate)
  - data/audit/scripts/search_term_analysis.py (brand detection, already-negated)
  - prompts/optimization/01-parse/search-term-report.md (classification tags)
  - .planning/finalized-todo/002-str-macro-metrics-and-campaign-view.md (macro formulas)
"""

from collections import defaultdict


def enrich_rows(
    rows: list[dict],
    config: dict,
) -> dict:
    """Enrich parsed STR rows with classification flags and macro-derived metrics.

    Args:
        rows: List of normalized row dicts from str_parser.parse_str()
        config: {
            "brand_terms": ["jason mark", "jm", ...],
            "target_acos": 30.0,
            "bleeder_multiplier": 1.5,
            "min_clicks_to_negate": 10,
            "ranking_keywords": ["rank", "position", ...],
            "existing_negatives": {  # optional — from parsed_bulk.json
                "campaign_name": {"exact": set(), "phrase": set()},
            },
            "keywords_exact": set(),  # optional — existing exact keywords
            "brands": [  # optional — from Brand model
                {"name": "Jason Mark", "match_terms": ["jason mark", "jm"]},
            ],
        }

    Returns:
        {
            "rows": [...],  # enriched rows with all flags and metrics
            "summary": {
                "total_rows": int,
                "unique_terms": int,
                "converting_count": int,
                "non_converting_count": int,
                "branded_count": int,
                "multi_campaign_count": int,
                "high_acos_count": int,
                "total_spend": float,
                "total_sales": float,
                "total_orders": int,
                "total_clicks": int,
                "overall_acos": float | None,
                "total_n_spent": float,
                "total_c_spent": float,
                "converting_spend_ratio": float,
                "waste_ratio": float,
            },
        }
    """
    brand_terms = config.get("brand_terms", [])
    brands_config = config.get("brands", [])
    target_acos = config.get("target_acos", 30.0)
    bleeder_multiplier = config.get("bleeder_multiplier", 1.5)
    min_clicks = config.get("min_clicks_to_negate", 10)
    ranking_keywords = config.get("ranking_keywords", [])

    # Build brand match list from both sources
    all_brand_terms = set(t.lower() for t in brand_terms)
    for brand in brands_config:
        for term in brand.get("match_terms", [brand["name"]]):
            all_brand_terms.add(term.lower())

    # Detect multi-campaign terms
    term_campaigns = defaultdict(set)
    for row in rows:
        term_campaigns[row["customer_search_term"].lower()].add(row["campaign_name"])

    # Enrich each row
    enriched = []
    for row in rows:
        term = row["customer_search_term"]
        term_lower = term.lower()

        # --- Classification flags ---
        is_branded = any(bt in term_lower for bt in all_brand_terms)
        is_ranking_kw = any(rk.lower() in term_lower for rk in ranking_keywords)
        is_converting = row["orders"] >= 1
        is_non_converting = row["clicks"] >= min_clicks and row["orders"] == 0
        is_exact_match_already = (
            term_lower == (row.get("targeting") or "").lower().strip()
            and (row.get("match_type") or "").lower() == "exact"
        )
        appears_in_multiple = len(term_campaigns[term_lower]) > 1
        is_high_acos = (
            row["orders"] >= 1
            and row.get("acos") is not None
            and row["acos"] > target_acos * bleeder_multiplier
        )

        # --- Macro-derived metrics (row level FIRST) ---
        spend = row["spend"]
        orders = row["orders"]
        sales = row["sales"]
        clicks = row["clicks"]

        c_spent = spend if orders > 0 else 0.0  # converting spend
        n_spent = spend if orders == 0 else 0.0  # non-converting spend

        rpc = round(sales / clicks, 4) if clicks > 0 else 0.0
        target_cpc = round(rpc * target_acos / 100, 4) if clicks > 0 else 0.0
        cpa = round(spend / orders, 2) if orders > 0 else None

        converting_spend_ratio = round(c_spent / spend, 4) if spend > 0 else 0.0
        waste_ratio = round(n_spent / spend, 4) if spend > 0 else 0.0

        # ACoS Power = acos / (c_spent / sales * 100) — divide by converting spend acos
        c_spent_acos = (c_spent / sales * 100) if c_spent > 0 and sales > 0 else None
        acos_power = None
        if (
            row.get("acos") is not None
            and c_spent_acos is not None
            and c_spent_acos > 0
        ):
            acos_power = round(row["acos"] / c_spent_acos, 4)

        enriched_row = {
            **row,
            # Flags
            "is_branded": is_branded,
            "is_ranking_kw": is_ranking_kw,
            "is_converting": is_converting,
            "is_non_converting": is_non_converting,
            "is_exact_match_already": is_exact_match_already,
            "appears_in_multiple_campaigns": appears_in_multiple,
            "is_high_acos": is_high_acos,
            # Macro-derived metrics
            "n_spent": round(n_spent, 4),
            "c_spent": round(c_spent, 4),
            "rpc": rpc,
            "target_cpc": target_cpc,
            "cpa": cpa,
            "converting_spend_ratio": converting_spend_ratio,
            "waste_ratio": waste_ratio,
            "acos_power": acos_power,
        }
        enriched.append(enriched_row)

    # --- Summary ---
    total_spend = sum(r["spend"] for r in enriched)
    total_sales = sum(r["sales"] for r in enriched)
    total_orders = sum(r["orders"] for r in enriched)
    total_clicks = sum(r["clicks"] for r in enriched)
    total_n_spent = sum(r["n_spent"] for r in enriched)
    total_c_spent = sum(r["c_spent"] for r in enriched)

    overall_acos = (
        round(total_spend / total_sales * 100, 2) if total_sales > 0 else None
    )
    converting_spend_ratio = (
        round(total_n_spent / total_spend, 4) if total_spend > 0 else 0.0
    )
    waste_ratio = round(total_c_spent / total_spend, 4) if total_spend > 0 else 0.0

    unique_terms = len(set(r["customer_search_term"].lower() for r in enriched))

    summary = {
        "total_rows": len(enriched),
        "unique_terms": unique_terms,
        "converting_count": sum(1 for r in enriched if r["is_converting"]),
        "non_converting_count": sum(1 for r in enriched if r["is_non_converting"]),
        "branded_count": sum(1 for r in enriched if r["is_branded"]),
        "multi_campaign_count": sum(
            1 for r in enriched if r["appears_in_multiple_campaigns"]
        ),
        "high_acos_count": sum(1 for r in enriched if r["is_high_acos"]),
        "total_spend": round(total_spend, 2),
        "total_sales": round(total_sales, 2),
        "total_orders": total_orders,
        "total_clicks": total_clicks,
        "overall_acos": overall_acos,
        "total_n_spent": round(total_n_spent, 2),
        "total_c_spent": round(total_c_spent, 2),
        "converting_spend_ratio": converting_spend_ratio,
        "waste_ratio": waste_ratio,
    }

    return {"rows": enriched, "summary": summary}
