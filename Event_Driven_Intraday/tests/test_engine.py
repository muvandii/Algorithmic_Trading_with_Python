"""Tests that encode the promises the lessons make.

Run from ``Event_Driven_Intraday/``:

    pytest -q

Every test name states the behaviour it protects. If you change the engine,
these are the contracts you must not break.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from intraday_engine import (  # noqa: E402
    AtrSizer,
    BacktestEngine,
    BaseStrategy,
    DataHandler,
    ExecutionModel,
    FixedFractionSizer,
    LookAheadError,
    Portfolio,
    Side,
    atr,
    detect_bos,
    detect_fvg,
    detect_sweep,
    make_ohlcv,
    make_pattern_sample,
    swing_points,
)
from intraday_engine.core import Fill  # noqa: E402


# ---------------------------------------------------------------------------
# Lesson 1 -- indexing and the look-ahead guard
# ---------------------------------------------------------------------------
def test_window_ends_at_t_and_never_contains_t_plus_1():
    df = make_ohlcv(50, seed=1)
    dh = DataHandler(df)
    dh.set_cursor(10)
    w = dh.window(10, 5)
    assert len(w) == 5
    assert w.index[-1] == df.index[10]
    assert w["close"].iloc[-1] == df["close"].iloc[10]
    assert df.index[11] not in w.index


def test_reading_future_bar_raises_lookahead_error():
    df = make_ohlcv(50, seed=1)
    dh = DataHandler(df)
    dh.set_cursor(10)
    with pytest.raises(LookAheadError):
        dh.bar(11)
    with pytest.raises(LookAheadError):
        dh.window(11, 5)


def test_previous_bar_access_is_allowed_and_correct():
    df = make_ohlcv(30, seed=2)
    dh = DataHandler(df)
    dh.set_cursor(7)
    prev = dh.window_before(7, 1)["close"].iloc[-1]
    assert prev == pytest.approx(df["close"].iloc[6])


def test_datahandler_rejects_naive_or_unsorted_index():
    df = make_ohlcv(10, seed=3)
    naive = df.copy()
    naive.index = naive.index.tz_localize(None)
    with pytest.raises(ValueError, match="tz-aware"):
        DataHandler(naive)
    unsorted = df.iloc[::-1]
    with pytest.raises(ValueError, match="sorted"):
        DataHandler(unsorted)


# ---------------------------------------------------------------------------
# Lesson 3 -- structure detectors (expected rows are documented in the module)
# ---------------------------------------------------------------------------
def test_fvg_is_detected_exactly_when_third_bar_completes_it():
    df = make_pattern_sample()
    assert detect_fvg(df.iloc[:10]) is None  # only 2 of 3 bars available
    fvg = detect_fvg(df.iloc[:11])
    assert fvg is not None
    assert fvg.index == 10
    assert (fvg.lower, fvg.upper) == (101.00, 101.20)
    assert detect_fvg(df.iloc[:9]) is None  # pattern has not started


def test_liquidity_sweep_detected_at_row_17_only_after_close():
    df = make_pattern_sample()
    assert detect_sweep(df.iloc[:17], lookback=20) is None  # bar 16 has no sweep yet
    sweep = detect_sweep(df.iloc[:18], lookback=20)
    assert sweep is not None
    assert sweep["direction"] == "bullish"
    assert sweep["level"] == pytest.approx(100.55)
    assert sweep["index"] == 17


def test_break_of_structure_confirmed_on_close_not_wick():
    df = make_pattern_sample()
    assert detect_bos(df.iloc[:19], short_len=10) is None  # row 18 close 100.85 < 101.45
    bos = detect_bos(df.iloc[:20], short_len=10)
    assert bos is not None and bos["direction"] == "bullish"
    assert bos["level"] == pytest.approx(101.45)


def test_swings_are_only_reported_with_enough_confirmation_bars():
    df = make_pattern_sample()
    # With right=1, a swing at row k needs bar k+1 -> bar 10 high is unconfirmed at row 10.
    unconfirmed = {s.index for s in swing_points(df.iloc[:12], left=2, right=2)}
    assert 10 not in unconfirmed  # bar 11 is not enough: needs bars 9,10,11,12
    confirmed = {s.index for s in swing_points(df.iloc[:13], left=2, right=2)}
    assert 10 in confirmed


# ---------------------------------------------------------------------------
# Lesson 4 -- execution, costs, intrabar ambiguity
# ---------------------------------------------------------------------------
class OneTradeStrategy(BaseStrategy):
    """Buy once at bar ``entry_bar`` with a bracket, then do nothing."""

    warmup = 1

    def __init__(self, entry_bar=2, stop=95.0, target=110.0, **kw):
        super().__init__(**kw)
        self.entry_bar = entry_bar
        self.stop, self.target = stop, target

    def generate(self, ctx):
        if ctx.bar.index == self.entry_bar and ctx.is_flat:
            return {"side": "buy", "stop": self.stop, "target": self.target, "reason": "test"}
        return None


def _flat_frame(rows, start="2024-01-02 14:00"):
    """Build OHLCV rows from (o, h, l, c) tuples."""
    idx = pd.date_range(start, periods=len(rows), freq="5min", tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 1000
    return df


def test_market_order_fills_at_next_bar_open_not_signal_bar_close():
    df = _flat_frame(
        [
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 101, 99, 100),   # signal bar (index 2)
            (102, 103, 101, 102),  # fill here, at this OPEN
            (102, 103, 101, 102),
            (102, 103, 101, 102),
        ]
    )
    model = ExecutionModel(fee_bps=0, slippage_bps=0, min_fee=0)
    strat = OneTradeStrategy(entry_bar=2, stop=95, target=120, sizer=FixedFractionSizer(risk_pct=0.01))
    res = BacktestEngine.build(df, strat, initial_cash=10_000, model=model).run()
    entry = res.fills.iloc[0]
    assert entry["bar_index"] == 3
    assert entry["price"] == pytest.approx(102.0)
    assert entry["timestamp"] == df.index[3]


def test_fees_and_slippage_are_charged_explicitly():
    df = _flat_frame([(100, 100, 100, 100)] * 4 + [(100, 100, 100, 100)])
    model = ExecutionModel(fee_bps=10, slippage_bps=5, min_fee=0)
    strat = OneTradeStrategy(entry_bar=1, stop=90, target=200, sizer=FixedFractionSizer(risk_pct=0.01))
    res = BacktestEngine.build(df, strat, initial_cash=10_000, model=model).run()
    f = res.fills.iloc[0]
    assert f["price"] == pytest.approx(100 * (1 + 5 / 10_000))
    assert f["fee"] == pytest.approx(f["notional"] * 10 / 10_000)
    assert res.portfolio.cash < 10_000


def test_when_stop_and_target_hit_in_same_bar_conservative_takes_the_stop():
    df = _flat_frame(
        [
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),  # signal
            (100, 112, 94, 100),      # entry at open; both 95 stop and 110 target touched
            (100, 101, 99, 100),
        ]
    )
    model = ExecutionModel(fee_bps=0, slippage_bps=0, stop_slippage_bps=0, min_fee=0)
    strat = OneTradeStrategy(entry_bar=2, stop=95, target=110, sizer=FixedFractionSizer(risk_pct=0.01))
    res = BacktestEngine.build(df, strat, initial_cash=10_000, model=model, ambiguity="conservative").run()
    assert res.trades.iloc[0]["exit_reason"] == "stop"
    assert res.trades.iloc[0]["net_pnl"] < 0
    # The optimistic assumption is only for measuring the ambiguity, never for shipping.
    strat2 = OneTradeStrategy(entry_bar=2, stop=95, target=110, sizer=FixedFractionSizer(risk_pct=0.01))
    res2 = BacktestEngine.build(df, strat2, initial_cash=10_000, model=model, ambiguity="optimistic").run()
    assert res2.trades.iloc[0]["exit_reason"] == "take_profit"


def test_gap_through_stop_fills_at_open_not_at_stop_price():
    df = _flat_frame(
        [
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),  # signal at close 100, stop 95
            (100, 101, 99, 100),      # entry at 100
            (90, 91, 89, 90),         # gap below stop: must fill at 90, not 95
        ]
    )
    model = ExecutionModel(fee_bps=0, slippage_bps=0, stop_slippage_bps=0, min_fee=0)
    strat = OneTradeStrategy(entry_bar=2, stop=95, target=120, sizer=FixedFractionSizer(risk_pct=0.01))
    res = BacktestEngine.build(df, strat, initial_cash=10_000, model=model).run()
    stop_fill = res.fills[res.fills["reason"] == "stop"].iloc[0]
    assert stop_fill["price"] == pytest.approx(90.0)
    # Nominal risk was 1% of 10k = $100; the gap made the realised loss $200.
    assert res.trades.iloc[0]["net_pnl"] == pytest.approx(-200.0)


def test_limit_entry_only_fills_when_price_trades_through_it():
    df = _flat_frame(
        [
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),
            (100, 100.5, 99.5, 100),  # signal: limit buy at 98
            (100, 101, 99.5, 100),    # never reaches 98 -> no fill
            (100, 101, 97.5, 100),    # touches 98 -> fill at 98
        ]
    )
    class LimitStrat(BaseStrategy):
        warmup = 1
        def generate(self, ctx):
            if ctx.bar.index == 2 and ctx.is_flat:
                return {"side": "buy", "stop": 95, "target": 105, "order_type": "limit",
                        "limit_price": 98.0, "expires_after": 5, "reason": "limit_test"}
            return None

    model = ExecutionModel(fee_bps=0, slippage_bps=0, min_fee=0)
    res = BacktestEngine.build(df, LimitStrat(sizer=FixedFractionSizer(risk_pct=0.01)), initial_cash=10_000, model=model).run()
    entry = res.fills.iloc[0]
    assert entry["bar_index"] == 4
    assert entry["price"] == pytest.approx(98.0)


# ---------------------------------------------------------------------------
# Accounting and sizing
# ---------------------------------------------------------------------------
def test_long_round_trip_pnl_and_equity_identity():
    pf = Portfolio(initial_cash=10_000)
    t0 = pd.Timestamp("2024-01-02 14:00", tz="UTC")
    pf.apply_fill(Fill(t0, 0, 1, Side.BUY, 10, 100.0, fee=1.0))
    pf.set_mark(110.0)
    assert pf.equity == pytest.approx(10_000 - 1000 - 1 + 10 * 110)
    trade = pf.apply_fill(Fill(t0 + pd.Timedelta("5min"), 1, 2, Side.SELL, 10, 110.0, fee=1.0))
    assert trade is not None
    assert trade.gross_pnl == pytest.approx(100.0)
    assert trade.net_pnl == pytest.approx(98.0)
    assert pf.cash == pytest.approx(10_000 - 1000 - 1 + 1100 - 1)
    assert pf.position.is_flat


def test_short_round_trip_profits_when_price_falls():
    pf = Portfolio(initial_cash=10_000)
    t0 = pd.Timestamp("2024-01-02 14:00", tz="UTC")
    pf.apply_fill(Fill(t0, 0, 1, Side.SELL, 10, 100.0, fee=0))
    pf.set_mark(90.0)
    trade = pf.apply_fill(Fill(t0, 1, 2, Side.BUY, 10, 90.0, fee=0))
    assert trade is not None and trade.net_pnl == pytest.approx(100.0)


def test_fixed_fraction_sizer_risks_exactly_the_budget():
    s = FixedFractionSizer(risk_pct=0.02)
    qty = s.size(equity=50_000, entry_price=100, stop_price=95)
    assert qty * 5 == pytest.approx(50_000 * 0.02)


def test_atr_sizer_shrinks_size_when_volatility_expands():
    s = AtrSizer(risk_pct=0.01, atr_mult=2.0)
    calm = s.size(equity=100_000, entry_price=100, atr=0.5)
    wild = s.size(equity=100_000, entry_price=100, atr=2.0)
    assert wild < calm
    assert calm * (2.0 * 0.5) == pytest.approx(1000)


def test_atr_is_causal_and_nan_during_warmup():
    df = make_ohlcv(60, seed=5)
    a = atr(df, 14)
    assert a.iloc[:13].isna().all()
    assert pd.notna(a.iloc[14])
    # Recomputing on a truncated frame must not change past values.
    a_short = atr(df.iloc[:40], 14)
    pd.testing.assert_series_equal(a.iloc[:40], a_short, check_names=False)


# ---------------------------------------------------------------------------
# Lesson 5 -- engine-level guarantees
# ---------------------------------------------------------------------------
def test_full_run_is_deterministic():
    def run():
        df = make_ohlcv(800, seed=21)
        from intraday_engine import SweepBosFvgStrategy
        strat = SweepBosFvgStrategy(sizer=FixedFractionSizer(risk_pct=0.01))
        res = BacktestEngine.build(df, strat, initial_cash=50_000).run()
        return res.equity["equity"].to_numpy(), len(res.trades)

    eq1, n1 = run()
    eq2, n2 = run()
    assert n1 == n2
    np.testing.assert_allclose(eq1, eq2)


def test_strategy_cannot_read_the_future_during_a_full_run():
    class Cheater(BaseStrategy):
        warmup = 1
        def generate(self, ctx):
            # A classic look-ahead bug: "just peek at tomorrow's close".
            self.data.bar(ctx.bar.index + 1)
            return None

    df = make_ohlcv(20, seed=8)
    engine = BacktestEngine.build(df, Cheater(), initial_cash=10_000)
    with pytest.raises(LookAheadError):
        engine.run()


def test_order_submitted_at_t_never_fills_within_t():
    class Recorder(BaseStrategy):
        warmup = 1
        def __init__(self, **kw):
            super().__init__(**kw)
            self.submitted_at = None
        def generate(self, ctx):
            if ctx.bar.index == 3 and ctx.is_flat:
                self.submitted_at = ctx.bar.index
                return {"side": "buy", "stop": 90, "target": 130, "reason": "t3"}
            return None

    df = make_ohlcv(12, seed=4)
    strat = Recorder(sizer=FixedFractionSizer(risk_pct=0.01))
    res = BacktestEngine.build(df, strat, initial_cash=10_000).run()
    assert strat.submitted_at == 3
    assert res.fills.iloc[0]["bar_index"] == 4


def test_invalid_order_is_rejected_with_a_reason_in_the_journal():
    class BadStrat(BaseStrategy):
        warmup = 1
        def generate(self, ctx):
            if ctx.bar.index == 2 and ctx.is_flat:
                return {"side": "buy", "stop": 105, "target": 110, "reason": "bad_stop"}
            return None

    df = make_ohlcv(10, seed=6)
    res = BacktestEngine.build(df, BadStrat(sizer=FixedFractionSizer(risk_pct=0.01)), initial_cash=10_000).run()
    rej = res.rejections()
    assert not rej.empty
    assert any("wrong side" in m for m in rej["message"])


def test_logger_schema_has_the_documented_columns():
    df = make_ohlcv(30, seed=9)
    from intraday_engine import SweepBosFvgStrategy
    res = BacktestEngine.build(
        df, SweepBosFvgStrategy(sizer=FixedFractionSizer(risk_pct=0.01)), initial_cash=10_000
    ).run()
    for col in ("timestamp", "bar_index", "kind", "message"):
        assert col in res.events.columns
    assert str(res.events["timestamp"].dt.tz) == "UTC"
