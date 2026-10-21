"""Pure, causal market-structure functions (Lesson 3 building blocks).

Every function here takes a DataFrame of bars **whose last row is t** and
returns information about patterns that are *confirmed at t*. They never
look at t+1, never mutate their input, and are trivially unit-testable.

Definitions used consistently across the module and the notebooks
-----------------------------------------------------------------
swing high at k : high[k] == max(high[k-left : k+right+1])
                  -> only *confirmed* at bar k+right, i.e. with ``right`` bars
                  of hindsight. That is why ``confirmed_index`` is returned.
break of structure (BOS): close[t] > the most recent confirmed swing high,
                  after price traded below it at some point (a genuine break,
                  not a re-test of the same high every bar).
liquidity sweep : wick[t] > swing_high AND close[t] < swing_high (for buyside
                  liquidity): the stop run happened but did not hold.
fair value gap (FVG): 3-bar imbalance. Bullish when low[t] > high[t-2]
                  (a gap between bar t-2's high and bar t's low). It becomes
                  tradable info only at the close of t; the *mitigation* zone is
                  [high[t-2], low[t]].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class Swing:
    """A confirmed pivot extreme."""

    index: int  # position of the extreme in the input frame
    confirmed_index: int  # bar at which it became knowable (index + right)
    timestamp: pd.Timestamp
    price: float
    kind: str  # 'high' | 'low'


@dataclass(frozen=True)
class Fvg:
    """A 3-bar imbalance, defined by the bar that completes it."""

    index: int  # bar t that completes the pattern
    timestamp: pd.Timestamp
    direction: str  # 'bullish' | 'bearish'
    lower: float
    upper: float
    mitigated_index: Optional[int] = None  # first later bar that trades into it

    @property
    def midpoint(self) -> float:
        """50% of the gap (a common limit-entry level, "consequent encroachment")."""
        return (self.lower + self.upper) / 2.0

    @property
    def size(self) -> float:
        """Gap height in price units."""
        return self.upper - self.lower


def swing_points(df: pd.DataFrame, left: int = 2, right: int = 2) -> list[Swing]:
    """Return pivots confirmed by ``right`` bars on both sides.

    ``df`` must end at the bar you are allowed to see, and must already contain
    ``left + right + 1`` rows. A swing at position k is only returned if
    ``k + right <= len(df) - 1`` -- i.e. it is confirmed by the last row.

    Complexity O(n * (left+right)); for a rolling window of 50 bars this is free.
    """
    if left < 1 or right < 1:
        raise ValueError("left and right must be >= 1")
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    out: list[Swing] = []
    for k in range(left, n - right):
        window_h = highs[k - left : k + right + 1]
        window_l = lows[k - left : k + right + 1]
        if highs[k] == window_h.max():
            out.append(Swing(k, k + right, df.index[k], float(highs[k]), "high"))
        if lows[k] == window_l.min():
            out.append(Swing(k, k + right, df.index[k], float(lows[k]), "low"))
    return out


def last_swing(df: pd.DataFrame, kind: str = "high", left: int = 2, right: int = 2) -> Optional[Swing]:
    """Most recent *confirmed* swing of ``kind`` ('high' or 'low')."""
    swings = [s for s in swing_points(df, left, right) if s.kind == kind]
    return swings[-1] if swings else None


def detect_bos(df: pd.DataFrame, short_len: int = 10, left: int = 3, right: int = 3) -> Optional[dict]:
    """Break of structure confirmed at the last bar of ``df``.

    Bullish BOS: the last close is above the highest confirmed swing high made
    in the preceding ``short_len`` bars, and the previous close was not.
    Returns None when there is no break. The returned dict contains the level
    and the confirmation bar so the caller can log the *reason*.

    Only rows up to and including the last row are read: zero look-ahead.
    """
    if len(df) < short_len + right + 2:
        return None
    reference = df.iloc[-short_len - right - 1 : -1]
    highs = reference["high"].to_numpy()
    lows = reference["low"].to_numpy()
    # Confirmed swing high: a high with `right` bars after it inside `reference`.
    level_high = None
    for k in range(left, len(highs) - right):
        if highs[k] == highs[k - left : k + right + 1].max():
            level_high = float(highs[k])
    level_low = None
    for k in range(left, len(lows) - right):
        if lows[k] == lows[k - left : k + right + 1].min():
            level_low = float(lows[k])

    close_now, close_prev = float(df["close"].iloc[-1]), float(df["close"].iloc[-2])
    if level_high is not None and close_prev <= level_high < close_now:
        return {"direction": "bullish", "level": level_high, "close": close_now, "index": len(df) - 1}
    if level_low is not None and close_prev >= level_low > close_now:
        return {"direction": "bearish", "level": level_low, "close": close_now, "index": len(df) - 1}
    return None


def detect_sweep(
    df: pd.DataFrame,
    lookback: int = 20,
    left: int = 2,
    right: int = 1,
    min_penetration_atr: float = 0.0,
    atr_value: Optional[float] = None,
) -> Optional[dict]:
    """Liquidity sweep confirmed by the last bar of ``df``.

    Buyside sweep (bearish intent): the last bar's high exceeds a confirmed
    swing high from the previous ``lookback`` bars, but its close falls back
    below that level. Sellside sweep is the mirror image.

    ``min_penetration_atr`` filters out one-tick fake-outs: the penetration
    must exceed that many ATRs. ``atr_value`` must be computed from bars <= t.
    """
    if len(df) < max(5, left + right + 2):
        return None
    history = df.iloc[:-1].tail(max(lookback, left + right + 2))
    last = df.iloc[-1]
    swings = swing_points(history, left=left, right=right)
    highs = [s.price for s in swings if s.kind == "high"]
    lows = [s.price for s in swings if s.kind == "low"]
    if not highs or not lows:
        return None
    swing_high, swing_low = max(highs), min(lows)
    min_pen = (atr_value or 0.0) * min_penetration_atr

    if last["high"] > swing_high + min_pen and last["close"] < swing_high:
        return {
            "direction": "bearish",  # sweep of highs -> look for shorts
            "level": swing_high,
            "extreme": float(last["high"]),
            "close": float(last["close"]),
            "index": len(df) - 1,
        }
    if last["low"] < swing_low - min_pen and last["close"] > swing_low:
        return {
            "direction": "bullish",
            "level": swing_low,
            "extreme": float(last["low"]),
            "close": float(last["close"]),
            "index": len(df) - 1,
        }
    return None


def detect_fvg(df: pd.DataFrame) -> Optional[Fvg]:
    """Fair value gap completed by the last bar of ``df`` (needs >= 3 rows).

    Bullish: low[t] > high[t-2]  -> zone [high[t-2], low[t]]
    Bearish: high[t] < low[t-2]  -> zone [high[t], low[t-2]]
    """
    if len(df) < 3:
        return None
    t = len(df) - 1
    h2, l2 = float(df["high"].iloc[t - 2]), float(df["low"].iloc[t - 2])
    ht, lt = float(df["high"].iloc[t]), float(df["low"].iloc[t])
    if lt > h2:
        return Fvg(t, df.index[t], "bullish", lower=h2, upper=lt)
    if ht < l2:
        return Fvg(t, df.index[t], "bearish", lower=ht, upper=l2)
    return None


def active_fvgs(df: pd.DataFrame, direction: str = "bullish", lookback: int = 30) -> list[Fvg]:
    """Unmitigated FVGs in the last ``lookback`` bars, oldest first.

    A gap is considered mitigated once a later bar's low (bullish) or high
    (bearish) trades back into the zone. Only bars <= the last row are used.
    """
    if len(df) < 3:
        return []
    start = max(2, len(df) - lookback)
    out: list[Fvg] = []
    for t in range(start, len(df)):
        h2, l2 = float(df["high"].iloc[t - 2]), float(df["low"].iloc[t - 2])
        ht, lt = float(df["high"].iloc[t]), float(df["low"].iloc[t])
        fvg: Optional[Fvg] = None
        if direction == "bullish" and lt > h2:
            fvg = Fvg(t, df.index[t], "bullish", h2, lt)
        elif direction == "bearish" and ht < l2:
            fvg = Fvg(t, df.index[t], "bearish", ht, l2)
        if fvg is None:
            continue
        mitigated = None
        for j in range(t + 1, len(df)):
            if direction == "bullish" and df["low"].iloc[j] <= fvg.upper:
                mitigated = j
                break
            if direction == "bearish" and df["high"].iloc[j] >= fvg.lower:
                mitigated = j
                break
        if mitigated is None:
            out.append(fvg)
    return out
