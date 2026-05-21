# PPC Shared Parser Changelog

This file records parser behavior changes that affect downstream PPC logs and audit outputs.

## 2026-05-21 20:02 PKT

### Shared campaign metric reconciliation

- Extended campaign metric reconciliation so Amazon bulk-sheet Campaign rows are no longer blindly trusted when a lower-level metric layer is more reliable.
- The parser now aggregates non-archived Ad group rows by campaign and compares their sales/orders against lower-level targeting rows:
  - Sponsored Products: Keyword + Product targeting rows
  - Sponsored Brands: Keyword rows
  - Sponsored Display: Audience targeting rows
- If Campaign-row sales/orders materially differ while Ad group sales/orders reconcile with targeting-row sales/orders, the parser uses Ad group totals for campaign spend, sales, orders, clicks, impressions, CTR, CPC, conversion rate, and ACoS.
- If Campaign-row sales/orders are zero while Ad group rows contain conversions, the parser also uses Ad group totals.
- Reconciled rows are marked with `metric_source = "ad_group_reconciled"`; unreconciled rows keep `metric_source = "campaign"`.
- This fixes Amazon exports where Campaign/placement rows show stale or lower sales/orders while Ad group, target, and STR layers agree with each other.

### Shared consumers affected

- `ppc_shared.build_campaigns()` now exposes `metric_source` for the PPC logs upload flow.
- `ppc_shared.parse_all()` applies the same reconciliation for the PPC audit parser.

### Verification

- Ran synthetic bulk-sheet checks for Sponsored Products, Sponsored Brands, and Sponsored Display.
- Ran `python -m compileall ppc_shared`.
