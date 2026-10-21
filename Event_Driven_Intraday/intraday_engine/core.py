"""Core value objects shared by every component of the backtester.

Nothing in this module knows about pandas DataFrames, strategies or brokers --
it only defines the vocabulary (Bar, Order, Fill, TradeRecord, Event) that the
DataHandler, Strategy, ExecutionEngine, Portfolio and EventLogger exchange.

Keeping these tiny and immutable is what makes the components swappable:
a live broker adapter only has to produce ``Fill`` objects and consume
``Order`` objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

import pandas as pd


class LookAheadError(RuntimeError):
    """Raised when strategy code tries to read data with index > current bar.

    This is a *feature*: the backtester turns the most common backtest bug
    (using the future) into a loud, immediate exception instead of a beautiful
    equity curve that cannot be traded.
    """


class OrderRejected(RuntimeError):
    """Raised (and logged) when an order cannot be accepted."""


class Side(str, Enum):
    """Direction of an order or a position."""

    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        """+1 for BUY, -1 for SELL. Handy for position arithmetic."""
        return 1 if self is Side.BUY else -1

    @property
    def exit_side(self) -> "Side":
        """The side you must trade to close a position opened on this side."""
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(str, Enum):
    """Supported order types (deliberately few: they cover 95% of retail use)."""

    MARKET = "market"
    LIMIT = "limit"


@dataclass(frozen=True)
class Bar:
    """One completed OHLCV bar. Immutable: a bar never changes once closed."""

    index: int
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def range(self) -> float:
        """High minus low."""
        return self.high - self.low

    @property
    def body(self) -> float:
        """Absolute close minus open."""
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        """True when close >= open."""
        return self.close >= self.open

    def as_dict(self) -> Dict[str, Any]:
        """Flat dict for logging / DataFrame construction."""
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass
class Order:
    """An order *intent*. It is not a fill; the ExecutionEngine decides that.

    Parameters
    ----------
    side, qty:
        Direction and size (always positive; direction lives in ``side``).
    type:
        MARKET (fill at next bar open) or LIMIT (fill only if price trades
        through ``limit_price``).
    limit_price:
        Required for LIMIT orders.
    stop_price, take_profit_price:
        Optional bracket attached to the *entry*. Once the entry fills, the
        ExecutionEngine protects the position with these levels.
    tag:
        Free-text label used in the journal, e.g. ``"entry:sweep_fvg"``.
    expires_after:
        Number of bars the order may rest before being cancelled.
    """

    side: Side
    qty: float
    type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    tag: str = ""
    submitted_index: int = -1
    expires_after: Optional[int] = None
    id: int = 0


@dataclass(frozen=True)
class Fill:
    """A confirmed execution: the bridge between orders and accounting."""

    timestamp: pd.Timestamp
    index: int
    order_id: int
    side: Side
    qty: float
    price: float
    fee: float = 0.0
    slippage_cost: float = 0.0
    reason: str = ""
    tag: str = ""

    @property
    def notional(self) -> float:
        """Absolute traded notional."""
        return self.qty * self.price

    def as_dict(self) -> Dict[str, Any]:
        """Flat record with the exact schema documented in the lessons."""
        return {
            "timestamp": self.timestamp,
            "bar_index": self.index,
            "order_id": self.order_id,
            "side": self.side.value,
            "qty": self.qty,
            "price": self.price,
            "notional": self.notional,
            "fee": self.fee,
            "slippage_cost": self.slippage_cost,
            "reason": self.reason,
            "tag": self.tag,
        }


@dataclass(frozen=True)
class TradeRecord:
    """A round-trip trade (entry -> flat), net of fees and slippage."""

    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    side: Side
    qty: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    fees: float
    net_pnl: float
    bars_held: int
    entry_reason: str
    exit_reason: str

    @property
    def return_pct(self) -> float:
        """Net PnL as a fraction of entry notional."""
        notional = self.entry_price * self.qty
        return self.net_pnl / notional if notional else 0.0

    def as_dict(self) -> Dict[str, Any]:
        """Flat record; one row per completed trade."""
        return {
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "side": self.side.value,
            "qty": self.qty,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "gross_pnl": self.gross_pnl,
            "fees": self.fees,
            "net_pnl": self.net_pnl,
            "return_pct": self.return_pct,
            "bars_held": self.bars_held,
            "entry_reason": self.entry_reason,
            "exit_reason": self.exit_reason,
        }


@dataclass
class Event:
    """One line of the journal. Everything the system does becomes an Event."""

    timestamp: pd.Timestamp
    index: int
    kind: str  # BAR | SIGNAL | STATE | ORDER | FILL | REJECT | TRADE | NOTE | ERROR
    message: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """Flat record for ``pd.DataFrame`` or JSONL output."""
        return {
            "timestamp": self.timestamp,
            "bar_index": self.index,
            "kind": self.kind,
            "message": self.message,
            **self.payload,
        }
