"""BacktestEngine: the 30-line conductor that wires the components together.

Order of operations for every bar t (this order *is* the anti-look-ahead rule)
---------------------------------------------------------------------------
1. data.set_cursor(t)             -- future reads now raise LookAheadError
2. strategy.on_bar(ctx <= t)      -- strategy may submit orders, which are queued
3. execution.process_bar(bar t)   -- exiting positions first, then resting orders
                                     fill at bar t prices *only if* they were
                                     placed on an earlier bar
4. portfolio.mark(t, close)       -- one equity row per bar

Because orders submitted in step 2 can only fill in step 3 of a *later* bar
(market orders fill at the next open), a strategy can never trade on a price
it could not have known. That single rule kills 90% of look-ahead bugs.

Run modes
---------
* Batch: iterate the whole DataFrame (default) -- O(n) time, O(n) memory for
  the equity curve.
* Streaming: call ``engine.step(bar)`` as bars arrive from a websocket/CSV
  tailer; the strategy is unchanged. Keep only ``warmup + 1`` rows to bound
  memory (see ``DataHandler.window``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from .core import Fill
from .data import DataHandler
from .execution import ExecutionEngine, ExecutionModel
from .journal import EventLogger
from .portfolio import Portfolio
from .strategy import Context, Strategy


@dataclass
class BacktestResult:
    """Everything you need to evaluate (and debug) a run."""

    equity: pd.DataFrame
    trades: pd.DataFrame
    events: pd.DataFrame
    fills: pd.DataFrame
    portfolio: Portfolio
    data: DataHandler

    def summary(self) -> Dict[str, Any]:
        """Headline metrics. Deliberately plain: compute your own edge metrics too."""
        eq = self.equity["equity"]
        if len(eq) < 2:
            return {"trades": len(self.trades)}
        rets = eq.pct_change().dropna()
        peak = eq.cummax()
        dd = (eq / peak - 1.0).min()
        days = (eq.index[-1] - eq.index[0]).total_seconds() / 86400 or 1.0
        total_return = eq.iloc[-1] / eq.iloc[0] - 1.0
        bar_seconds = float(pd.Series(eq.index).diff().median().total_seconds() or 300.0)
        # Annualise with *trading* time: a session-filtered equity series has
        # ~78 five-minute bars per day, not 288. Using calendar 24/7 periods
        # would inflate the Sharpe of an intraday strategy.
        per_day = eq.groupby(eq.index.date).size().median()
        covered_seconds = float(per_day * bar_seconds)
        days_per_year = 252.0 if covered_seconds < 0.8 * 86400 else 365.0
        periods_per_year = days_per_year * float(per_day)
        trades = self.trades
        wins = trades[trades["net_pnl"] > 0] if not trades.empty else trades
        losses = trades[trades["net_pnl"] <= 0] if not trades.empty else trades
        gross_win = float(wins["net_pnl"].sum()) if len(wins) else 0.0
        gross_loss = float(-losses["net_pnl"].sum()) if len(losses) else 0.0
        return {
            "start": eq.index[0],
            "end": eq.index[-1],
            "n_bars": len(eq),
            "trades": int(len(trades)),
            "total_return": float(total_return),
            "cagr": float((1 + total_return) ** (365.0 / days) - 1) if total_return > -1 else -1.0,
            "max_drawdown": float(dd),
            "sharpe_ann": float(rets.mean() / rets.std() * periods_per_year ** 0.5) if rets.std() > 0 else 0.0,
            "win_rate": float(len(wins) / len(trades)) if len(trades) else 0.0,
            "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
            "fees_paid": float(self.equity["fees_paid"].iloc[-1]) if "fees_paid" in self.equity else 0.0,
            "avg_bars_held": float(trades["bars_held"].mean()) if len(trades) else 0.0,
            "open_position": float(self.portfolio.position.qty),
        }

    def rejections(self) -> pd.DataFrame:
        """All rejected orders with reasons (a great first debugging stop)."""
        ev = self.events
        return ev[ev["kind"] == "REJECT"].reset_index(drop=True) if not ev.empty else ev


@dataclass
class BacktestEngine:
    """Compose DataHandler + Strategy + ExecutionEngine + Portfolio + Logger."""

    data: DataHandler
    strategy: Strategy
    portfolio: Portfolio
    execution: ExecutionEngine
    logger: EventLogger
    log_bars: bool = False

    @classmethod
    def build(
        cls,
        df: pd.DataFrame,
        strategy: Strategy,
        initial_cash: float = 100_000.0,
        model: Optional[ExecutionModel] = None,
        ambiguity: str = "conservative",
        symbol: str = "SYMBOL",
        log_bars: bool = False,
        logger: Optional[EventLogger] = None,
    ) -> "BacktestEngine":
        """Assemble the five components with sensible defaults."""
        log = logger or EventLogger(verbose=False, log_bars=log_bars)
        data = DataHandler(df, symbol=symbol)
        portfolio = Portfolio(initial_cash=initial_cash, symbol=symbol, log=log)
        execution = ExecutionEngine(
            data=data,
            portfolio=portfolio,
            logger=log,
            model=model or ExecutionModel(),
            ambiguity=ambiguity,
        )
        return cls(data=data, strategy=strategy, portfolio=portfolio, execution=execution, logger=log, log_bars=log_bars)

    # --------------------------------------------------------------------- run
    def run(self, flatten_at_end: bool = True) -> BacktestResult:
        """Iterate every bar once, in order. Deterministic by construction.

        ``flatten_at_end`` liquidates any still-open position at the final close
        (with slippage) so trade statistics are complete. Set it to False only
        when studying overnight carry explicitly.
        """
        self.logger.log("NOTE", "backtest start", timestamp=self.data.timestamps[0], index=-1,
                        n_bars=self.data.n_bars, initial_cash=self.portfolio.initial_cash)
        self.strategy.on_start(self.data, self.logger)
        for i in range(self.data.n_bars):
            self.step(i)
        if flatten_at_end and not self.portfolio.position.is_flat:
            last = self.data.bar(self.data.n_bars - 1)
            fills = self.execution.flatten(last)
            self.logger.log("NOTE", "flattened open position at end of test",
                            timestamp=last.timestamp, index=last.index, qty=fills[0].qty if fills else 0.0)
            ctx = Context(bar=last, history=self.data.window(last.index, last.index + 1),
                          portfolio=self.portfolio, state=self.strategy.state)
            for fill in fills:
                self.strategy.on_fill(fill, ctx)   # keep the state machine truthful
            self.portfolio.mark(last.timestamp, last.close, last.index)
        self.logger.log("NOTE", "backtest end", timestamp=self.data.timestamps[-1], index=self.data.n_bars - 1)
        self.strategy.on_finish(self.portfolio, self.logger)
        return self.result()

    def step(self, i: int) -> None:
        """Process exactly one bar (also the entry point for streaming mode)."""
        self.data.set_cursor(i)  # (1) future reads now raise
        bar = self.data.bar(i)
        history = self.data.window(i, i + 1)  # growing view; use tail(n) in strategies
        ctx = Context(bar=bar, history=history, portfolio=self.portfolio, state=self.strategy.state)
        self.logger.bar(bar.timestamp, i, close=bar.close, position=self.portfolio.position.qty)
        orders = self.strategy.on_bar(ctx) or []
        if not isinstance(orders, list):
            orders = [orders]
        for order in orders:
            if self.portfolio.position.is_flat or order.tag.startswith("exit"):
                self.execution.submit(order, bar)
        new_fills: List[Fill] = self.execution.process_bar(bar)
        for fill in new_fills:
            self.strategy.on_fill(fill, ctx)
        for order, reason in self.execution.drain_rejections():
            self.strategy.on_reject(order, ctx, reason)
        self.portfolio.mark(bar.timestamp, bar.close, i)

    # ------------------------------------------------------------------ output
    def result(self) -> BacktestResult:
        """Package the run into DataFrames (cheap; safe to call repeatedly)."""
        equity = self.portfolio.equity_curve()
        fills = pd.DataFrame([f.as_dict() for f in self.execution.fills]) if self.execution.fills else pd.DataFrame()
        return BacktestResult(
            equity=equity,
            trades=self.portfolio.trades(),
            events=self.logger.to_frame(),
            fills=fills,
            portfolio=self.portfolio,
            data=self.data,
        )

