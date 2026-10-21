"""ExecutionEngine: orders in, fills out -- with explicit costs and no peeking.

Responsibilities
----------------
1. Hold pending orders and fill them under *conservative* intrabar rules.
2. Manage the protective bracket (stop-loss / take-profit) of an open position.
3. Charge configurable fees and adverse slippage and report both per fill.

Rules that matter (Lesson 4)
----------------------------
* Market orders fill at the **open of the next bar** (the signal bar is already
  history when the strategy sees its close).
* Limit orders fill only if price trades through them; among equally valid
  assumptions we take the conservative one (fill at the limit, no improvement).
* If a bar's range touches BOTH stop and target, the default assumption is the
  **stop** (``ambiguity='conservative'``). ``'optimistic'`` exists only so you
  can measure how much that assumption is worth. Never ship 'optimistic'.
* Gaps are handled explicitly: a stop gapped through fills at the open, not at
  the stop price -- this is where most backtests lie to their authors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .core import Bar, Fill, Order, OrderType, Side
from .data import DataHandler
from .portfolio import Portfolio


@dataclass
class ExecutionModel:
    """All frictions in one config object.

    Parameters
    ----------
    fee_bps:
        Taker fee in basis points of notional (1 bp = 0.01%).
    maker_fee_bps:
        Fee used for passive limit fills (often negative = rebate).
    min_fee:
        Absolute minimum commission per fill (many brokers have one).
    slippage_bps:
        Adverse price impact applied to taker fills.
    stop_slippage_bps:
        Extra adverse impact on stop fills (stops are liquidity-taking in a
        hurry). Keep it >= slippage_bps.
    """

    fee_bps: float = 2.0
    maker_fee_bps: float = 0.0
    min_fee: float = 0.0
    slippage_bps: float = 1.0
    stop_slippage_bps: float = 3.0

    def commission(self, notional: float, maker: bool = False) -> float:
        """Fee for a fill of ``notional``."""
        bps = self.maker_fee_bps if maker else self.fee_bps
        return max(abs(notional) * bps / 10_000.0, self.min_fee)

    def apply_slippage(self, price: float, side: Side, kind: str = "taker") -> float:
        """Return the (adverse) fill price and record nothing."""
        bps = self.stop_slippage_bps if kind == "stop" else self.slippage_bps
        return price * (1.0 + side.sign * bps / 10_000.0)


@dataclass
class Bracket:
    """Protective levels attached to an open position."""

    order_id: int
    side: Side
    qty: float
    stop_price: Optional[float]
    take_profit_price: Optional[float]
    entry_index: int
    reason: str = ""


@dataclass
class ExecutionEngine:
    """Bar-by-bar broker simulator.

    Parameters
    ----------
    data, portfolio, logger:
        Injected collaborators (swap any of them for a live adapter).
    model:
        Fees/slippage configuration.
    ambiguity:
        ``'conservative'`` (default) or ``'optimistic'`` -- see module docstring.
    """

    data: DataHandler
    portfolio: Portfolio
    logger: object
    model: ExecutionModel = field(default_factory=ExecutionModel)
    ambiguity: str = "conservative"
    pending: List[Order] = field(default_factory=list)
    brackets: Dict[int, Bracket] = field(default_factory=dict)
    _next_id: int = 1
    fills: List[Fill] = field(default_factory=list)
    rejections: List[Tuple[Order, str]] = field(default_factory=list)

    # ------------------------------------------------------------------ orders
    def submit(self, order: Order, bar: Bar) -> Order:
        """Validate, stamp and queue an order. Rejections are logged, not raised."""
        if order.qty <= 0:
            self._reject(order, bar, "qty must be > 0")
            return order
        if order.tag.startswith("exit") and self.portfolio.position.is_flat:
            self._reject(order, bar, "no position to exit")
            return order
        if order.tag.startswith("exit") and any(o.tag.startswith("exit") for o in self.pending):
            # Duplicate exit protection: two exits queued for one position would
            # close it and then open the opposite one. This is a real bug we hit;
            # the guard makes it impossible.
            self._reject(order, bar, "duplicate exit already pending")
            return order
        if order.type is OrderType.LIMIT and order.limit_price is None:
            self._reject(order, bar, "LIMIT order without limit_price")
            return order
        if order.stop_price is not None and order.take_profit_price is not None:
            # Levels are validated against the realised fill price in
            # ``_register_bracket`` (an entry can gap away from the signal bar).
            if order.side is Side.BUY and order.stop_price >= order.take_profit_price:
                self._reject(order, bar, "long bracket needs stop < take-profit")
                return order
            if order.side is Side.SELL and order.stop_price <= order.take_profit_price:
                self._reject(order, bar, "short bracket needs stop > take-profit")
                return order
        order.id = self._next_id
        order.submitted_index = bar.index
        self._next_id += 1
        self.pending.append(order)
        self.logger.log(
            "ORDER",
            f"{order.type.value} {order.side.value} {order.qty:g} {order.tag}",
            timestamp=bar.timestamp,
            index=bar.index,
            order_id=order.id,
            side=order.side.value,
            qty=order.qty,
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            take_profit_price=order.take_profit_price,
            type=order.type.value,
            tag=order.tag,
        )
        return order

    def _reject(self, order: Order, bar: Bar, reason: str) -> None:
        """Log a rejection. Rejections are data: always look at them."""
        self.rejections.append((order, reason))
        self.logger.log(
            "REJECT",
            reason,
            timestamp=bar.timestamp,
            index=bar.index,
            order_id=order.id,
            side=order.side.value,
            qty=order.qty,
            tag=order.tag,
        )

    # --------------------------------------------------------------- main loop
    def process_bar(self, bar: Bar) -> List[Fill]:
        """Handle intrabar exits first, then new orders. Returns new fills."""
        out: List[Fill] = []
        out.extend(self._manage_brackets(bar))       # exits for positions opened earlier
        if self.portfolio.position.is_flat and self.pending:
            # The bracket already flattened us: any queued "exit" intent is stale.
            stale = [o for o in self.pending if o.tag.startswith("exit")]
            self.pending = [o for o in self.pending if not o.tag.startswith("exit")]
            for o in stale:
                self._reject(o, bar, "position already flat (bracket exited)")
        out.extend(self._process_pending(bar))       # new entries at this bar's prices
        out.extend(self._manage_brackets(bar))       # same-bar stop/target on a fresh entry

        if self.portfolio.position.is_flat:
            self.brackets.clear()
        return out

    def _manage_brackets(self, bar: Bar) -> List[Fill]:
        """Resolve stop/target hits for the open position (conservative)."""
        pos = self.portfolio.position
        if pos.is_flat or not self.brackets:
            return []
        bracket = next(iter(self.brackets.values()))
        side = bracket.side  # side of the *entry*
        qty = abs(pos.qty)
        exit_side = side.exit_side

        stop_hit, stop_px = self._stop_triggered(bracket, bar)
        tp_hit, tp_px = self._target_triggered(bracket, bar)

        if stop_hit and tp_hit:
            # Ambiguous bar. Conservative = assume the stop was hit first (you were
            # in the trade, the worst happened). Optimistic exists only to size
            # how much this assumption is worth.
            if self.ambiguity == "conservative":
                tp_hit, tp_px = False, None
            else:
                stop_hit, stop_px = False, None

        if stop_hit:
            px = self.model.apply_slippage(stop_px, exit_side, kind="stop")
            fill = self._make_fill(bar, exit_side, qty, px, stop_px, reason="stop", tag=f"exit:stop:{bracket.reason}", maker=False)
            self.brackets.pop(bracket.order_id, None)
            return [fill]
        if tp_hit:
            px = tp_px  # resting limit: no adverse slippage, maker fee
            fill = self._make_fill(bar, exit_side, qty, px, tp_px, reason="take_profit", tag=f"exit:tp:{bracket.reason}", maker=True)
            self.brackets.pop(bracket.order_id, None)
            return [fill]
        return []

    @staticmethod
    def _stop_triggered(br: Bracket, bar: Bar) -> tuple[bool, Optional[float]]:
        """True + fill price if the stop is touched, including gap-through."""
        if br.stop_price is None:
            return False, None
        if br.side is Side.BUY:  # long: stop below
            if bar.open <= br.stop_price:
                return True, bar.open  # gapped through: fill at open
            if bar.low <= br.stop_price:
                return True, br.stop_price
        else:  # short: stop above
            if bar.open >= br.stop_price:
                return True, bar.open
            if bar.high >= br.stop_price:
                return True, br.stop_price
        return False, None

    @staticmethod
    def _target_triggered(br: Bracket, bar: Bar) -> tuple[bool, Optional[float]]:
        """True + fill price if the take-profit is touched (gaps help you)."""
        if br.take_profit_price is None:
            return False, None
        if br.side is Side.BUY:
            if bar.open >= br.take_profit_price:
                return True, bar.open
            if bar.high >= br.take_profit_price:
                return True, br.take_profit_price
        else:
            if bar.open <= br.take_profit_price:
                return True, bar.open
            if bar.low <= br.take_profit_price:
                return True, br.take_profit_price
        return False, None

    def _process_pending(self, bar: Bar) -> List[Fill]:
        """Fill market orders at the open, limit orders if touched."""
        out: List[Fill] = []
        keep: List[Order] = []
        for order in self.pending:
            if order.submitted_index >= bar.index:
                # THE anti-look-ahead rule: an order created while processing bar t
                # cannot be filled with bar t's prices. It becomes eligible at t+1.
                keep.append(order)
                continue
            if order.expires_after is not None and bar.index - order.submitted_index > order.expires_after:
                self._reject(order, bar, "expired")
                continue
            if order.type is OrderType.MARKET:
                px = self.model.apply_slippage(bar.open, order.side)
                out.append(self._make_fill(bar, order.side, order.qty, px, bar.open, "market", order.tag))
                self._register_bracket(order, bar, px)
            else:  # LIMIT
                touched = (
                    bar.low <= order.limit_price
                    if order.side is Side.BUY
                    else bar.high >= order.limit_price
                )
                if not touched:
                    keep.append(order)
                    continue
                px = float(order.limit_price)  # conservative: no price improvement
                out.append(self._make_fill(bar, order.side, order.qty, px, px, "limit", order.tag, maker=True))
                self._register_bracket(order, bar, px)
        self.pending = keep
        return out

    def _register_bracket(self, order: Order, bar: Bar, fill_price: float) -> None:
        """Attach SL/TP to the newly opened position; sanity-check levels."""
        if order.stop_price is None and order.take_profit_price is None:
            return
        if order.stop_price is not None:
            wrong = (order.side is Side.BUY and order.stop_price >= fill_price) or (
                order.side is Side.SELL and order.stop_price <= fill_price
            )
            if wrong:
                self._reject(order, bar, "stop on the wrong side of the fill price")
                return
        if order.take_profit_price is not None:
            wrong = (order.side is Side.BUY and order.take_profit_price <= fill_price) or (
                order.side is Side.SELL and order.take_profit_price >= fill_price
            )
            if wrong:
                self._reject(order, bar, "take-profit on the wrong side of the fill price")
                return
        self.brackets[order.id] = Bracket(
            order_id=order.id,
            side=order.side,
            qty=order.qty,
            stop_price=order.stop_price,
            take_profit_price=order.take_profit_price,
            entry_index=bar.index,
            reason=order.tag,
        )

    # ---------------------------------------------------------------- plumbing
    def _make_fill(
        self,
        bar: Bar,
        side: Side,
        qty: float,
        price: float,
        reference_price: float,
        reason: str,
        tag: str,
        maker: bool = False,
    ) -> Fill:
        """Build, log and book a fill. This is the only place fills are created."""
        fee = self.model.commission(qty * price, maker=maker)
        slip = abs(price - reference_price) * qty
        fill = Fill(
            timestamp=bar.timestamp,
            index=bar.index,
            order_id=-1,
            side=side,
            qty=qty,
            price=float(price),
            fee=float(fee),
            slippage_cost=float(slip),
            reason=reason,
            tag=tag,
        )
        self.portfolio.apply_fill(fill)
        self.fills.append(fill)
        payload = fill.as_dict()
        payload.pop("timestamp", None)  # already the event timestamp
        self.logger.log(
            "FILL",
            f"{reason} {side.value} {qty:g} @ {price:.4f}",
            timestamp=bar.timestamp,
            index=bar.index,
            **payload,
        )
        return fill

    def flatten(self, bar: Bar, reason: str = "end_of_test") -> List[Fill]:
        """Liquidate any open position at ``bar.close`` (test boundary only).

        Called by the engine after the final bar so trade statistics are complete
        and no position is silently carried out of the sample. Slippage applies;
        the fill is tagged ``exit:end_of_test``.
        """
        pos = self.portfolio.position
        if pos.is_flat:
            return []
        side = Side.SELL if pos.qty > 0 else Side.BUY
        px = self.model.apply_slippage(bar.close, side, kind="taker")
        fill = self._make_fill(bar, side, abs(pos.qty), px, bar.close, reason, "exit:end_of_test")
        self.pending.clear()
        self.brackets.clear()
        return [fill]

    def drain_rejections(self) -> List[Tuple[Order, str]]:
        """Return and clear rejections since the last call (engine -> strategy)."""
        out = list(self.rejections)
        self.rejections.clear()
        return out

    def cancel_all(self, bar: Bar, reason: str = "cancelled") -> None:
        """Drop pending orders (end of session, kill-switch, etc.)."""
        for o in self.pending:
            self._reject(o, bar, reason)
        self.pending = []

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"ExecutionEngine(pending={len(self.pending)}, brackets={len(self.brackets)}, fills={len(self.fills)})"
