"""Max bid calculation logic."""


def calc_max_bid(base, pct, strategy, multiplier):
    """Calculate max effective bid based on bidding strategy.

    TOS: 2x multiplier for up-and-down
    ROS/PP: 1.5x multiplier for up-and-down
    AB: 2x multiplier for up-and-down
    All: 1x (just base + placement %) for other strategies
    """
    if base is None or base == 0:
        return None
    pct = pct or 0
    adjusted = base * (1 + pct / 100)
    if "up and down" in (strategy or "").lower():
        adjusted *= multiplier
    return round(adjusted, 2)


def max_bid_text(base, pct, strategy, multiplier):
    """Return combined text like '$1.09 - 30%' or None."""
    pct = pct or 0
    val = calc_max_bid(base, pct, strategy, multiplier)
    if val is None:
        return None
    pct_val = int(pct) if pct == int(pct) else pct
    return f"${val:.2f} - {pct_val}%"
