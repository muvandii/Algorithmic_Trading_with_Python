"""EventLogger: a tiny append-only journal for bars, signals, orders and fills.

Why not the stdlib ``logging``? Because a backtest journal is *data*, not text:
you will want to filter it (``events[events.kind == 'REJECT']``), join it with
trades, and diff two runs. Keeping it as structured records makes
"why did the engine do that at 14:05?" a one-line query.

For live trading, subclass and forward to file/DB; the interface is only
``log()`` so swapping is trivial.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .core import Event


class EventLogger:
    """Collect structured events with a strict, documented schema.

    Record schema (all kinds share the first four fields)
    -----------------------------------------------------
    timestamp : pd.Timestamp  UTC, bar-open time of the bar being processed
    bar_index : int           positional index of that bar
    kind      : str           BAR|SIGNAL|STATE|ORDER|FILL|REJECT|TRADE|NOTE|ERROR
    message   : str           short human sentence
    payload   : dict          kind-specific extras (see README)

    Memory: O(number of events). A 5-minute year is ~105k bars, so log BAR
    events only when you need them (``log_bars=True``) and keep INFO-level
    detailed logging for the handful of bars around a trade.
    """

    def __init__(self, verbose: bool = False, log_bars: bool = False) -> None:
        self.verbose = verbose
        self.log_bars = log_bars
        self._events: List[Event] = []

    # ------------------------------------------------------------------ write
    def log(
        self,
        kind: str,
        message: str,
        timestamp: Optional[pd.Timestamp] = None,
        index: int = -1,
        **payload: Any,
    ) -> Event:
        """Append one event. Returns it so callers can assert on it in tests."""
        ev = Event(
            timestamp=pd.Timestamp(timestamp) if timestamp is not None else pd.Timestamp("1970-01-01", tz="UTC"),
            index=index,
            kind=kind,
            message=message,
            payload=payload,
        )
        self._events.append(ev)
        if self.verbose:
            print(f"[{ev.kind:<6}] {ev.timestamp} #{ev.index:<6} {ev.message} {payload or ''}")
        return ev

    def bar(self, timestamp: pd.Timestamp, index: int, **payload: Any) -> None:
        """Log a BAR event (only when ``log_bars=True``)."""
        if self.log_bars:
            self.log("BAR", "bar closed", timestamp=timestamp, index=index, **payload)

    def info(self, message: str, timestamp: Optional[pd.Timestamp] = None, index: int = -1, **payload: Any) -> None:
        """Free-form NOTE."""
        self.log("NOTE", message, timestamp=timestamp, index=index, **payload)

    # ------------------------------------------------------------------- read
    @property
    def events(self) -> List[Event]:
        """Raw event list (cheap; no copy)."""
        return self._events

    def to_frame(self) -> pd.DataFrame:
        """Events as a DataFrame, chronological, with a stable column order.

        Unused payload keys become NaN (pandas union of columns), so the frame
        is easy to filter but wide. Use ``events_of_kind`` for a tidy view.
        """
        if not self._events:
            return pd.DataFrame(columns=["timestamp", "bar_index", "kind", "message"])
        df = pd.DataFrame([e.as_dict() for e in self._events])
        lead = ["timestamp", "bar_index", "kind", "message"]
        return df[lead + [c for c in df.columns if c not in lead]]

    def events_of_kind(self, kind: str) -> pd.DataFrame:
        """Tidy view of a single event kind, e.g. ``'REJECT'``."""
        df = self.to_frame()
        return df[df["kind"] == kind].reset_index(drop=True) if not df.empty else df

    def counts(self) -> Dict[str, int]:
        """Count events per kind -- a quick health check of a run."""
        out: Dict[str, int] = {}
        for e in self._events:
            out[e.kind] = out.get(e.kind, 0) + 1
        return out

    def clear(self) -> None:
        """Drop all events (used between repeated runs in a notebook)."""
        self._events.clear()

    def to_jsonl(self, path: str) -> Path:
        """Persist the journal as JSON Lines (one event per line)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for e in self._events:
                fh.write(json.dumps(e.as_dict(), default=str) + "\n")
        return p
