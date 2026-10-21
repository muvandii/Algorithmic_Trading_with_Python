"""intraday_engine -- a small, auditable event-driven intraday backtester.

The five components and their one-line responsibilities:

    DataHandler      validated OHLCV + a cursor that makes look-ahead raise
    Strategy         decisions only: sees Context(history <= t), returns Orders
    ExecutionEngine  accepts Orders, produces Fills under conservative rules
    Portfolio        cash/position accounting, equity curve, trade log
    EventLogger      structured journal of everything that happened

Public API
----------
    from intraday_engine import (
        Bar, Order, OrderType, Side, Fill, TradeRecord, Event, LookAheadError,
        DataHandler, ExecutionModel, ExecutionEngine, Portfolio, EventLogger,
        BacktestEngine, BacktestResult,
        FixedFractionSizer, AtrSizer, atr,
        detect_sweep, detect_bos, detect_fvg, active_fvgs, swing_points,
        make_ohlcv, load_ohlcv_csv, resample_ohlcv, session_filter,
    )
"""

from .core import Bar, Event, Fill, LookAheadError, Order, OrderRejected, OrderType, Side, TradeRecord
from .data import DataHandler, load_ohlcv_csv, resample_ohlcv, session_filter
from .engine import BacktestEngine, BacktestResult
from .execution import ExecutionEngine, ExecutionModel
from .journal import EventLogger
from .portfolio import Portfolio, Position
from .sizing import AtrSizer, FixedFractionSizer, Sizer, atr
from .strategies import SweepBosFvgParams, SweepBosFvgStrategy
from .strategy import BaseStrategy, Context, Strategy
from .structure import Fvg, Swing, active_fvgs, detect_bos, detect_fvg, detect_sweep, last_swing, swing_points
from .synthetic import make_ohlcv, make_pattern_sample

__all__ = [
    "Bar", "Event", "Fill", "LookAheadError", "Order", "OrderRejected", "OrderType", "Side", "TradeRecord",
    "DataHandler", "load_ohlcv_csv", "resample_ohlcv", "session_filter",
    "BacktestEngine", "BacktestResult",
    "ExecutionEngine", "ExecutionModel",
    "EventLogger", "Portfolio", "Position",
    "AtrSizer", "FixedFractionSizer", "Sizer", "atr",
    "BaseStrategy", "Context", "Strategy", "SweepBosFvgParams", "SweepBosFvgStrategy",
    "Fvg", "Swing", "active_fvgs", "detect_bos", "detect_fvg", "detect_sweep", "last_swing", "swing_points",
    "make_ohlcv", "make_pattern_sample",
]

__version__ = "1.0.0"
