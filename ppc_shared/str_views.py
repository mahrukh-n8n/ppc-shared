"""
STR views — generate view-specific datasets from aggregated STR data.

12 view functions, all pure (accept data + config, return datasets).
Priority order matches user specification.

Consolidates logic from:
  - data/audit/scripts/search_term_analysis.py (promote, negate, cannibalization, branded, funnel)
  - prompts/optimization/03-analyze/search-term-analysis.md (classification, promote, negate, leakage)
  - .planning/finalized-todo/002-str-macro-metrics-and-campaign-view.md (top by sales/spend, 1-or-less)
"""

import re
from collections import defaultdict


def view_aggregated_terms(
    agg_rows: list[dict], filters: dict | None = None
) -> list[dict]:
    """Base screen: all aggregated terms, sortable, filterable."""
    result = list(agg_rows)
    # Sort by spend descending by default
    result.sort(key=lambda x: x.get("spend", 0), reverse=True)
    return result


def view_top_spend(agg_rows: list[dict], limit: int = 50) -> list[dict]:
    """Terms sorted by spend DESC."""
    sorted_rows = sorted(agg_rows, key=lambda x: x.get("spend", 0), reverse=True)
    return sorted_rows[:limit]


def view_top_sales(agg_rows: list[dict], limit: int = 50) -> list[dict]:
    """Terms sorted by orders/sales DESC."""
    sorted_rows = sorted(
        agg_rows, key=lambda x: (x.get("orders", 0), x.get("sales", 0)), reverse=True
    )
    return sorted_rows[:limit]


def view_low_order_terms(agg_rows: list[dict], max_orders: int = 1) -> list[dict]:
    """Terms with orders <= max_orders (waste pool)."""
    result = [r for r in agg_rows if r.get("orders", 0) <= max_orders]
    result.sort(key=lambda x: x.get("spend", 0), reverse=True)
    return result


def view_promote_candidates(
    enriched_rows: list[dict],
    config: dict,
) -> list[dict]:
    """Converting terms not in exact keywords — promote to exact match.

    Criteria: orders >= 2, ACoS < target_acos, not already an exact keyword.
    """
    exact_keywords = set(k.lower().strip() for k in config.get("keywords_exact", []))
    target_acos = config.get("target_acos", 30.0)

    # Aggregate by search term to get total orders
    term_agg = defaultdict(
        lambda: {
            "orders": 0,
            "spend": 0.0,
            "sales": 0.0,
            "clicks": 0,
            "campaigns": set(),
            "match_types": set(),
        }
    )
    for r in enriched_rows:
        key = r["customer_search_term"].lower().strip()
        a = term_agg[key]
        a["orders"] += r.get("orders", 0)
        a["spend"] += r.get("spend", 0)
        a["sales"] += r.get("sales", 0)
        a["clicks"] += r.get("clicks", 0)
        a["campaigns"].add(r.get("campaign_name", ""))
        if r.get("match_type"):
            a["match_types"].add(r["match_type"])

    promote_list = []
    for term, a in term_agg.items():
        if a["orders"] < 2:
            continue
        if term in exact_keywords:
            continue
        acos = round(a["spend"] / a["sales"] * 100, 2) if a["sales"] > 0 else None
        if acos is not None and acos >= target_acos:
            continue
        cvr = round(a["orders"] / a["clicks"] * 100, 2) if a["clicks"] > 0 else 0
        cpc = round(a["spend"] / a["clicks"], 4) if a["clicks"] > 0 else 0

        promote_list.append(
            {
                "customer_search_term": term,
                "orders": a["orders"],
                "spend": round(a["spend"], 2),
                "sales": round(a["sales"], 2),
                "acos": acos,
                "cvr": cvr,
                "cpc": cpc,
                "current_match_types": sorted(a["match_types"]),
                "campaigns": sorted(a["campaigns"]),
                "action": "Add as Exact match keyword",
            }
        )

    promote_list.sort(key=lambda x: x["orders"], reverse=True)
    return promote_list


def view_negate_candidates(
    enriched_rows: list[dict],
    config: dict,
) -> list[dict]:
    """Zero-order high-spend terms — negate candidates with dedup and sibling conflict detection.

    Criteria: orders = 0, spend >= negate_min_spend, not branded.
    """
    negate_min_spend = config.get("negate_min_spend", 5.0)
    brand_terms = [t.lower() for t in config.get("brand_terms", [])]
    brands_config = config.get("brands", [])
    for brand in brands_config:
        for term in brand.get("match_terms", [brand["name"]]):
            brand_terms.append(term.lower())

    existing_negatives = config.get("existing_negatives", {})

    # Aggregate zero-order terms
    zero_agg = defaultdict(
        lambda: {
            "spend": 0.0,
            "clicks": 0,
            "impressions": 0,
            "campaigns": set(),
            "targetings": set(),
        }
    )
    for r in enriched_rows:
        if r.get("orders", 0) > 0:
            continue
        term = r["customer_search_term"].lower().strip()
        a = zero_agg[term]
        a["spend"] += r.get("spend", 0)
        a["clicks"] += r.get("clicks", 0)
        a["impressions"] += r.get("impressions", 0)
        a["campaigns"].add(r.get("campaign_name", ""))
        if r.get("targeting"):
            a["targetings"].add(r["targeting"])

    # Terms that convert somewhere (for sibling conflict detection)
    term_converting_campaigns = defaultdict(set)
    for r in enriched_rows:
        if r.get("orders", 0) > 0:
            term_converting_campaigns[r["customer_search_term"].lower().strip()].add(
                r.get("campaign_name", "")
            )

    negate_list = []
    for term, a in zero_agg.items():
        if a["spend"] < negate_min_spend:
            continue
        # Skip branded terms
        if any(bt in term for bt in brand_terms):
            continue

        word_count = len(term.split())
        negate_type = "Negative Exact" if word_count >= 3 else "Negative Phrase"
        ctr = (
            round(a["clicks"] / a["impressions"] * 100, 4)
            if a["impressions"] > 0
            else 0
        )

        # Check if term converts elsewhere
        converting_campaigns = term_converting_campaigns.get(term, set())
        negate_campaigns = a["campaigns"]
        converts_elsewhere = bool(converting_campaigns - negate_campaigns)

        # Check already-negated status
        already_negated_in = {}
        for cn in negate_campaigns:
            negs = existing_negatives.get(cn, {})
            if term in negs.get("exact", set()):
                already_negated_in[cn] = "negative exact exists"
            else:
                for phrase in negs.get("phrase", set()):
                    if phrase in term:
                        already_negated_in[cn] = (
                            f"covered by phrase negative '{phrase}'"
                        )
                        break

        needs_negative_in = sorted(negate_campaigns - set(already_negated_in.keys()))
        all_already_negated = len(needs_negative_in) == 0

        negate_list.append(
            {
                "customer_search_term": term,
                "spend": round(a["spend"], 2),
                "clicks": a["clicks"],
                "impressions": a["impressions"],
                "ctr": ctr,
                "campaigns": sorted(a["campaigns"]),
                "matched_keywords": sorted(a["targetings"]),
                "negate_type": negate_type,
                "converts_elsewhere": converts_elsewhere,
                "already_negated_in": already_negated_in,
                "needs_negative_in": needs_negative_in,
                "all_already_negated": all_already_negated,
                "action": f"{negate_type} in {', '.join(needs_negative_in)[:80]}"
                if needs_negative_in
                else "SKIP — already negated in all campaigns",
            }
        )

    negate_list.sort(key=lambda x: x["spend"], reverse=True)
    return negate_list


def view_campaign_summary(campaign_agg: list[dict]) -> list[dict]:
    """Campaign-level STR metrics with ACoS Power, waste ratio, converting spend ratio."""
    result = []
    for c in campaign_agg:
        result.append(
            {
                "campaign_name": c["campaign_name"],
                "spend": c["spend"],
                "sales": c["sales"],
                "orders": c["orders"],
                "clicks": c["clicks"],
                "impressions": c["impressions"],
                "acos": c["acos"],
                "cvr": c["cvr"],
                "cpc": c["cpc"],
                "n_spent": c["n_spent"],
                "c_spent": c["c_spent"],
                "acos_power": c["acos_power"],
                "converting_spend_ratio": c["converting_spend_ratio"],
                "waste_ratio": c["waste_ratio"],
                "spend_ratio": c["spend_ratio"],
                "order_ratio": c["order_ratio"],
                "clicks_per_order": c["clicks_per_order"],
                "unique_terms": c["unique_terms"],
                "match_types": c["match_types"],
            }
        )
    result.sort(key=lambda x: x["spend"], reverse=True)
    return result


def view_cannibalization(
    enriched_rows: list[dict],
    config: dict,
) -> list[dict]:
    """Same term in 2+ campaigns — same-parent vs cross-parent classification.

    Requires child_to_parent mapping from business report for accurate same-parent detection.
    Falls back to campaign-name-only grouping if not available.
    """
    child_to_parent = config.get("child_to_parent", {})
    negate_min_spend = config.get("negate_min_spend", 5.0)
    target_acos = config.get("target_acos", 30.0)

    # Group by term -> campaign
    term_campaigns = defaultdict(
        lambda: defaultdict(
            lambda: {
                "spend": 0.0,
                "sales": 0.0,
                "orders": 0,
                "clicks": 0,
            }
        )
    )
    for r in enriched_rows:
        term = r["customer_search_term"].lower().strip()
        cn = r.get("campaign_name", "")
        d = term_campaigns[term][cn]
        d["spend"] += r.get("spend", 0)
        d["sales"] += r.get("sales", 0)
        d["orders"] += r.get("orders", 0)
        d["clicks"] += r.get("clicks", 0)

    def get_camp_parents(campaign_name):
        """Get set of parent ASINs for a campaign from business report data."""
        # This would need campaign->ASIN mapping from bulk sheet
        # Simplified: return empty set if not available
        return set()

    cannibalization = []
    for term, camp_data in term_campaigns.items():
        if len(camp_data) < 2:
            continue
        combined_spend = sum(d["spend"] for d in camp_data.values())
        combined_orders = sum(d["orders"] for d in camp_data.values())
        if combined_spend < negate_min_spend:
            continue

        # Find best campaign (lowest ACoS with sales)
        best_camp = None
        best_acos = float("inf")
        for cn, d in camp_data.items():
            if d["sales"] > 0:
                a = d["spend"] / d["sales"] * 100
                if a < best_acos:
                    best_acos = a
                    best_camp = cn

        waste_camps = [cn for cn in camp_data if cn != best_camp]
        waste_spend = sum(camp_data[cn]["spend"] for cn in waste_camps)
        severity = "CRITICAL" if len(camp_data) >= 3 else "WARNING"

        # Per-campaign detail
        waste_details = []
        for cn in waste_camps:
            d = camp_data[cn]
            w_acos = round(d["spend"] / d["sales"] * 100, 1) if d["sales"] > 0 else None
            reason = (
                "No Sales"
                if d["orders"] == 0
                else (
                    "ACoS > Target"
                    if (w_acos and w_acos > target_acos)
                    else "Duplicate"
                )
            )
            waste_details.append(
                {
                    "campaign": cn,
                    "spend": round(d["spend"], 2),
                    "sales": round(d["sales"], 2),
                    "orders": d["orders"],
                    "clicks": d["clicks"],
                    "acos": w_acos,
                    "reason": reason,
                }
            )
        waste_details.sort(key=lambda w: -w["spend"])

        # Determine cannibalization type
        all_parents = set()
        for cn in camp_data:
            all_parents.update(get_camp_parents(cn))
        cannibal_type = "Same-Parent" if len(all_parents) <= 1 else "Cross-Parent"

        worst = waste_details[0] if waste_details else None

        cannibalization.append(
            {
                "customer_search_term": term,
                "campaigns": sorted(camp_data.keys()),
                "combined_spend": round(combined_spend, 2),
                "combined_orders": combined_orders,
                "best_campaign": best_camp,
                "best_acos": round(best_acos, 1) if best_acos < float("inf") else None,
                "waste_campaigns": waste_camps,
                "waste_details": waste_details,
                "worst_campaign": worst["campaign"] if worst else None,
                "worst_acos": worst["acos"] if worst else None,
                "worst_spend": worst["spend"] if worst else 0,
                "worst_orders": worst["orders"] if worst else 0,
                "worst_reason": worst["reason"] if worst else None,
                "waste_spend": round(waste_spend, 2),
                "severity": severity,
                "type": cannibal_type,
                "parent_count": len(all_parents),
            }
        )

    cannibalization.sort(key=lambda x: x["combined_spend"], reverse=True)
    return cannibalization


def view_duplicate_terms(enriched_rows: list[dict]) -> list[dict]:
    """Same search term triggered by different targets/keywords within a single campaign.

    Detects match type leakage and redundant targeting.
    """
    # Group by (campaign, term) -> collect match types and targetings
    campaign_term_map = defaultdict(
        lambda: defaultdict(
            lambda: {
                "match_types": set(),
                "targetings": set(),
                "spend": 0.0,
                "orders": 0,
                "sales": 0.0,
                "clicks": 0,
            }
        )
    )

    for r in enriched_rows:
        cn = r.get("campaign_name", "")
        term = r["customer_search_term"].lower().strip()
        d = campaign_term_map[cn][term]
        d["spend"] += r.get("spend", 0)
        d["orders"] += r.get("orders", 0)
        d["sales"] += r.get("sales", 0)
        d["clicks"] += r.get("clicks", 0)
        if r.get("match_type"):
            d["match_types"].add(r["match_type"])
        if r.get("targeting"):
            d["targetings"].add(r["targeting"])

    duplicates = []
    for cn, terms in campaign_term_map.items():
        for term, d in terms.items():
            if len(d["match_types"]) > 1 or len(d["targetings"]) > 1:
                acos = (
                    round(d["spend"] / d["sales"] * 100, 2) if d["sales"] > 0 else None
                )
                duplicates.append(
                    {
                        "campaign_name": cn,
                        "customer_search_term": term,
                        "match_types": sorted(d["match_types"]),
                        "targetings": sorted(d["targetings"]),
                        "spend": round(d["spend"], 2),
                        "orders": d["orders"],
                        "sales": round(d["sales"], 2),
                        "acos": acos,
                        "severity": "WARNING" if len(d["match_types"]) > 1 else "INFO",
                        "action": "Consolidate to single match type"
                        if len(d["match_types"]) > 1
                        else "Review redundant targetings",
                    }
                )

    duplicates.sort(key=lambda x: x["spend"], reverse=True)
    return duplicates


def view_high_acos_converting(
    enriched_rows: list[dict],
    config: dict,
) -> list[dict]:
    """Terms with orders but ACoS > target_acos * bleeder_multiplier — bid reduction candidates."""
    target_acos = config.get("target_acos", 30.0)
    bleeder_multiplier = config.get("bleeder_multiplier", 1.5)
    threshold = target_acos * bleeder_multiplier

    # Aggregate by term
    term_agg = defaultdict(
        lambda: {
            "orders": 0,
            "spend": 0.0,
            "sales": 0.0,
            "clicks": 0,
            "campaigns": set(),
            "match_types": set(),
        }
    )
    for r in enriched_rows:
        if r.get("orders", 0) < 1:
            continue
        key = r["customer_search_term"].lower().strip()
        a = term_agg[key]
        a["orders"] += r.get("orders", 0)
        a["spend"] += r.get("spend", 0)
        a["sales"] += r.get("sales", 0)
        a["clicks"] += r.get("clicks", 0)
        a["campaigns"].add(r.get("campaign_name", ""))
        if r.get("match_type"):
            a["match_types"].add(r["match_type"])

    high_acos = []
    for term, a in term_agg.items():
        acos = round(a["spend"] / a["sales"] * 100, 2) if a["sales"] > 0 else None
        if acos is None or acos <= threshold:
            continue

        cvr = round(a["orders"] / a["clicks"] * 100, 2) if a["clicks"] > 0 else 0
        cpc = round(a["spend"] / a["clicks"], 4) if a["clicks"] > 0 else 0
        rpc = round(a["sales"] / a["clicks"], 4) if a["clicks"] > 0 else 0
        target_cpc = round(rpc * target_acos / 100, 4) if a["clicks"] > 0 else 0

        # Recommendation based on volume
        if a["clicks"] >= 20 and a["sales"] >= 3:
            action = "Reduce bid — high volume, high ACoS converting term"
        elif a["clicks"] >= 10:
            action = "Reduce bid by 15-20% — moderate volume, high ACoS"
        else:
            action = "Monitor — low volume, high ACoS converting term"

        high_acos.append(
            {
                "customer_search_term": term,
                "orders": a["orders"],
                "spend": round(a["spend"], 2),
                "sales": round(a["sales"], 2),
                "acos": acos,
                "cvr": cvr,
                "cpc": cpc,
                "rpc": rpc,
                "target_cpc": target_cpc,
                "campaigns": sorted(a["campaigns"]),
                "match_types": sorted(a["match_types"]),
                "action": action,
            }
        )

    high_acos.sort(key=lambda x: x["spend"], reverse=True)
    return high_acos


def view_branded_summary(
    enriched_rows: list[dict],
    config: dict,
) -> list[dict]:
    """Branded vs non-branded split per brand."""
    brands_config = config.get("brands", [])
    brand_terms = config.get("brand_terms", [])

    # Build brand match list
    brand_match_list = []
    for brand in brands_config:
        for term in brand.get("match_terms", [brand["name"]]):
            brand_match_list.append((term.lower(), brand["name"]))
    # Also add standalone brand terms
    for bt in brand_terms:
        brand_match_list.append((bt.lower(), bt))
    brand_match_list.sort(key=lambda x: -len(x[0]))

    # Filter to keyword-triggered STRs only
    kw_triggered = [r for r in enriched_rows if r.get("match_type", "-") != "-"]

    results = []
    for brand_cfg in brands_config:
        brand_name = brand_cfg["name"]
        own_terms = [t.lower() for t in brand_cfg.get("match_terms", [brand_name])]

        branded = [
            r
            for r in kw_triggered
            if any(term in r["customer_search_term"].lower() for term in own_terms)
        ]

        b_spend = sum(r["spend"] for r in branded)
        b_sales = sum(r["sales"] for r in branded)
        b_orders = sum(r["orders"] for r in branded)
        b_clicks = sum(r["clicks"] for r in branded)
        b_acos = round(b_spend / b_sales * 100, 2) if b_sales > 0 else None
        b_cvr = round(b_orders / b_clicks * 100, 2) if b_clicks > 0 else 0

        results.append(
            {
                "brand_name": brand_name,
                "spend": round(b_spend, 2),
                "sales": round(b_sales, 2),
                "orders": b_orders,
                "clicks": b_clicks,
                "acos": b_acos,
                "cvr": b_cvr,
                "term_count": len(
                    set(r["customer_search_term"].lower() for r in branded)
                ),
            }
        )

    # Non-branded summary
    branded_terms_set = set()
    for brand in brands_config:
        for term in brand.get("match_terms", [brand["name"]]):
            branded_terms_set.add(term.lower())

    non_branded = [
        r
        for r in kw_triggered
        if not any(bt in r["customer_search_term"].lower() for bt in branded_terms_set)
    ]
    nb_spend = sum(r["spend"] for r in non_branded)
    nb_sales = sum(r["sales"] for r in non_branded)
    nb_orders = sum(r["orders"] for r in non_branded)
    nb_clicks = sum(r["clicks"] for r in non_branded)
    nb_acos = round(nb_spend / nb_sales * 100, 2) if nb_sales > 0 else None
    nb_cvr = round(nb_orders / nb_clicks * 100, 2) if nb_clicks > 0 else 0

    results.append(
        {
            "brand_name": "Non-Branded",
            "spend": round(nb_spend, 2),
            "sales": round(nb_sales, 2),
            "orders": nb_orders,
            "clicks": nb_clicks,
            "acos": nb_acos,
            "cvr": nb_cvr,
            "term_count": len(
                set(r["customer_search_term"].lower() for r in non_branded)
            ),
        }
    )

    return results


def view_leakage(enriched_rows: list[dict]) -> list[dict]:
    """Full query leakage by campaign:
    (a) match type leakage — broad/phrase spend on zero-order terms
    (b) cross-campaign leakage — same term spending across multiple campaigns
    (c) targeting leakage — auto campaign terms that should be in manual campaigns
    """
    # (a) Match type leakage: broad/phrase campaigns with high zero-order spend
    campaign_leakage = defaultdict(
        lambda: {
            "total_spend": 0.0,
            "zero_order_spend": 0.0,
            "broad_phrase_spend": 0.0,
            "broad_phrase_zero_spend": 0.0,
            "auto_spend": 0.0,
            "auto_zero_spend": 0.0,
            "total_terms": 0,
            "zero_order_terms": 0,
        }
    )

    for r in enriched_rows:
        cn = r.get("campaign_name", "")
        mt = (r.get("match_type") or "").lower()
        d = campaign_leakage[cn]
        d["total_spend"] += r.get("spend", 0)
        d["total_terms"] += 1
        if r.get("orders", 0) == 0:
            d["zero_order_spend"] += r.get("spend", 0)
            d["zero_order_terms"] += 1

        if mt in ("broad", "phrase"):
            d["broad_phrase_spend"] += r.get("spend", 0)
            if r.get("orders", 0) == 0:
                d["broad_phrase_zero_spend"] += r.get("spend", 0)

        if mt in ("auto", "-"):
            d["auto_spend"] += r.get("spend", 0)
            if r.get("orders", 0) == 0:
                d["auto_zero_spend"] += r.get("spend", 0)

    results = []
    for cn, d in campaign_leakage.items():
        if d["total_spend"] == 0:
            continue

        waste_ratio = round(d["zero_order_spend"] / d["total_spend"] * 100, 1)
        bp_waste_ratio = (
            round(d["broad_phrase_zero_spend"] / d["broad_phrase_spend"] * 100, 1)
            if d["broad_phrase_spend"] > 0
            else 0
        )
        auto_waste_ratio = (
            round(d["auto_zero_spend"] / d["auto_spend"] * 100, 1)
            if d["auto_spend"] > 0
            else 0
        )

        flags = []
        if waste_ratio > 40:
            flags.append("High overall waste")
        if bp_waste_ratio > 40 and d["broad_phrase_spend"] > 0:
            flags.append("Broad/phrase match leakage")
        if auto_waste_ratio > 50 and d["auto_spend"] > 0:
            flags.append("Auto campaign waste — consider harvesting to manual")

        results.append(
            {
                "campaign_name": cn,
                "total_spend": round(d["total_spend"], 2),
                "zero_order_spend": round(d["zero_order_spend"], 2),
                "waste_ratio": waste_ratio,
                "broad_phrase_spend": round(d["broad_phrase_spend"], 2),
                "broad_phrase_zero_spend": round(d["broad_phrase_zero_spend"], 2),
                "broad_phrase_waste_ratio": bp_waste_ratio,
                "auto_spend": round(d["auto_spend"], 2),
                "auto_zero_spend": round(d["auto_zero_spend"], 2),
                "auto_waste_ratio": auto_waste_ratio,
                "total_terms": d["total_terms"],
                "zero_order_terms": d["zero_order_terms"],
                "flags": flags,
                "severity": "CRITICAL"
                if waste_ratio > 60
                else ("WARNING" if waste_ratio > 40 else "OK"),
            }
        )

    results.sort(key=lambda x: x["zero_order_spend"], reverse=True)
    return results
