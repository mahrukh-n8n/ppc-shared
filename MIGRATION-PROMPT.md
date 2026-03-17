# Migration Prompt — ppc logs app → ppc-shared

Feed this to the AI working on the ppc logs app project:

---

## Task

Refactor `scripts/process_upload.py` to use the shared `ppc-shared` package instead of its own duplicated parsing logic.

### Setup

The shared package is installed at `C:\Users\Glorvax\Documents\ppc-shared` via `pip install -e`. It exports everything from `ppc_shared`:

```python
from ppc_shared import (
    build_campaigns, apply_ranking_data, detect_date_range,
    detect_marketplace_from_columns, extract_portfolio_names,
    safe_float, safe_str, parse_sheet, format_tos_is_text,
)
```

Read `C:\Users\Glorvax\Documents\ppc-shared\RULES.md` before making any changes.

### What to Do

1. **Delete all duplicated code** from `process_upload.py`:
   - `safe_float`, `safe_str`, `get_campaign_name`, `get_portfolio_name`
   - `parse_sheet`, `extract_campaigns`, `extract_placement_data`, `extract_base_bids`
   - `calc_max_bid`, `max_bid_text`
   - `read_dashboard_tos`, `read_business_report`, `apply_ranking_data`
   - `build_campaigns`, `extract_portfolio_names`
   - `CURRENCY_TO_MARKETPLACE`, `detect_marketplace_from_columns`, `detect_date_range`

2. **Import from ppc_shared** instead. Call `build_campaigns()` which returns:
   ```python
   campaigns, summary, camp_asins, asin_price, br_totals = build_campaigns(
       bulk_path, portfolio, days, dashboard_path, br_path
   )
   ```

3. **Keep only the thin wrapper** in `process_upload.py`:
   - API auth (`fetch_batch_files`, `post_result`, `report_failure`)
   - CLI argument parsing
   - The `_process_batch()` orchestration
   - camelCase field mapping before POST

### Field Mapping (snake_case → camelCase)

The shared package returns snake_case. Map to camelCase for the API:

```python
def to_api_campaign(c):
    return {
        "campaignName": c["campaign_name"],
        "adType": c["ad_type"],
        "price": c["price"] if isinstance(c["price"], (int, float)) else None,
        # If price is a range string like "$29.99-$39.99", store lowest:
        # prices[0] from the range, or the float directly
        "tosIsPct": c["tos_is_pct"],  # already decimal from shared
        "acosAll": c["acos_all"],
        "acosTos": c["acos_tos"],
        "acosRos": c["acos_ros"],
        "acosPp": c["acos_pp"],
        "acosAb": c["acos_ab"],
        "crAll": c["cr_all"],
        "crTos": c["cr_tos"],
        "crRos": c["cr_ros"],
        "crPp": c["cr_pp"],
        "crAb": c["cr_ab"],
        "cpcAll": c["cpc_all"],
        "cpcTos": c["cpc_tos"],
        "cpcRos": c["cpc_ros"],
        "cpcPp": c["cpc_pp"],
        "cpcAb": c["cpc_ab"],
        "ctrAll": c["ctr_all"],
        "ctrTos": c["ctr_tos"],
        "ctrRos": c["ctr_ros"],
        "ctrPp": c["ctr_pp"],
        "ctrAb": c["ctr_ab"],
        "baseBid": f"${c['base_bid']:.2f}" if c["base_bid"] else None,
        "maxTos": c["max_tos"],
        "maxRos": c["max_ros"],
        "maxPp": c["max_pp"],
        "maxAb": c["max_ab"],
        "totalSpend": c["total_spend"],
        "dailySpend": c["daily_spend"],
        "budget": c["budget"],
        "ppcRevenue": c["ppc_revenue"],
        "ordersAll": int(c["orders_all"]) if c["orders_all"] else None,
        "ordersTos": int(c["orders_tos"]) if c["orders_tos"] else None,
        "ordersRos": int(c["orders_ros"]) if c["orders_ros"] else None,
        "ordersPp": int(c["orders_pp"]) if c["orders_pp"] else None,
        "ordersAb": int(c["orders_ab"]) if c["orders_ab"] else None,
        "clicksAll": int(c["clicks_all"]) if c["clicks_all"] else None,
        "clicksTos": int(c["clicks_tos"]) if c["clicks_tos"] else None,
        "clicksRos": int(c["clicks_ros"]) if c["clicks_ros"] else None,
        "clicksPp": int(c["clicks_pp"]) if c["clicks_pp"] else None,
        "clicksAb": int(c["clicks_ab"]) if c["clicks_ab"] else None,
        "biddingStrategy": c["bidding_strategy"],
        "cpa": c["cpa"],
        "spendRatio": c["spend_ratio"],
        "orderRatio": c["order_ratio"],
        "recommendedBudget": c["recommended_budget"],
        "spRank": c["sp_rank"],
        "orgRank": c["org_rank"],
    }
```

### Ranking Integration

Use configurable keys since the shared function modifies campaigns in-place:

```python
# After build_campaigns, before mapping to camelCase:
apply_ranking_data(campaigns, ranking_path, bulk_path, portfolio, marketplace,
                   campaign_name_key="campaign_name",
                   org_rank_key="org_rank", sp_rank_key="sp_rank")
```

### Summary Row — MUST Include These Fields

The `summary` dict from `build_campaigns()` contains these. Map to camelCase and POST as the `summary` field in the API payload. The `PeriodSummary` model must store all of these:

| Shared Key | API Key | What | Example |
|---|---|---|---|
| `tacos` | `tacos` | TACoS as decimal (spend/BR revenue) | `0.068` |
| `br_revenue` | `brRevenue` | Business report total revenue for portfolio ASINs | `4850.00` |
| `br_orders` | `brOrders` | BR total orders for portfolio ASINs | `105` |
| `organic_orders` | `organicOrders` | BR orders minus PPC orders | `92` |
| `daily_orders` | `dailyOrders` | PPC orders / days | `1.86` |
| `total_spend` | `totalSpend` | Sum of all campaign spend | `331.62` |
| `daily_spend` | `dailySpend` | total_spend / days | `47.37` |
| `budget` | `budget` | Sum of all campaign budgets | `135.00` |
| `ppc_revenue` | `ppcRevenue` | Sum of all campaign PPC sales | `459.92` |
| `cpa` | `cpa` | total_spend / total_orders | `25.51` |
| `acos_all` | `acosAll` | total_spend / ppc_revenue as decimal | `0.721` |
| `orders_all` | `ordersAll` | Total PPC orders | `13` |

### Remarks Field

Add a `remarks` field to `PeriodSummary`. The optimization Excel shows this in the total row as:

```
TACoS 6.8% | BR Rev $4,850
```

Build it from summary data:

```python
def build_summary_remarks(summary):
    parts = []
    if summary.get("tacos") is not None:
        parts.append(f"TACoS {summary['tacos'] * 100:.1f}%")
    if summary.get("br_revenue"):
        parts.append(f"BR Rev ${summary['br_revenue']:,.0f}")
    return " | ".join(parts) if parts else None
```

Store this in `PeriodSummary.remarks`. Display it in the total/summary row of the logs grid.

### Price Handling

The shared package returns:
- `float` for single price (e.g., `34.99`)
- `string` for range (e.g., `"$29.99-$39.99"`)

The DB `price` field is `Decimal?`. For range strings, extract the lowest price:

```python
price = c["price"]
if isinstance(price, str) and price.startswith("$"):
    # Range like "$29.99-$39.99" → take lowest
    price = float(price.split("-")[0].replace("$", ""))
```

### TOS IS% Handling

Already decimal from shared (`0.1862`). Store directly in DB. Display in grid as percentage (`18.6%`).

### DB Schema Updates Needed

Add to `PeriodSummary` if missing:
- `remarks String?`
- `brRevenue Decimal?`
- `brOrders Int?`
- `organicOrders Int?`
- `dailyOrders Decimal?`
- `dailySpend Decimal?`
- `ppcRevenue Decimal?`
- `cpa Decimal?`
- `acosAll Decimal?`

### What NOT to Do

- Do NOT modify the shared package
- Do NOT add camelCase fields to `ppc_shared`
- Do NOT change the return signature of `build_campaigns()`
- Read `RULES.md` in the shared package before touching anything
