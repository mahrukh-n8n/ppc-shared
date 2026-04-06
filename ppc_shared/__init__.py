"""
ppc-shared — Core PPC parsing and campaign extraction logic.

Used by both:
  - ppc optimization (CLI logs_maker.py + audit scripts)
  - ppc logs app (API process_upload.py)
"""
from ppc_shared.utils import safe_float, safe_str, get_campaign_name, get_portfolio_name
from ppc_shared.parsers import parse_sheet, parse_sp_sheet, parse_sb_sheet, parse_sd_sheet, parse_all
from ppc_shared.detection import (
    detect_date_range, detect_marketplace_from_columns, CURRENCY_TO_MARKETPLACE,
)
from ppc_shared.extraction import (
    extract_campaigns, extract_placement_data, extract_base_bids,
    extract_campaign_asins,
)
from ppc_shared.bids import calc_max_bid, max_bid_text
from ppc_shared.dashboard import read_dashboard_tos, match_tos_is, format_tos_is_text
from ppc_shared.business_report import read_business_report, get_campaign_price
from ppc_shared.ranking import apply_ranking_data
from ppc_shared.builder import build_campaigns
from ppc_shared.portfolios import extract_portfolio_names
