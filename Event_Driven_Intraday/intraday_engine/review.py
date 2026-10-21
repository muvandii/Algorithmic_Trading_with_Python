"""Causal feature review: what a signal looked like, and when it was knowable.

The functions here are the "review" side of the workflow: after a candidate
signal fires, you want to inspect the confluence, measure it, and later replay
the exact bar. They are pure and operate on frames ending at bar t.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from .structure import detect_sweep


def signal(df: pd.DataFrame, lookback: int = 20, left: int = 2, right: int = 1) -> Optional[Dict[str, Any]]:
    """Return a sweep signal confirmed by the last bar of ``df``, or None.

    Thin wrapper so strategies do not import ``structure`` directly; makes it
    easy to swap in your own detector later (same dict schema).
    """
    return detect_sweep(df, lookback=lookback, left=left, right=right)
