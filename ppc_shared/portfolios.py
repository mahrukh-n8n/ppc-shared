"""Portfolio name extraction from bulk sheets."""
from ppc_shared.parsers import parse_sheet


def extract_portfolio_names(file_path):
    """Extract unique portfolio names from all sheet tabs in a bulk file."""
    sheet_names = [
        "Sponsored Products Campaigns",
        "Sponsored Display Campaigns",
        "Sponsored Brands Campaigns",
    ]
    portfolios = set()
    for sheet in sheet_names:
        df = parse_sheet(file_path, sheet)
        if df is None:
            continue
        col = None
        for c in ["portfolio name (informational only)", "portfolio name",
                  "Portfolio name", "Portfolio Name"]:
            if c in df.columns:
                col = c
                break
        if not col:
            continue
        for val in df[col].dropna().unique():
            name = str(val).strip()
            if name and name != "-":
                portfolios.add(name)
    return sorted(portfolios)
