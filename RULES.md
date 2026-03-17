# ppc-shared — Rules & Contracts

**Read this before changing anything in this package.**

This package is the single source of truth for PPC data processing. Two consumers depend on it:
- `ppc optimization` — CLI scripts, JSON logs, Excel reports
- `ppc logs app` — Next.js web app, PostgreSQL, API

Breaking a contract here breaks both.

---

## 1. Output Contract

### Field Names: Always snake_case
- Internal field names are **always snake_case**: `campaign_name`, `acos_all`, `total_spend`
- **Never** use camelCase in this package
- Consumers map to their own format:
  - Optimization: uses snake_case as-is
  - App: maps to camelCase (`campaignName`, `acosAll`) in its own wrapper

### Return Types: Raw values, never formatted
- Numbers stay as numbers: `0.1862` not `"18.6%"`, `34.99` not `"$34.99"`
- The only exception: `max_bid_text()` returns `"$1.09 - 30%"` (both consumers use this format)
- Formatting helpers exist (`format_tos_is_text()`) but are opt-in, never called internally

### Price: Return what the data gives
- Single price → `float` (e.g., `34.99`)
- Multiple distinct prices → `string` range (e.g., `"$29.99-$39.99"`)
- No sales data → `None`
- Consumers decide how to handle: app takes lowest, optimization shows range

### TOS IS%: Decimal internally
- Stored as decimal: `0.1862` = 18.62%
- `<5%` from dashboard → stored as `0.05`
- Use `format_tos_is_text()` only at the display layer (never in builder)

### Nullability
- Any metric field can be `None` — consumers must handle this
- `None` means "no data available", not zero
- Zero means zero (campaign ran but got no clicks/orders)

---

## 2. Function Contracts

### `build_campaigns()` — The Core Function
```python
campaigns, summary, camp_asins, asin_price, br_totals = build_campaigns(
    bulk_path, portfolio, days, dashboard_path, br_path
)
```
- Returns **5 values** — never change the count or order
- `campaigns`: list of dicts, one per campaign, snake_case keys
- `summary`: dict with aggregate metrics, snake_case keys
- Adding new fields to campaigns/summary: **OK** (additive)
- Removing or renaming existing fields: **NEVER** — breaks both consumers
- Changing a field's type (e.g., float → string): **NEVER**

### `apply_ranking_data()` — Configurable Keys
```python
apply_ranking_data(campaigns, ranking_path, bulk_path, portfolio, marketplace,
                   campaign_name_key="campaign_name",
                   org_rank_key="org_rank", sp_rank_key="sp_rank")
```
- Modifies campaigns **in-place**
- Key names are configurable so the app can pass camelCase keys
- Default keys are snake_case (for optimization consumer)

### `read_dashboard_tos()` — Returns Raw Map
- Returns `{campaign_name: decimal_value}`
- Matching (exact + substring) is done by `match_tos_is()`, not here
- Caller decides how to format the value

### `read_business_report()` — Returns 4 Values
```python
asin_price, camp_asins, br_totals, br_rows = read_business_report(br_path, bulk_path, portfolio)
```
- `br_rows` is the raw parsed data — consumers may need it for custom aggregation
- Never change the return count

---

## 3. What You CAN Do

- **Add new fields** to campaign dicts or summary — both consumers ignore unknown keys
- **Add new functions** — no impact on existing consumers
- **Add new optional parameters** with defaults — existing calls still work
- **Fix bugs** in calculation logic — both consumers benefit
- **Add new file format support** (e.g., TSV) in parsers — additive

## 4. What You CANNOT Do

- **Rename fields** — breaks both consumers' field mappings
- **Remove fields** — breaks consumers that read them
- **Change field types** — `float` → `string` or `None` → `0` breaks validation
- **Change return value count** — `build_campaigns()` returns 5, keep it 5
- **Change parameter order** — add new params at the end with defaults
- **Change `safe_float` behavior** — both consumers depend on identical parsing
- **Add required parameters** — existing callers would break
- **Import consumer-specific code** — this package must not know about logs_maker or process_upload

## 5. What You MUST Test After Changes

```bash
# Quick smoke test — run from any directory
python -c "
from ppc_shared import build_campaigns, extract_portfolio_names, detect_date_range, safe_float

# Test safe_float edge cases
assert safe_float(None) == 0.0
assert safe_float('12.5%') == 12.5
assert safe_float('<5%') == 5.0
assert safe_float('\$1,234.56') == 1234.56
assert safe_float('12,5') == 12.5

print('All assertions passed')
"
```

Then test both consumers:
```bash
# Optimization
cd "ppc optimization"
python data/optimization/scripts/logs_maker.py --bulk <bulk.xlsx> --portfolio list

# App
cd "ppc logs app"
python scripts/process_upload.py --batch-id <test-batch> --token <token>
```

---

## 6. Adding a New Metric

Example: adding `impressions_all` to campaign output.

1. Add to `builder.py` → `_build_log()`:
   ```python
   "impressions_all": c.get("impressions_all"),  # NEW — add at end
   ```

2. Add extraction in `extraction.py` → `extract_campaigns()`:
   ```python
   "impressions_all": safe_float(row.get("impressions")),  # NEW
   ```

3. **Do NOT** touch `logs_maker.py` or `process_upload.py` here — they handle new fields in their own wrappers

4. Update this RULES.md if the new field has special semantics

---

## 7. Consumer Responsibilities

### logs_maker.py (optimization)
- Maps shared output → LOG_COLUMNS for Excel
- Adds: data_period, remarks, total_row formatting, JSON logs, Excel output
- Converts TOS IS% decimal → text via `format_tos_is_text()`

### process_upload.py (app)
- Maps shared output → camelCase for API POST
- Adds: API auth, batch fetch, error reporting, portfolio extraction CLI
- Stores TOS IS% as decimal directly (DB field is float)
- Takes `prices[0]` (lowest) instead of range string for single DB field

### audit scripts (parse_bulk_sheet.py wrapper)
- Imports `parse_all`, `parse_sp_sheet`, `parse_sb_sheet`, `parse_sd_sheet` from shared
- Keeps backward-compatible function aliases
- Used by 15+ audit analysis scripts — never break the output shape

---

## 8. Version Discipline

When making changes:
1. Read this file first
2. Check if the change is additive (safe) or breaking (forbidden)
3. Test the smoke test above
4. Test both consumers
5. If adding a field, document it here if it has special semantics
