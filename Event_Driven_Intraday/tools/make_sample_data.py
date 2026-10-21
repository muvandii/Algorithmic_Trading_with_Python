"""Generate the small, committed datasets used by the notebooks.

Run from ``Event_Driven_Intraday/``:

    python tools/make_sample_data.py

Files produced in ``data/``:
    pattern_sample.csv            24 bars, hand-planted FVG / sweep / BOS
    sample_5min_equity_1m.csv     ~1 month of 5-min NYSE-session bars (UTC)
    sample_1min_crypto_3d.csv     ~3 days of 1-min 24/7 crypto bars (UTC)

Why commit CSVs at all? Reproducibility: a lesson must give the same answer
next year. They are small (< 1 MB total) and deterministic (fixed seeds).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from intraday_engine.synthetic import make_ohlcv, make_pattern_sample  # noqa: E402


def main() -> None:
    """Write the three CSVs with an ISO-8601 UTC ``timestamp`` column."""
    out = ROOT / "data"
    out.mkdir(exist_ok=True)

    pattern = make_pattern_sample().rename_axis("timestamp").reset_index()
    pattern["timestamp"] = pattern["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    pattern.to_csv(out / "pattern_sample.csv", index=False)

    equity = make_ohlcv(2000, freq="5min", seed=2024, start="2024-01-02 13:30",
                        bar_vol_bps=16, drift_bps=0.06, session=("13:30", "20:00"))
    equity = equity.rename_axis("timestamp").reset_index()
    equity["timestamp"] = equity["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    equity.to_csv(out / "sample_5min_equity_1m.csv", index=False)

    crypto = make_ohlcv(4320, freq="1min", seed=7, start="2024-03-04 00:00",
                        bar_vol_bps=7, drift_bps=0.0, session=None, start_price=63_000)
    crypto["volume"] = crypto["volume"].round(3)  # BTC units, not shares
    crypto = crypto.rename_axis("timestamp").reset_index()
    crypto["timestamp"] = crypto["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    crypto.to_csv(out / "sample_1min_crypto_3d.csv", index=False)

    for path in sorted(out.glob("*.csv")):
        print(f"{path.name:32s} {len(pd.read_csv(path)):>6,d} rows  {path.stat().st_size / 1024:7.1f} KB")


if __name__ == "__main__":
    main()
