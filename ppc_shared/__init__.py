"""
ppc-shared — Core PPC parsing and campaign extraction logic.

Used by both:
  - ppc optimization (CLI logs_maker.py + audit scripts)
  - ppc logs app (API process_upload.py)
"""

from ppc_shared.utils import safe_float, safe_str, get_campaign_name, get_portfolio_name
from ppc_shared.parsers import (
    parse_sheet,
    parse_sp_sheet,
    parse_sb_sheet,
    parse_sd_sheet,
    parse_all,
)
from ppc_shared.detection import (
    detect_date_range,
    detect_marketplace_from_columns,
    CURRENCY_TO_MARKETPLACE,
)
from ppc_shared.extraction import (
    extract_campaigns,
    extract_placement_data,
    extract_base_bids,
    extract_campaign_asins,
)
from ppc_shared.bids import calc_max_bid, max_bid_text
from ppc_shared.dashboard import read_dashboard_tos, match_tos_is, format_tos_is_text
from ppc_shared.business_report import read_business_report, get_campaign_price
from ppc_shared.ranking import apply_ranking_data
from ppc_shared.builder import build_campaigns
from ppc_shared.portfolios import extract_portfolio_names
from ppc_shared.str_parser import parse_str
from ppc_shared.str_enrichment import enrich_rows
from ppc_shared.str_aggregations import (
    aggregate_by_term,
    aggregate_by_campaign,
    aggregate_by_portfolio,
    apply_filters,
    merge_periods,
)
from ppc_shared.str_views import (
    view_aggregated_terms,
    view_top_spend,
    view_top_sales,
    view_low_order_terms,
    view_promote_candidates,
    view_negate_candidates,
    view_campaign_summary,
    view_cannibalization,
    view_duplicate_terms,
    view_high_acos_converting,
    view_branded_summary,
    view_leakage,
)
from ppc_shared.str_actions import (
    to_optimization_output,
    to_audit_output,
    to_app_json,
    to_excel_sheets,
)
