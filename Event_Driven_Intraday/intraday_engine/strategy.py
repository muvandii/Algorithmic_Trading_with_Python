"""Strategy interfaces and a demo "pullback into FVG" strategy (Lesson 3/4/5).

A Strategy is deliberately dumb plumbing-wise: it receives a *view* of the
world that ends at bar t and may return a list of ``Order`` intents. It cannot
touch cash, fills or future bars. Everything it wants to happen must go through
an Order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

import pandas as pd

from .core import Bar, Order, OrderType, Side
from .data import DataHandler
from .journal import EventLogger
from .sizing import Sizer


@dataclass
class Context:
    """Everything a strategy is allowed to know at bar t.

    ``ctx.history`` is a DataFrame ending at and including the current bar.
    ``ctx.state`` is a dict the engine snapshots for you (Lesson 2).
    """

    bar: Bar
    history: pd.DataFrame  # 0..t inclusive, never beyond
    portfolio: Any  # read-only-ish: strategies may read equity/position
    state: Dict[str, Any] = field(default_factory=dict)

    @property
    def position(self) -> float:
        """Signed position size (0 when flat)."""
        return self.portfolio.position.qty

    @property
    def is_flat(self) -> bool:
        """True when there is no open position."""
        return self.portfolio.position.is_flat

    @property
    def equity(self) -> float:
        """Current equity marked at the last bar close."""
        return self.portfolio.equity

    @property
    def close(self) -> float:
        """Close of the current bar."""
        return self.bar.close


class Strategy(Protocol):
    """The five methods the engine calls. Implement all five; they are cheap."""

    def on_start(self, data: DataHandler, logger: EventLogger) -> None:
        """Called once before the first bar. Build indicators, reset state."""

    def on_bar(self, ctx: "Context") -> List[Order]:
        """Decide, using only data <= t. Return [] for 'do nothing'."""

    def on_fill(self, fill: Any, ctx: Optional["Context"] = None) -> None:
        """React to a fill (optional hook; useful for state transitions)."""

    def on_reject(self, order: Any, ctx: "Context", reason: str) -> None:
        """Keep the state machine honest when an order is refused or expires."""
        if getattr(order, "tag", "").startswith("entry") and self.state.get("phase") == "ENTERING":
            self.transition("FLAT", ctx.bar, f"entry rejected: {reason}")
            self.state.update(armed_level=None, setup=None)

    def on_finish(self, portfolio: Any, logger: EventLogger) -> None:
        """Called once after the last bar (reporting only)."""


class BaseStrategy:
    """Convenience base class: state machine, warm-up, helpers, logging.

    Subclass this, implement ``generate`` (signal logic) and optionally
    ``manage`` (discretionary exits). ``on_bar`` handles the boring parts:
    warm-up, state transitions, and refusing to trade while not flat.

    State machine (Lesson 2)
    ------------------------
    FLAT --signal--> ENTERING --fill--> IN_POSITION --exit--> FLAT
                          |                                    ^
                          +-------- rejected/cancelled --------+

    Transitions are logged as STATE events so a journal replay tells the story.
    """

    warmup: int = 50  # bars required before any signal is considered

    #: Which sizing rule to use: 'fixed' or 'atr'. Switch in one line.
    sizing_mode: str = "fixed"

    def __init__(
        self,
        symbol: str = "SYMBOL",
        sizer: Optional[Sizer] = None,
        params: Optional[Dict[str, Any]] = None,
        logger: Optional[EventLogger] = None,
        sizing_mode: str = "fixed",
    ) -> None:
        if sizing_mode not in ("fixed", "atr"):
            raise ValueError("sizing_mode must be 'fixed' or 'atr'")
        self.symbol = symbol
        self.sizer = sizer
        self.params: Dict[str, Any] = params or {}
        self.logger = logger or EventLogger()
        self.sizing_mode = sizing_mode
        self.state: Dict[str, Any] = {"phase": "FLAT", "entry_bar": -1, "pending_id": None, "signals": 0}
        self.data: Optional[DataHandler] = None

    # ------------------------------------------------------------ lifecycle
    def on_start(self, data: DataHandler, logger: EventLogger) -> None:
        """Store collaborators and reset the machine for a fresh run."""
        self.data = data
        self.logger = logger
        self.state = {"phase": "FLAT", "entry_bar": -1, "pending_id": None, "signals": 0}
        self.reset()

    def reset(self) -> None:
        """Hook for subclasses: clear indicators/counters (must be deterministic)."""

    def transition(self, phase: str, bar: Bar, reason: str) -> None:
        """Move the state machine and log the edge (from -> to)."""
        old = self.state["phase"]
        if old == phase:
            return
        self.state["phase"] = phase
        self.logger.log(
            "STATE",
            f"{old} -> {phase}: {reason}",
            timestamp=bar.timestamp,
            index=bar.index,
            **{"from": old, "to": phase, "reason": reason},
        )

    # ------------------------------------------------------------- main hook
    def on_bar(self, ctx: Context) -> List[Order]:
        """Default flow: warm-up -> manage exits -> entry signals -> orders."""
        self.state["phase"] = self.state.get("phase", "FLAT")
        if ctx.bar.index < self.warmup:
            return []
        orders = self.manage(ctx) or []
        if ctx.is_flat and self.state["phase"] != "ENTERING":
            sig = self.generate(ctx)
            if sig is not None:
                orders.extend(self.build_orders(ctx, sig))
        return orders

    # --------------------------------------------------------------- to override
    def generate(self, ctx: Context) -> Optional[Dict[str, Any]]:
        """Return a signal dict or None. Pure function of ``ctx.history``."""
        raise NotImplementedError

    def manage(self, ctx: Context) -> List[Order]:
        """Optional discretionary exits (time stops, trailing, session close)."""
        return []

    # ---------------------------------------------------------------- helpers
    def spot(self, ctx: Context, atr_mult: float = 1.5, atr_period: int = 14) -> float:
        """Stop distance: ATR-based when ``sizing_mode == 'atr'``, else structural."""
        h = ctx.history
        prev_close = h["close"].shift(1)
        tr = pd.concat([h["high"] - h["low"], (h["high"] - prev_close).abs(), (h["low"] - prev_close).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1.0 / atr_period, adjust=False, min_periods=atr_period).mean().iloc[-1]
        return float(atr_mult * atr) if pd.notna(atr) else 0.0

    def build_orders(self, ctx: Context, sig: Dict[str, Any]) -> List[Order]:
        """Translate a signal into a sized bracket order.

        Signals must supply ``side`` either explicitly or via ``direction``
        ('long'/'short'), plus ``stop`` and ``target`` prices. Sizing happens
        here so every strategy gets identical risk handling.
        """
        if ctx.is_flat is False:
            return []
        side = Side(sig.get("side") or ("buy" if sig["direction"] == "long" else "sell"))
        stop = float(sig["stop"])
        target = float(sig["target"])
        entry_ref = float(sig.get("entry_ref", ctx.close))
        qty = self.size(ctx, entry_ref, stop, sig.get("atr"))
        if qty <= 0:
            self.logger.log("REJECT", "size == 0 (risk budget too small)", timestamp=ctx.bar.timestamp, index=ctx.bar.index)
            return []
        self.state["signals"] += 1
        self.transition("ENTERING", ctx.bar, sig.get("reason", "signal"))
        self.logger.log(
            "SIGNAL",
            sig.get("reason", "signal"),
            timestamp=ctx.bar.timestamp,
            index=ctx.bar.index,
            reason=sig.get("reason", "signal"),
            side=side.value,
            qty=qty,
            entry_ref=entry_ref,
            stop=stop,
            target=target,
            **{k: v for k, v in sig.items() if k not in ("stop", "target", "entry_ref", "direction", "side", "reason")},
        )
        return [
            Order(
                side=side,
                qty=qty,
                type=OrderType(sig.get("order_type", "market")),
                limit_price=sig.get("limit_price"),
                stop_price=stop,
                take_profit_price=target,
                tag=f"entry:{sig.get('reason', 'signal')}",
                expires_after=sig.get("expires_after"),
            )
        ]

    def size(self, ctx: Context, entry: float, stop: float, atr_value: Optional[float] = None) -> float:
        """Size with the injected sizer; ``sizing_mode`` only picks the ATR input."""
        if self.sizer is None:
            raise ValueError("No sizer configured. Pass FixedFractionSizer() or AtrSizer().")
        atr_for_sizing = self.spot(ctx) if (atr_value is None and self.sizing_mode == "atr") else atr_value
        return self.sizer.size(
            equity=ctx.equity,
            entry_price=entry,
            stop_price=stop,
            atr=atr_for_sizing,
            price=ctx.close,
        )

    # ------------------------------------------------------------- fill hooks
    def on_fill(self, fill: Any, ctx: Optional[Context] = None) -> None:
        """Track entries so the state machine stays truthful."""
        if ctx is None:
            return
        reason = getattr(fill, "reason", "")
        tag = getattr(fill, "tag", "")
        if reason in ("stop", "take_profit") or tag.startswith("exit"):
            self.transition("FLAT", ctx.bar, f"exit: {reason or tag}")
        elif "entry" in tag:
            self.transition("IN_POSITION", ctx.bar, f"entry filled @ {fill.price:.4f}")
            self.state["entry_bar"] = ctx.bar.index

    def on_reject(self, order: Any, ctx: "Context", reason: str) -> None:
        """Keep the state machine honest when an order is refused or expires."""
        if getattr(order, "tag", "").startswith("entry") and self.state.get("phase") == "ENTERING":
            self.transition("FLAT", ctx.bar, f"entry rejected: {reason}")
            self.state.update(armed_level=None, setup=None)

    def on_finish(self, portfolio: Any, logger: EventLogger) -> None:
        """Default: nothing. Override for custom summary metrics."""
