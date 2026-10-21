"""DataHandler: the single door through which a strategy may see market data.

Conventions enforced here (and taught in Lesson 1):

* index    : ``pd.DatetimeIndex``, tz-aware UTC, ascending, unique.
* columns  : lowercase ``open, high, low, close, volume``.
* labelling: each row is stamped with the bar's **open** time; the bar is only
             complete at ``timestamp + timeframe``.
* access   : positional index ``i`` (fast, unambiguous). Timestamps are for
             reporting; never for ``.loc`` inside a strategy.

The handler also carries a *cursor* (the index of the bar currently being
processed). Any read beyond the cursor raises ``LookAheadError``.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from .core import Bar, LookAheadError

REQUIRED_COLUMNS: Sequence[str] = ("open", "high", "low", "close", "volume")


class DataHandler:
    """Validated OHLCV access with a hard look-ahead guard.

    Parameters
    ----------
    df:
        Bar data. Must satisfy the conventions above (the constructor raises
        a helpful ``ValueError`` otherwise).
    symbol:
        Label copied into every event/fill/trade record.
    strict:
        When True (default) reads beyond ``cursor`` raise ``LookAheadError``.
        Set False only for offline research helpers (e.g. plotting the whole
        sample), never for decisions inside a strategy.

    Notes
    -----
    Memory: O(n) floats -- one float64 column set per bar. Streaming adaptation:
    keep the last ``max_lookback + 1`` rows in a ring buffer and expose the same
    ``bar()`` / ``window()`` API; nothing else in the engine needs the full frame.
    """

    def __init__(self, df: pd.DataFrame, symbol: str = "SYMBOL", strict: bool = True) -> None:
        self.symbol = symbol
        self.strict = strict
        self._df = self._validate(df)
        self._cursor = -1
        self._timestamps = self._df.index
        self._ohlcv = self._df.to_numpy(dtype="float64")  # (n, 5) fast path
        self._n = len(self._df)

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _validate(df: pd.DataFrame) -> pd.DataFrame:
        """Return a clean copy or raise a ValueError that explains the fix."""
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(
                f"DataHandler needs columns {list(REQUIRED_COLUMNS)}; missing {missing}. "
                "Rename your columns to lowercase OHLCV."
            )
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError(
                "DataHandler needs a pandas DatetimeIndex of bar-open timestamps, "
                f"got {type(df.index).__name__}."
            )
        if df.index.tz is None:
            raise ValueError(
                "Index must be tz-aware UTC. Fix with "
                "df.index = df.index.tz_localize('UTC') (or tz_convert('UTC'))."
            )
        if str(df.index.tz) != "UTC":
            df = df.tz_convert("UTC")
        if not df.index.is_monotonic_increasing:
            raise ValueError("Bars must be sorted ascending by timestamp. Use df.sort_index().")
        if df.index.has_duplicates:
            raise ValueError("Duplicate timestamps found. Use df = df[~df.index.duplicated(keep='last')].")
        out = df.loc[:, list(REQUIRED_COLUMNS)].copy()
        if out.isna().any().any():
            bad = out.isna().sum()
            raise ValueError(f"NaNs in OHLCV at {out.index[0]}: {bad[bad > 0].to_dict()}. Drop/ffill before backtesting.")
        if (out["high"] < out["low"]).any():
            raise ValueError("Found high < low. Clean the data; do not 'fix' it silently.")
        bad_range = (out["high"] < out[["open", "close"]].max(axis=1)) | (
            out["low"] > out[["open", "close"]].min(axis=1)
        )
        if bad_range.any():
            raise ValueError(f"{int(bad_range.sum())} bars have OHLC outside [low, high]. Inspect them.")
        return out

    # ----------------------------------------------------------------- cursor
    @property
    def cursor(self) -> int:
        """Index of the bar currently being processed (-1 before the run)."""
        return self._cursor

    def set_cursor(self, i: int) -> None:
        """Advance the 'now' pointer. Called by the engine, not by strategies."""
        if i < -1 or i >= self._n:
            raise IndexError(f"cursor {i} outside [-1, {self._n - 1}]")
        self._cursor = i

    def _check(self, i: int) -> None:
        if i < 0:
            raise IndexError(f"bar index {i} is negative; use i >= 0")
        if i >= self._n:
            raise IndexError(f"bar index {i} >= n_bars ({self._n})")
        if self.strict and i > self._cursor:
            raise LookAheadError(
                f"Bar {i} is in the future (cursor={self._cursor}). "
                "When handling bar t you may only read data with index <= t. "
                "If you need a completed pattern, wait for its confirmation bar."
            )

    # ------------------------------------------------------------- accessors
    @property
    def n_bars(self) -> int:
        """Number of bars."""
        return self._n

    @property
    def timestamps(self) -> pd.DatetimeIndex:
        """All bar-open timestamps (metadata only; do not use for decisions)."""
        return self._timestamps

    @property
    def timeframe(self) -> pd.Timedelta:
        """Bar duration inferred from the median timestamp gap."""
        if self._n < 2:
            return pd.Timedelta(0)
        return pd.Series(self._timestamps).diff().median()

    def bar(self, i: int) -> Bar:
        """Return bar ``i`` as an immutable ``Bar`` (respects the cursor)."""
        self._check(i)
        o, h, l, c, v = self._ohlcv[i]
        return Bar(i, self._timestamps[i], o, h, l, c, v)

    def window(self, end_i: int, n: int) -> pd.DataFrame:
        """Last ``n`` bars ending **at and including** ``end_i``.

        This is the only history API a strategy needs. It never returns rows
        after ``end_i``, so a window of 20 bars at t cannot leak t+1.
        """
        self._check(end_i)
        if n <= 0:
            raise ValueError("n must be positive")
        start = max(0, end_i - n + 1)
        return self._df.iloc[start : end_i + 1]

    def window_before(self, i: int, n: int) -> pd.DataFrame:
        """``n`` bars strictly **before** ``i`` (i.e. ending at i-1).

        Useful for "compare today's open with the previous 20 bars" logic.
        """
        self._check(i)
        if i == 0:
            return self._df.iloc[0:0]
        return self.window(i - 1, n)

    def at_timestamp(self, ts: pd.Timestamp) -> Bar:
        """Look up a bar by its (already-known) open timestamp."""
        pos = int(self._timestamps.get_indexer([ts])[0])
        if pos < 0:
            raise KeyError(f"{ts!r} is not a bar-open timestamp in this dataset")
        return self.bar(pos)

    def frame_upto(self, i: int) -> pd.DataFrame:
        """All bars from 0..i inclusive (research/diagnostics only)."""
        self._check(i)
        return self._df.iloc[: i + 1]

    def full_frame(self) -> pd.DataFrame:
        """The complete dataset, cursor ignored. **Never** call from a strategy."""
        return self._df

    def __len__(self) -> int:
        return self._n

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"DataHandler(symbol={self.symbol!r}, n_bars={self._n}, "
            f"timeframe={self.timeframe}, start={self._timestamps[0]}, end={self._timestamps[-1]})"
        )


# --------------------------------------------------------------------------
# Small, testable data utilities used by the notebooks
# --------------------------------------------------------------------------
def load_ohlcv_csv(path: str, tz: str = "UTC") -> pd.DataFrame:
    """Read an OHLCV CSV with a ``timestamp`` (or ``date``) column.

    The returned frame follows the DataHandler conventions exactly.
    """
    df = pd.read_csv(path)
    lower = {c.lower(): c for c in df.columns}
    ts_col = lower.get("timestamp") or lower.get("date") or lower.get("datetime")
    if ts_col is None:
        raise ValueError(f"No timestamp column in {path}: {list(df.columns)}")
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
    df = df.rename(columns={ts_col: "timestamp", **{lower[c]: c for c in ("open", "high", "low", "close", "volume")}})
    return df.set_index("timestamp").sort_index()[list(REQUIRED_COLUMNS)]


def session_filter(df: pd.DataFrame, start: str = "13:30", end: str = "20:00", tz: str = "UTC") -> pd.DataFrame:
    """Keep only bars inside a session expressed in the given timezone.

    Default 13:30-20:00 UTC == 09:30-16:00 New York (NYSE regular session).
    Crypto is 24/7: skip this helper. For equities, **always** filter, because
    overnight gaps and thin pre-market bars silently change every statistic.
    """
    local = df.index.tz_convert(tz)
    mask = (local.time >= pd.Timestamp(start).time()) & (local.time < pd.Timestamp(end).time())
    return df.loc[np.asarray(mask)]


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate bars to a coarser timeframe with correct OHLCV semantics."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return df.resample(rule, label="left", closed="left").agg(agg).dropna()
