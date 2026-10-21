"""Example strategy: liquidity sweep -> break of structure -> FVG pullback.

This is the multi-stage setup taught in Lesson 3, written the way you would
write *your own* strategy: pure functions for detection, a small state machine
for sequencing, and the base class handling sizing/logging.

Setup (long side; short side is the mirror image)
-------------------------------------------------
1. SWEEP   : price wicks below a confirmed swing low and closes back above it
             (sell-side liquidity taken). Arms the setup.
2. BOS     : within ``expiry_bars`` bars, a 5-bar close breaks the most recent
             confirmed swing high. Confirms intent.
3. FVG     : price pulls back into the bullish fair value gap created by the
             impulse. Entry = FVG midpoint (limit order).
4. EXIT    : stop below the sweep low, target = 2R (configurable R multiple).

Everything is evaluated with data up to and including bar t; orders fill on
the next bar(s) via the ExecutionEngine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .core import Order, OrderType, Side
from .review import signal as detect_signal
from .structure import active_fvgs, last_swing
from .strategy import BaseStrategy, Context


@dataclass
class SweepBosFvgParams:
    """All knobs in one place, with defaults tuned for 5-min liquid futures/equity."""

    swing_lookback: int = 20
    swing_left: int = 2
    swing_right: int = 1
    expiry_bars: int = 12
    fvg_lookback: int = 10
    stop_buffer_atr: float = 0.15
    r_multiple: float = 2.0
    session_exit_hour: Optional[int] = 20  # UTC; None = hold overnight
    allow_shorts: bool = True
    entry_mode: str = "limit"  # 'limit' = FVG midpoint, 'market' = fill at next open


class SweepBosFvgStrategy(BaseStrategy):
    """Three-stage long/short setup with a limit entry at the FVG midpoint."""

    warmup = 40

    def __init__(self, params: Optional[SweepBosFvgParams] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.p = params or SweepBosFvgParams()

    def reset(self) -> None:
        """State: phase, the armed level, and the bar index of the sweep."""
        self.state.update({"phase": "FLAT", "armed_level": None, "armed_bar": -1, "setup": None, "fwds": []})

    # ---------------------------------------------------------------- signals
    def generate(self, ctx: Context) -> Optional[Dict[str, Any]]:
        """Advance the setup machine one bar and return an entry signal if ready.

        Phases: FLAT -> ARMED (sweep) -> BOS_CONFIRMED -> ENTERING -> IN_POSITION.
        Every branch is a pure function of ``ctx.history`` plus stored state.
        """
        h = ctx.history
        idx = ctx.bar.index
        phase = self.state["phase"]

        if phase == "FLAT":
            sig = detect_signal(h, lookback=self.p.swing_lookback, left=self.p.swing_left, right=self.p.swing_right)
            if sig is None:
                return None
            if sig["direction"] == "bearish" and not self.p.allow_shorts:
                return None
            structure = last_swing(
                h.iloc[:-1],
                "high" if sig["direction"] == "bullish" else "low",
                left=self.p.swing_left,
                right=self.p.swing_right,
            )
            self.state.update(
                phase="ARMED",
                armed_level=structure.price if structure else sig["level"],
                armed_bar=idx,
                setup={
                    "direction": sig["direction"],
                    "sweep_index": idx,
                    "sweep_extreme": sig["extreme"],
                    "structure_level": structure.price if structure else sig["level"],
                },
            )
            self.transition("ARMED", ctx.bar, f"sweep of {sig['level']:.2f}")
            return None

        if phase == "ARMED":
            setup = self.state["setup"]
            if idx - self.state["armed_bar"] > self.p.expiry_bars:
                self._expire(ctx, "setup expired")
                return None
            level = setup["structure_level"]
            prev_close = float(h["close"].iloc[-2])
            broke = (prev_close <= level < ctx.close) if setup["direction"] == "bullish" else (
                prev_close >= level > ctx.close
            )
            if not broke:
                return None
            self.transition("BOS_CONFIRMED", ctx.bar, "close beyond structure")
            self.state["bos_bar"] = idx
            return self._await_fvg(ctx)

        if phase == "BOS_CONFIRMED":
            if idx - self.state.get("bos_bar", idx) > self.p.expiry_bars:
                self._expire(ctx, "no imbalance after BOS")
                return None
            return self._await_fvg(ctx)

        return None

    def _await_fvg(self, ctx: Context) -> Optional[Dict[str, Any]]:
        """Look for an unmitigated FVG in the setup direction and build a signal."""
        setup = self.state.get("setup") or {}
        direction = setup.get("direction")
        if direction is None:
            self._expire(ctx, "no setup context")
            return None
        gaps = active_fvgs(ctx.history, direction=direction, lookback=self.p.fvg_lookback)
        if not gaps:
            return None
        gap = gaps[-1]
        entry = ctx.close if self.p.entry_mode == "market" else gap.midpoint
        atr = self.spot(ctx)
        if direction == "bullish":
            stop = setup["sweep_extreme"] - self.p.stop_buffer_atr * atr
            if entry <= stop:
                return None
            target = entry + self.p.r_multiple * (entry - stop)
            side = "buy"
        else:
            stop = setup["sweep_extreme"] + self.p.stop_buffer_atr * atr
            if entry >= stop:
                return None
            target = entry - self.p.r_multiple * (stop - entry)
            side = "sell"
        self.state["phase"] = "WAITING_PULLBACK"
        self.state["setup"]["entry"] = entry
        return {
            "side": side,
            "direction": "long" if side == "buy" else "short",
            "stop": stop,
            "target": target,
            "entry_ref": entry,
            "order_type": "market" if self.p.entry_mode == "market" else "limit",
            "limit_price": None if self.p.entry_mode == "market" else entry,
            "expires_after": self.p.expiry_bars,
            "reason": f"{'sell' if side == 'buy' else 'buy'}side sweep + BOS + FVG",
            "fvg_lower": gap.lower,
            "fvg_upper": gap.upper,
        }

    def _expire(self, ctx: Context, reason: str) -> None:
        """Return to FLAT and forget the setup."""
        self.transition("FLAT", ctx.bar, reason)
        self.state.update(armed_level=None, setup=None, bos_bar=-1)

    # ------------------------------------------------------------------ exits
    def manage(self, ctx: Context) -> List[Order]:
        """Time-based exit: flatten before the session close (no overnight risk)."""
        if ctx.is_flat or self.p.session_exit_hour is None:
            return []
        if ctx.bar.timestamp.hour >= self.p.session_exit_hour:
            return [
                Order(
                    side=Side.BUY if ctx.position < 0 else Side.SELL,
                    qty=abs(ctx.position),
                    type=OrderType.MARKET,
                    tag="exit:session_close",
                )
            ]
        return []

    # ------------------------------------------------------------- fill logic
    def on_fill(self, fill: Any, ctx: Optional[Context] = None) -> None:
        """Reset the machine after any round trip; cancel logic handled by engine."""
        super().on_fill(fill, ctx)
        if ctx is not None and getattr(fill, "reason", "") in ("stop", "take_profit"):
            self.state.update(armed_level=None, setup=None)
        if getattr(fill, "tag", "").startswith("exit"):
            self.state.update(armed_level=None, setup=None)
