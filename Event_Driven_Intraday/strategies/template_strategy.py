"""TEMPLATE: write your own strategy here.

Copy this file to ``my_strategy.py``, rename the class, replace ``generate``.
The engine only needs the five hooks defined in ``intraday_engine.strategy``;
everything else (sizing, bracket management, journaling, accounting) is already
handled -- which is what "separation of concerns" buys you.

Worked example included: an opening-range breakout (ORB) for the first hour of
the NYSE session. It is intentionally simple so you can see the whole anatomy:

    warm-up -> session filter -> range formation -> breakout entry -> bracket

Run it end-to-end:

    python strategies/template_strategy.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow ``python strategies/template_strategy.py`` from the module root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from intraday_engine import (  # noqa: E402
    BacktestEngine,
    BaseStrategy,
    Context,
    ExecutionModel,
    FixedFractionSizer,
    Order,
    OrderType,
    Side,
    load_ohlcv_csv,
)


@dataclass
class OrbParams:
    """All strategy knobs in one place -- no magic numbers inside methods."""

    range_start: str = "13:30"   # UTC; 09:30 New York
    range_end: str = "14:30"     # UTC; 10:30 New York (first hour)
    session_end: str = "19:45"   # UTC; flatten 15 min before the close
    last_entry: str = "19:00"    # UTC; no new risk this close to the bell
    stop_buffer_atr: float = 0.10
    r_multiple: float = 1.5
    min_range_atr: float = 0.35  # skip days whose opening range is too narrow
    allow_shorts: bool = True


class OpeningRangeBreakout(BaseStrategy):
    """Long/short breakout of the first-hour range, bracketed with SL/TP."""

    warmup = 20  # bars needed for ATR / sanity

    def __init__(self, params: Optional[OrbParams] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.p = params or OrbParams()

    def reset(self) -> None:
        """Called by ``on_start``: forget everything about previous runs."""
        self.state.update({"phase": "FLAT", "day": None, "range_high": None,
                           "range_low": None, "done_today": False})

    # ------------------------------------------------------------- helpers
    def _clock(self, ctx: Context) -> str:
        return ctx.bar.timestamp.strftime("%H:%M")

    def _new_day(self, ctx: Context) -> bool:
        day = ctx.bar.timestamp.date()
        if self.state["day"] != day:
            self.state.update({"day": day, "range_high": None, "range_low": None, "done_today": False})
            self.transition("FLAT", ctx.bar, "new session")
            return True
        return False

    # --------------------------------------------------------------- signal
    def generate(self, ctx: Context) -> Optional[Dict[str, Any]]:
        """Build the opening range, then trade its first confirmed break."""
        self._new_day(ctx)
        clock = self._clock(ctx)
        p = self.p

        # 1) Accumulate the opening range. Only bars *inside* the window count.
        if p.range_start <= clock < p.range_end:
            self.state["range_high"] = max(self.state["range_high"] or ctx.bar.high, ctx.bar.high)
            self.state["range_low"] = min(self.state["range_low"] or ctx.bar.low, ctx.bar.low)
            return None

        # 2) Decide once per day, after the range is complete.
        if ctx.is_flat is False or self.state["done_today"]:
            return None
        if self.state["range_high"] is None or clock >= p.session_end:
            return None
        if not (p.range_end <= clock < p.last_entry):
            return None

        atr = self.spot(ctx)
        rng = self.state["range_high"] - self.state["range_low"]
        if atr <= 0 or rng < p.min_range_atr * atr:
            return None

        long_break = ctx.close > self.state["range_high"]
        short_break = ctx.close < self.state["range_low"]
        if long_break:
            entry = ctx.close
            stop = self.state["range_low"] - p.stop_buffer_atr * atr
            target = entry + p.r_multiple * (entry - stop)
            side = "buy"
        elif short_break and p.allow_shorts:
            entry = ctx.close
            stop = self.state["range_high"] + p.stop_buffer_atr * atr
            target = entry - p.r_multiple * (stop - entry)
            side = "sell"
        else:
            return None

        self.state["done_today"] = True  # one shot per session
        return {"side": side, "stop": stop, "target": target, "reason": "orb_break",
                "entry_ref": entry, "range_high": self.state["range_high"],
                "range_low": self.state["range_low"]}

    # ---------------------------------------------------------------- exits
    def manage(self, ctx: Context) -> List[Order]:
        """Time stop: never hold through the close (no overnight gap risk)."""
        if ctx.is_flat or self._clock(ctx) < self.p.session_end:
            return []
        return [Order(side=Side.BUY if ctx.position < 0 else Side.SELL,
                      qty=abs(ctx.position), type=OrderType.MARKET, tag="exit:session_close")]


def main() -> None:
    """Tiny CLI demo so you can run this file directly."""
    df = load_ohlcv_csv(str(_ROOT / "data" / "sample_5min_equity_1m.csv"))
    strat = OpeningRangeBreakout(sizer=FixedFractionSizer(risk_pct=0.01), sizing_mode="fixed")
    result = BacktestEngine.build(df, strat, initial_cash=100_000,
                                  model=ExecutionModel(fee_bps=2, slippage_bps=1)).run()
    print(result.summary())
    print("\nTrades:")
    print(result.trades.head(10).to_string(index=False))
    print("\nRejections:")
    print(result.rejections().head(10).to_string(index=False))


if __name__ == "__main__":
    main()
