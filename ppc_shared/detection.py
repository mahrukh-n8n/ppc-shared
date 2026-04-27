"""Date range and marketplace auto-detection."""
import os
import re
from datetime import datetime

CURRENCY_TO_MARKETPLACE = {
    "usd": "amazon.com", "cad": "amazon.ca", "gbp": "amazon.co.uk",
    "mxn": "amazon.com.mx", "brl": "amazon.com.br", "aud": "amazon.com.au",
    "jpy": "amazon.co.jp", "inr": "amazon.in", "sgd": "amazon.sg",
    "aed": "amazon.ae", "sar": "amazon.sa",
    "eur": "amazon.de",  # EUR default; use detect_marketplace_from_columns for DE/FR/IT/ES/NL/BE disambiguation
}


def detect_marketplace_from_columns(df):
    """Auto-detect marketplace from currency in column names like 'Budget(CAD)'.
    For EUR marketplaces, disambiguates using filename marketplace suffix."""
    for col in df.columns:
        m = re.search(r"\(([A-Z]{3})\)", col, re.IGNORECASE)
        if m:
            currency = m.group(1).lower()
            mp = CURRENCY_TO_MARKETPLACE.get(currency)
            if mp:
                return mp
    return None


# Filename patterns used to disambiguate EUR marketplaces
_FILENAME_MARKETPLACE = {
    "de": "amazon.de", "fr": "amazon.fr", "it": "amazon.it",
    "es": "amazon.es", "nl": "amazon.nl", "be": "amazon.com.be",
    "uk": "amazon.co.uk", "com": "amazon.com", "ca": "amazon.ca",
    "mx": "amazon.com.mx", "br": "amazon.com.br", "au": "amazon.com.au",
    "jp": "amazon.co.jp", "in": "amazon.in", "sg": "amazon.sg",
    "ae": "amazon.ae", "sa": "amazon.sa",
}


def detect_marketplace_from_filename(filename):
    """Disambiguate marketplace from bulk filename suffix (e.g. 'DE', 'FR')."""
    base = os.path.basename(filename).lower()
    # Match marketplace codes in filenames like: bulk-...-DE-... or _de_
    for code, marketplace in _FILENAME_MARKETPLACE.items():
        if f"-{code}-" in base or f"_{code}_" in base or base.endswith(f"-{code}"):
            return marketplace
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
