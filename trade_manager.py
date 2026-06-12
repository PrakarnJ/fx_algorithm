from config import SharedParams


def update_sl(
    direction: str,
    entry: float,
    current_sl: float,
    atr_val: float,
    current_price: float,
    shared: SharedParams,
    partial_done: bool = False,
) -> float:
    """
    Apply break-even and ATR trailing logic.
    Returns the new SL (unchanged if no update needed).
    Stateless — caller tracks the SL.

    After partial TP fills (partial_done=True), trails tighter at
    shared.trail_after_partial_atr_mult instead of trail_atr_mult.
    """
    if atr_val == 0:
        return current_sl

    be_trigger = shared.breakeven_atr_mult * atr_val
    trail_dist  = (
        shared.trail_after_partial_atr_mult * atr_val
        if partial_done
        else shared.trail_atr_mult * atr_val
    )
    new_sl = current_sl

    if direction == "buy":
        profit = current_price - entry
        if profit >= be_trigger and new_sl < entry:
            new_sl = entry + atr_val * 0.1
        if new_sl >= entry:
            trail_sl = current_price - trail_dist
            if trail_sl > new_sl:
                new_sl = trail_sl
    else:  # sell
        profit = entry - current_price
        if profit >= be_trigger and new_sl > entry:
            new_sl = entry - atr_val * 0.1
        if new_sl <= entry:
            trail_sl = current_price + trail_dist
            if trail_sl < new_sl:
                new_sl = trail_sl

    return new_sl
