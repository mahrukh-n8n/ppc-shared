"""Date range and marketplace auto-detection."""
import os
import re
from datetime import datetime

CURRENCY_TO_MARKETPLACE = {
    "usd": "amazon.com", "cad": "amazon.ca", "gbp": "amazon.co.uk",
    "mxn": "amazon.com.mx", "brl": "amazon.com.br", "aud": "amazon.com.au",
    "jpy": "amazon.co.jp", "inr": "amazon.in", "sgd": "amazon.sg",
    "aed": "amazon.ae", "sar": "amazon.sa", "eur": "amazon.de",
}


def detect_marketplace_from_columns(df):
    """Auto-detect marketplace from currency in column names like 'Budget(CAD)'."""
    for col in df.columns:
        m = re.search(r"\(([A-Z]{3})\)", col, re.IGNORECASE)
        if m:
            currency = m.group(1).lower()
            mp = CURRENCY_TO_MARKETPLACE.get(currency)
            if mp:
                return mp
    return None


def detect_date_range(filename):
    """Extract date range from bulk filename like 'bulk-...-20260309-20260316-...xlsx'.
    Returns (start_date, end_date, days, label) or (None, None, None, None).
    """
    m = re.search(r"(\d{8})-(\d{8})", os.path.basename(filename))
    if not m:
        return None, None, None, None
    d1 = datetime.strptime(m.group(1), "%Y%m%d")
    d2 = datetime.strptime(m.group(2), "%Y%m%d")
    days = (d2 - d1).days
    label = f"{d1.strftime('%d%b')}-{d2.strftime('%d%b%y')}"
    return d1, d2, days, label
