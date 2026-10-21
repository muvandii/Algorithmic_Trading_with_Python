"""Synthetic, realistic intraday OHLCV generator (reproducible).

Why synthetic first?
--------------------
Real intraday data has gaps, halts, bad prints and session quirks that confuse a
beginner debugging a loop. Synthetic data lets us *know the answer*: we can
plant a liquidity sweep or an FVG exactly at bar 37 and assert our detector
finds it there. The generator also models:
  * a per-session open gap (equities),
  * an intraday volatility smile (U-shape),
  * fat-ish tails via occasional jump bars,
  * volume correlated with range.

Everything is seeded: same seed => byte-identical DataFrame.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

EQUITY_SESSION = ("13:30", "20:00")  # UTC, NYSE regular hours


def make_ohlcv(
    n_bars: int = 500,
    freq: str = "5min",
    start: str = "2024-01-02 13:30",
    seed: int = 42,
    symbol: str = "SYNTH",
    start_price: float = 100.0,
    bar_vol_bps: float = 18.0,
    drift_bps: float = 0.05,
    session: Optional[tuple[str, str]] = EQUITY_SESSION,
    jump_prob: float = 0.01,
) -> pd.DataFrame:
    """Generate a reproducible OHLCV DataFrame with a UTC DatetimeIndex.

    Parameters
    ----------
    n_bars:
        Number of bars to *keep* inside trading sessions (extras are dropped).
    freq:
        pandas offset alias, e.g. ``'1min'``, ``'5min'``, ``'15min'``.
    session:
        (start, end) UTC times to keep, or None for 24/7 crypto.
    bar_vol_bps:
        Per-bar log-return standard deviation in basis points.
    jump_prob:
        Probability of a 4x-volatility bar (news/fat finger).

    Returns
    -------
    DataFrame with columns open, high, low, close, volume and a tz-aware UTC index.

    Notes
    -----
    Complexity O(n). Volatility is scaled by ``sqrt(bar_minutes / 5)`` so a
    1-minute series is not accidentally as volatile as a 5-minute one.
    """
    rng = np.random.default_rng(seed)
    step = pd.Timedelta(freq)
    bar_minutes = step.total_seconds() / 60.0
    vol = bar_vol_bps / 10_000.0 * np.sqrt(bar_minutes / 5.0)
    drift = drift_bps / 10_000.0 * (bar_minutes / 5.0)

    # Build a continuous timestamp index (sessions filtered afterwards).
    # A 6.5h equity session is ~27% of the clock, so ask for ~4x the bars.
    multiplier = 4.5 if session is not None else 1.05
    stamps = pd.date_range(start=pd.Timestamp(start, tz="UTC"), periods=int(n_bars * multiplier), freq=freq)
    if session is not None:
        lo, hi = (pd.Timestamp(t).time() for t in session)
        local = stamps.tz_convert("UTC")
        stamps = stamps[(local.time >= lo) & (local.time < hi)][:n_bars]
    else:
        stamps = stamps[:n_bars]
    n = len(stamps)

    # Intraday U-shaped volatility: higher at the open and into the close.
    frac = np.linspace(0, 1, n)
    smile = 1.0 + 0.8 * (frac - 0.5) ** 2 * 4
    jumps = (rng.random(n) < jump_prob) * 3.0
    rets = rng.normal(drift, vol, n) * smile * (1.0 + jumps)

    # Session open gaps: first bar of each day gets extra noise.
    day = pd.Series(stamps).dt.date.to_numpy()
    first_of_day = np.r_[True, day[1:] != day[:-1]]
    rets[first_of_day] += rng.normal(0, vol * 3, first_of_day.sum())

    close = start_price * np.exp(np.cumsum(rets))
    open_ = np.r_[start_price, close[:-1]] * (1 + rng.normal(0, vol * 0.15, n))
    span = np.abs(rng.normal(vol * 1.6, vol * 0.7, n))
    high = np.maximum(open_, close) * (1 + span * rng.random(n))
    low = np.minimum(open_, close) * (1 - span * rng.random(n))
    volume = np.round(rng.lognormal(9.0, 0.45, n) * (1 + jumps) * (high - low) / (vol * start_price), 0)

    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=pd.DatetimeIndex(stamps, name="timestamp"),
    )
    return df.round({"open": 2, "high": 2, "low": 2, "close": 2})


def make_pattern_sample(seed: int = 7) -> pd.DataFrame:
    """A 24-bar hand-crafted sample with an FVG, a sweep and a BOS.

    The patterns are planted at known rows so the lesson's "expected output"
    and the tests can assert exact indices:

    * row 10     : bullish fair value gap completed by rows 8-10,
                   zone = [high[8], low[10]] = [101.00, 101.20]
    * row 15     : confirmed swing low at 100.55 (with left=2, right=1)
    * row 17     : sell-side liquidity sweep (low 100.10 < 100.55, close 100.65)
    * row 19     : bullish break of structure (close 101.60 > swing high 101.45)
    * row 20     : bullish fair value gap from the impulse, zone [100.90, 101.30]

    The frame is validated internally: high >= max(open, close) and
    low <= min(open, close) on every row.
    """
    ts = pd.date_range("2024-01-02 14:00", periods=24, freq="5min", tz="UTC")
    open_ = [100.00, 100.10, 100.35, 100.55, 100.65, 100.80, 100.95, 101.00,
             100.95, 101.00, 101.35, 101.25, 101.10, 101.00, 100.85, 100.75,
             100.60, 100.70, 100.65, 100.85, 101.60, 101.40, 101.15, 101.05]
    high = [100.20, 100.35, 100.60, 100.75, 100.85, 101.00, 101.15, 101.10,
            101.00, 101.40, 101.45, 101.30, 101.20, 101.05, 100.90, 100.80,
            100.85, 100.85, 100.90, 101.70, 101.75, 101.50, 101.30, 101.25]
    low = [99.90, 100.05, 100.30, 100.50, 100.60, 100.75, 100.90, 100.95,
           100.85, 100.95, 101.20, 101.05, 100.95, 100.80, 100.70, 100.55,
           100.58, 100.10, 100.55, 100.80, 101.30, 101.25, 101.00, 100.98]
    close = [100.10, 100.30, 100.55, 100.70, 100.80, 101.00, 101.00, 101.10,
             100.95, 101.35, 101.25, 101.10, 101.00, 100.85, 100.75, 100.60,
             100.80, 100.65, 100.85, 101.60, 101.40, 101.28, 101.10, 101.05]
    vol = [1000 + 60 * i for i in range(24)]
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=pd.DatetimeIndex(ts, name="timestamp"),
    ).round(2)
    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
    return df
