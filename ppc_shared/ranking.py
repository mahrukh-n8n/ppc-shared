"""Ranking CSV integration — match keywords + ASINs to rank data."""
import csv
import os

from ppc_shared.utils import safe_str, get_portfolio_name
from ppc_shared.parsers import parse_sheet


def apply_ranking_data(campaigns, ranking_path, bulk_path, portfolio, marketplace,
                       campaign_name_key="campaignName",
                       org_rank_key="orgRank", sp_rank_key="spRank"):
    """Match ranking CSV data to campaigns and populate rank fields.

    Args:
        campaigns: list of campaign dicts to update in-place
        ranking_path: path to ranking CSV
        bulk_path: path to bulk sheet (for keyword/ASIN extraction)
        portfolio: portfolio name filter
        marketplace: marketplace to filter ranking rows
        campaign_name_key: key used for campaign name in campaign dicts
        org_rank_key: key to write organic rank into
        sp_rank_key: key to write sponsored rank into
    """
    if not ranking_path or not os.path.exists(ranking_path):
        return

    with open(ranking_path, encoding="utf-8-sig") as f:
        rank_rows = list(csv.DictReader(f))
    if not rank_rows:
        print("WARNING: Ranking file is empty")
        return

    # Filter by marketplace
    if marketplace:
        mp_lower = marketplace.lower()
        rank_rows = [r for r in rank_rows if r.get("Marketplace", "").lower() == mp_lower]
        if not rank_rows:
            print(f"WARNING: No ranking rows match marketplace '{marketplace}'")
            return

    # Build lookup: (keyword_lower, asin) → {organic, sponsored, found}
    has_split_ranks = "Organic Rank" in rank_rows[0]
    rank_lookup = {}
    for r in rank_rows:
        kw = r.get("Keyword", "").lower().strip()
        asin = r.get("ASIN", "").strip()
        found = r.get("Found", "").strip().lower() == "true"
        if not kw or not asin:
            continue
        if has_split_ranks:
            org_rank = r.get("Organic Rank", "N/A").strip()
            sp_rank = r.get("Sponsored Rank", "N/A").strip()
        else:
            rank_val = r.get("Rank", "N/A").strip()
            org_rank = rank_val
            sp_rank = "N/A"

        key = (kw, asin)
        if key not in rank_lookup or found:
            rank_lookup[key] = {
                "organic": org_rank if org_rank != "N/A" else None,
                "sponsored": sp_rank if sp_rank != "N/A" else None,
                "found": found,
            }

    # Build campaign → keywords and campaign → ASINs from bulk
    sp_df = parse_sheet(bulk_path, "Sponsored Products Campaigns")
    if sp_df is None:
        return

    camp_keywords = {}
    camp_asins_map = {}
    for _, row in sp_df.iterrows():
        entity = safe_str(row.get("entity", "")).lower()
        camp = safe_str(row.get("campaign name (informational only)",
                                 row.get("campaign name", "")))
        if not camp:
            continue
        if portfolio and portfolio != "-":
            port = get_portfolio_name(row)
            if port.lower() != portfolio.lower():
                continue
        if entity == "keyword" and safe_str(row.get("state", "")).lower() == "enabled":
            kw_text = safe_str(row.get("keyword text", "")).lower()
            if kw_text:
                camp_keywords.setdefault(camp, []).append(kw_text)
        elif entity == "product ad" and safe_str(row.get("state", "")).lower() != "archived":
            asin = safe_str(row.get("asin (informational only)", ""))
            if asin:
                camp_asins_map.setdefault(camp, set()).add(asin)

    # Match
    matched = 0
    for c in campaigns:
        name = c[campaign_name_key]
        keywords = camp_keywords.get(name, [])
        asins = camp_asins_map.get(name, set())
        if not keywords or not asins:
            continue

        best_org, best_sp = None, None
        for kw in keywords:
            for asin in asins:
                r = rank_lookup.get((kw, asin))
                if not r or not r["found"]:
                    continue
                try:
                    org = int(r["organic"]) if r["organic"] else None
                except (ValueError, TypeError):
                    org = None
                try:
                    sp = int(r["sponsored"]) if r["sponsored"] else None
                except (ValueError, TypeError):
                    sp = None
                if org is not None and (best_org is None or org < best_org):
                    best_org = org
                if sp is not None and (best_sp is None or sp < best_sp):
                    best_sp = sp

        if best_org is not None or best_sp is not None:
            c[org_rank_key] = best_org
            c[sp_rank_key] = best_sp
            matched += 1

    print(f"Ranking: matched {matched}/{len(campaigns)} campaigns")
