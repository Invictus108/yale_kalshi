"""LMSR (Logarithmic Market Scoring Rule) helpers for binary markets."""

from __future__ import annotations

import math


def _soft_cost(q_yes: float, q_no: float, b: float) -> float:
    # Numerically stable LMSR cost: b * log(exp(qy/b) + exp(qn/b))
    my = q_yes / b
    mn = q_no / b
    m = max(my, mn)
    return b * (m + math.log(math.exp(my - m) + math.exp(mn - m)))


def lmsr_price_yes(q_yes: float, q_no: float, b: float) -> float:
    my = q_yes / b
    mn = q_no / b
    m = max(my, mn)
    ey = math.exp(my - m)
    en = math.exp(mn - m)
    return ey / (ey + en)


def trade_cost(
    q_yes: float,
    q_no: float,
    b: float,
    side: str,
    action: str,
    shares: float,
) -> tuple[float, float, float]:
    """
    Return (cost, new_q_yes, new_q_no).

    cost > 0 means trader pays the market.
    cost < 0 means trader receives from the market (sell).
    """
    if not all(math.isfinite(v) for v in (shares, q_yes, q_no, b)):
        raise ValueError("trade values must be finite")
    if b <= 0 or shares <= 0:
        raise ValueError("shares and liquidity must be positive")
    side = side.upper()
    action = action.upper()
    if side not in {"YES", "NO"} or action not in {"BUY", "SELL"}:
        raise ValueError("invalid side/action")
    if action == "BUY" and shares > 1_000_000:
        raise ValueError("buy at most 1,000,000 shares per trade")

    delta = shares if action == "BUY" else -shares
    new_yes = q_yes + (delta if side == "YES" else 0.0)
    new_no = q_no + (delta if side == "NO" else 0.0)
    if new_yes < -1e-9 or new_no < -1e-9:
        raise ValueError("cannot sell more shares than the market maker holds path allows")

    before = _soft_cost(q_yes, q_no, b)
    after = _soft_cost(new_yes, new_no, b)
    cost = after - before
    return cost, new_yes, new_no


def avg_price(cost: float, shares: float) -> float:
    if shares == 0:
        return 0.0
    return abs(cost) / shares
