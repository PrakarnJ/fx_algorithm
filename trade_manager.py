from config import SharedParams


def update_sl(
    direction: str,
    entry: float,
    current_sl: float,
    atr_val: float,
    current_price: float,
    shared: SharedParams,
    partial_done: bool = False,
    breakeven_mult: float = None,
    trail_mult: float = None,
    tp: float = None,
) -> float:
    """
    Apply break-even and ATR trailing logic.
    Returns the new SL (unchanged if no update needed).
    Stateless — caller tracks the SL.

    tp: if provided, uses the "stepped SL" mechanic instead of ATR trailing:
        - At 25% of TP distance from entry → move SL to break-even
        - At 50% of TP distance from entry → move SL to +25% of TP locked
    breakeven_mult / trail_mult override SharedParams when provided
    (used to wire strategy-specific trail params, e.g. TrendBreakoutParams).
    After partial TP fills (partial_done=True), trails tighter at
    shared.trail_after_partial_atr_mult instead of trail_atr_mult.
    """
    # Stepped SL ("zero risk") — replaces ATR trailing entirely
    if tp is not None:
        tp_dist = abs(tp - entry)
        if tp_dist == 0:
            return current_sl
        profit = (current_price - entry) if direction == "buy" else (entry - current_price)
        pct = max(0.0, profit / tp_dist)
        if pct >= 0.50:
            floor = (entry + 0.25 * tp_dist) if direction == "buy" else (entry - 0.25 * tp_dist)
        elif pct >= 0.25:
            floor = entry
        else:
            return current_sl
        return max(current_sl, floor) if direction == "buy" else min(current_sl, floor)

    if atr_val == 0:
        return current_sl

    be_trigger = (breakeven_mult if breakeven_mult is not None else shared.breakeven_atr_mult) * atr_val
    trail_dist  = (
        shared.trail_after_partial_atr_mult * atr_val
        if partial_done
        else (trail_mult if trail_mult is not None else shared.trail_atr_mult) * atr_val
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
