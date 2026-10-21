"""Portfolio/Account: the only component that is allowed to change money.

Accounting model
----------------
* ``cash``    : unencumbered cash. A buy reduces cash by `qty*price + fee`,
                a sell increases it by `qty*price - fee`.
* ``position``: signed quantity (+ long, - short). One position per symbol.
* ``equity``  : ``cash + position * mark_price``. This identity holds for
                shorts too, which is why the same code path works both ways.
* Realised PnL is booked when quantity is *closed*; fees are always expensed
  immediately (conservative: you never get them back).

Simplifications (documented on purpose)
---------------------------------------
* No margin/leverage model, no borrow fees, no funding for perps.
* One symbol per Portfolio instance (use one portfolio per symbol, or extend
  ``positions`` to a dict keyed by symbol).
* Fractional units are allowed; set ``LotRounding`` in your strategy if your
  venue requires whole coins/shares.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .core import Fill, Side, TradeRecord


@dataclass
class Position:
    """Signed position with an average entry price."""

    qty: float = 0.0
    avg_price: float = 0.0
    entry_time: Optional[pd.Timestamp] = None
    entry_index: int = -1
    entry_reason: str = ""

    @property
    def is_flat(self) -> bool:
        """True when qty == 0."""
        return abs(self.qty) < 1e-12

    @property
    def side(self) -> Optional[Side]:
        """BUY for a long, SELL for a short, None when flat."""
        if self.is_flat:
            return None
        return Side.BUY if self.qty > 0 else Side.SELL


class Portfolio:
    """Cash + position accounting and an equity curve.

    The Portfolio knows nothing about strategies or orders: it only reacts to
    fills (``apply_fill``) and marks (``mark``). That is what makes it
    replaceable by a broker account adapter in live trading.
    """

    def __init__(self, initial_cash: float = 100_000.0, symbol: str = "SYMBOL", log=None) -> None:
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.symbol = symbol
        self.position = Position()
        self.realized_pnl = 0.0
        self.fees_paid = 0.0
        self.log = log
        self._equity_rows: List[Dict[str, float]] = []
        self._trades: List[TradeRecord] = []
        # Accumulators for the *open* leg, so a partial close still records fees.
        self._open_fees = 0.0
        self._last_mark: float = 0.0

    # ------------------------------------------------------------------ state
    @property
    def equity(self) -> float:
        """Cash plus the market value of the open position at the last mark."""
        return self.cash + self.position.qty * self._last_mark

    def set_mark(self, price: float) -> None:
        """Record the latest price used for equity (call once per bar close)."""
        self._last_mark = float(price)

    # ------------------------------------------------------------------ fills
    def apply_fill(self, fill: Fill) -> Optional[TradeRecord]:
        """Update cash/position with ``fill``; return a TradeRecord on a close.

        Handles four cases: open, increase, reduce/close, and flip (a sell
        larger than a long position closes it and opens a short).
        """
        self.cash -= fill.side.sign * fill.qty * fill.price
        self.cash -= fill.fee
        self.fees_paid += fill.fee
        self._last_mark = fill.price

        signed = fill.side.sign * fill.qty
        pos = self.position
        trade: Optional[TradeRecord] = None

        if pos.is_flat or (pos.qty > 0) == (signed > 0):
            # Open or increase: weighted average entry, accumulate entry fees.
            new_qty = pos.qty + signed
            total_cost = abs(pos.qty) * pos.avg_price + fill.qty * fill.price
            pos.avg_price = total_cost / abs(new_qty)
            pos.qty = new_qty
            pos.entry_time = pos.entry_time or fill.timestamp
            pos.entry_index = pos.entry_index if pos.entry_index >= 0 else fill.index
            pos.entry_reason = pos.entry_reason or fill.reason or fill.tag
            self._open_fees += fill.fee
        else:
            # Reduce, close or flip.
            closing_qty = min(abs(pos.qty), abs(signed))
            direction = 1.0 if pos.qty > 0 else -1.0
            gross = (fill.price - pos.avg_price) * closing_qty * direction
            # Allocate a proportional share of the entry fees to this close.
            entry_fee_share = self._open_fees * (closing_qty / abs(pos.qty)) if pos.qty else 0.0
            total_fees = entry_fee_share + fill.fee
            self._open_fees -= entry_fee_share
            self.realized_pnl += gross - fill.fee
            trade = TradeRecord(
                entry_time=pos.entry_time if pos.entry_time is not None else fill.timestamp,
                exit_time=fill.timestamp,
                side=Side.BUY if direction > 0 else Side.SELL,
                qty=closing_qty,
                entry_price=pos.avg_price,
                exit_price=fill.price,
                gross_pnl=gross,
                fees=total_fees,
                net_pnl=gross - total_fees,
                bars_held=max(0, fill.index - pos.entry_index),
                entry_reason=pos.entry_reason,
                exit_reason=fill.reason or fill.tag,
            )
            self._trades.append(trade)
            if self.log is not None:
                self.log.log(
                    "TRADE",
                    f"closed {trade.side.value} {closing_qty:g} net={trade.net_pnl:,.2f}",
                    timestamp=fill.timestamp,
                    index=fill.index,
                    **{k: v for k, v in trade.as_dict().items() if k not in ("entry_time", "exit_time")},
                )
            remaining = abs(signed) - closing_qty
            if remaining > 1e-12:
                # Flip: opening a new position in the opposite direction.
                pos.qty = (1.0 if signed > 0 else -1.0) * remaining
                pos.avg_price = fill.price
                pos.entry_time = fill.timestamp
                pos.entry_index = fill.index
                pos.entry_reason = fill.reason or fill.tag
                self._open_fees = fill.fee * (remaining / fill.qty)
            else:
                pos.qty = 0.0
                pos.avg_price = 0.0
                pos.entry_time = None
                pos.entry_index = -1
                pos.entry_reason = ""
        return trade

    # ------------------------------------------------------------------- marks
    def mark(self, timestamp: pd.Timestamp, price: float, index: int) -> float:
        """Mark the book to ``price`` and append one row to the equity curve."""
        self.set_mark(price)
        equity = self.equity
        self._equity_rows.append(
            {
                "timestamp": timestamp,
                "bar_index": index,
                "equity": equity,
                "cash": self.cash,
                "position": self.position.qty,
                "price": price,
                "realized_pnl": self.realized_pnl,
                "unrealized_pnl": equity - self.cash,
                "fees_paid": self.fees_paid,
            }
        )
        return equity

    # ------------------------------------------------------------------ output
    def equity_curve(self) -> pd.DataFrame:
        """Per-bar equity DataFrame indexed by timestamp."""
        if not self._equity_rows:
            return pd.DataFrame(columns=["equity", "cash", "position", "price"])
        return pd.DataFrame(self._equity_rows).set_index("timestamp")

    def trades(self) -> pd.DataFrame:
        """Completed round-trip trades (one row each)."""
        if not self._trades:
            return pd.DataFrame(columns=list(TradeRecord.__dataclass_fields__) + ["return_pct"])
        return pd.DataFrame([t.as_dict() for t in self._trades])

    def trades_raw(self) -> List[TradeRecord]:
        """TradeRecord objects (used by tests)."""
        return list(self._trades)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"Portfolio(cash={self.cash:,.2f}, position={self.position.qty:g}, equity={self.equity:,.2f})"
