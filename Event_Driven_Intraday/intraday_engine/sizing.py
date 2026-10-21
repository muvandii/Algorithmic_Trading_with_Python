"""Position sizing: turn a stop distance into a quantity.

Two production-grade methods are provided and are interchangeable because both
implement ``Sizer.size(...)``:

FixedFractionSizer
    Risk a constant fraction of *current equity* per trade:
    ``qty = equity * risk_pct / |entry - stop|``.
    Stops closer to price => bigger size. Simple, and the right default.

AtrSizer
    Same risk budget, but the stop distance comes from volatility:
    ``stop_distance = atr_mult * ATR(period)``.
    Size shrinks automatically in fast markets. When a structural stop is also
    supplied, the *larger* distance is used so the realised risk at the actual
    bracket can never exceed the budget.

Both respect ``max_leverage`` and round to ``lot_step`` so the backtest matches
what a real venue would accept. Sizing must be *causal*: use the ATR computed
from bars up to and including t (never t+1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

import numpy as np
import pandas as pd


class Sizer(Protocol):
    """Structural interface: anything with this method can size a trade."""

    def size(
        self,
        equity: float,
        entry_price: float,
        stop_price: Optional[float] = None,
        atr: Optional[float] = None,
        price: Optional[float] = None,
    ) -> float:
        """Return a non-negative quantity in units of the traded asset."""


@dataclass
class FixedFractionSizer:
    """Risk a fixed % of equity per trade, stop-distance sized.

    Parameters
    ----------
    risk_pct:
        Fraction of equity risked between entry and stop (0.01 = 1%).
    max_leverage:
        Cap on notional / equity (1.0 = no leverage).
    lot_step:
        Quantity increment (0.001 for many crypto pairs, 1 for shares).
    allow_fractional:
        If False, floor to whole units.
    """

    risk_pct: float = 0.01
    max_leverage: float = 1.0
    lot_step: float = 0.0
    allow_fractional: bool = True

    def size(
        self,
        equity: float,
        entry_price: float,
        stop_price: Optional[float] = None,
        atr: Optional[float] = None,
        price: Optional[float] = None,
    ) -> float:
        """Size = risk budget / stop distance, capped by leverage and lot step."""
        if equity <= 0 or entry_price <= 0:
            return 0.0
        if stop_price is None:
            raise ValueError("FixedFractionSizer needs a stop_price (risk must be defined up front)")
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            raise ValueError("entry and stop must differ")
        qty = (equity * self.risk_pct) / stop_distance
        qty = min(qty, (equity * self.max_leverage) / entry_price)
        return _round_qty(qty, self.lot_step, self.allow_fractional)


@dataclass
class AtrSizer:
    """Volatility sizing: stop distance = ``atr_mult * ATR(period)``.

    ``stop_price`` is optional. If supplied, sizing uses
    ``max(|entry - stop_price|, atr_mult * ATR)``: the quantity is based on the
    larger distance, so the loss realised at the real bracket is <= the risk
    budget. (Sizing on a tighter stop than the one actually used is a classic
    way to risk 2x what you intended.)
    """

    risk_pct: float = 0.01
    atr_mult: float = 1.5
    max_leverage: float = 1.0
    lot_step: float = 0.0
    allow_fractional: bool = True

    def size(
        self,
        equity: float,
        entry_price: float,
        stop_price: Optional[float] = None,
        atr: Optional[float] = None,
        price: Optional[float] = None,
    ) -> float:
        """Size from ATR-based risk; requires ``atr`` (from bars <= t)."""
        if atr is None or not np.isfinite(atr) or atr <= 0:
            raise ValueError("AtrSizer needs a positive ATR computed from past bars")
        atr_distance = self.atr_mult * float(atr)
        if stop_price is not None:
            structural = abs(entry_price - stop_price)
            stop_distance = max(structural, atr_distance)
        else:
            stop_distance = atr_distance
        if stop_distance <= 0:
            return 0.0
        qty = (equity * self.risk_pct) / stop_distance
        qty = min(qty, (equity * self.max_leverage) / entry_price)
        return _round_qty(qty, self.lot_step, self.allow_fractional)


def _round_qty(qty: float, lot_step: float, allow_fractional: bool) -> float:
    """Floor to the venue lot size (never round risk *up*)."""
    if qty <= 0:
        return 0.0
    if lot_step and lot_step > 0:
        return float(np.floor(qty / lot_step + 1e-9) * lot_step)
    return float(np.floor(qty)) if not allow_fractional else float(qty)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's Average True Range using only past data (causal).

    ``df`` must contain ``high, low, close``. Returns a Series aligned to
    ``df.index``; the first ``period`` values are NaN by construction.

    Complexity: O(n). Memory: O(n) for the intermediate True Range series.
    """
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    # Wilder smoothing == EWM with alpha = 1/period, adjust=False.
    return true_range.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
