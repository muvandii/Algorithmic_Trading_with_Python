"""Notebook 04 — execution and risk."""

from __future__ import annotations

from .common import Notebook, header, note, section

FILENAME = "04_execution_and_risk.ipynb"
TITLE = "Trade execution and risk"


def build() -> Notebook:
    """Return Lesson 4."""
    nb = Notebook(TITLE)
    nb.md(header(4, "Trade execution and risk",
                 "A signal is an opinion. A trade is a size, a stop, a target, a fee and a fill."))
    nb.setup()

    nb.md(section(1, "Learning objectives"))
    nb.md(
        """
By the end of this lesson you can:

1. **Size** a position from a risk budget using both fixed-fraction and ATR-based methods, and switch between them in one line.
2. **Build** a bracket order (entry, stop, take-profit) and compute R multiples and break-even win rates *net of costs*.
3. **Model** fees and slippage explicitly and show how they change expectancy.
4. **Resolve** intrabar ambiguity conservatively (stop before target) and describe how to upgrade to microbar simulation.
5. **Distinguish** signal from execution: the same signal filled as a market order or a limit order produces different results.
"""
    )

    nb.md(section(2, "Key concepts and definitions"))
    nb.md(
        """
| Term | Meaning |
|---|---|
| **Signal** | A decision to want exposure. Not an order. |
| **Execution** | Turning intent into fills: order type, venue, timing, price. |
| **Market order** | Takes liquidity; fills at the next available price with adverse slippage. |
| **Limit order** | Provides liquidity; fills only if the market trades through your price. No guarantee. |
| **Bracket** | Entry + stop-loss + take-profit as one logical unit. |
| **Stop-loss** | A trigger to exit a losing position; becomes a market order when hit (hence slippage and gaps). |
| **Take-profit** | A resting limit exit at a target price. |
| **R** | Initial risk in price = `|entry − stop|`. A 2R target is twice the risk. |
| **Position size** | Units = `(equity × risk%) / stop_distance`, capped by leverage. |
| **Fixed-fraction sizing** | Risk a constant fraction of *current* equity per trade. |
| **ATR sizing** | Stop distance = `k × ATR(period)`; size shrinks when volatility expands. |
| **Slippage** | Difference between the price you wanted and the price you got. |
| **Fee (bps)** | Commission as basis points of notional (1 bp = 0.01%). |
| **Spread** | Bid/ask difference; a cost even when commission is zero. |
| **Gap risk** | The next bar opens beyond your stop; you fill at the open, not the stop. |
| **Intrabar ambiguity** | OHLC does not say whether the high or the low came first. |
| **Conservative fill** | The assumption that hurts the strategy (stop first, adverse slippage, no price improvement). |
| **Microbar simulation** | Decomposing a bar into sub-intervals to approximate the true path. |
| **Expectancy** | Average PnL per trade = `p·win − (1−p)·loss` (in R, net of costs). |
| **Break-even win rate** | `1 / (1 + R)` for a symmetric bracket, before costs. |
| **Capacity** | How much size the market can absorb without moving away from you. |
"""
    )

    nb.md(section(3, "Step-by-step walkthrough"))
    nb.md(
        """
### 3.1 From signal to trade

| Step | Input | Output | Rule |
|---|---|---|---|
| 1 | signal + levels | stop distance `D` | `D = |entry_ref − stop|`, must be > 0 |
| 2 | equity, risk % | quantity | `qty = equity × risk% / D`, capped at `equity × max_leverage / price` |
| 3 | quantity, price | notional | `qty × price`; check fees as a fraction of R |
| 4 | order type | market or limit | market → next open; limit → only if touched, no improvement |
| 5 | bracket | stop, target | stop below the sweep low for longs; target = entry + R multiple × D |
| 6 | ambiguity | fill sequence | both touched in one bar ⇒ **stop first** (conservative) |
| 7 | accounting | cash, position, fees | applied by the portfolio, not by the strategy |

### 3.2 The sizing formula and what it protects you from

```
risk_budget = equity × risk_pct
qty         = risk_budget / |entry − stop|
```

If the stop is 1% away and you risk 1% of equity, your notional is 100% of
equity. If the stop is 5% away, notional is 20%. This is why tight stops do not
magically reduce risk — they increase size. Two guards are mandatory:

- `max_leverage`: `qty × price ≤ equity × max_leverage`;
- `lot_step`: floor to the venue's lot size (never round risk *up*).

ATR sizing replaces `|entry − stop|` with `k × ATR` (or the tighter of the two),
so the same risk budget buys fewer units in volatile markets.

### 3.3 Costs, in the units that matter

| Cost | Formula | On a \\$50k trade at 2 bps |
|---|---|---|
| Commission | `notional × fee_bps / 10,000` | \\$10 |
| Slippage (entry) | `notional × slippage_bps / 10,000` | \\$5 at 1 bp |
| Slippage (stop exit) | `notional × stop_slippage_bps / 10,000` | \\$20 at 4 bps |
| **Round trip** | | **≈ \\$35** |

Express costs as a fraction of R, not of notional, because R is what you are
risking:

```
cost_in_R = round_trip_cost / (qty × D) = round_trip_bps / (10,000 × stop_pct)
```

A 0.5% stop and a 7 bp round trip costs `0.0007 / 0.005 = 0.14R` per trade — 14%
of your edge, before you have any edge.

### 3.4 Intrabar ambiguity: the rule and the upgrade path

A 5-min bar with `high = 101.6` and `low = 99.4` does not tell you whether the
stop at 99.8 or the target at 101.2 was hit first. Three options:

| Option | Rule | Bias |
|---|---|---|
| A. Conservative (implemented) | stop wins any tie | pessimistic, defensible |
| B. Optimistic | target wins any tie | flattering, never ship it |
| C. Microbar / tick | simulate the path inside the bar | closest to reality, needs data |

Implement A by default. Measure B to know the value of your ignorance. Upgrade
to C only when the cost of being wrong exceeds the cost of the data.

**How to upgrade:** replace `_manage_brackets` with a path simulator:

```python
def micro_path(bar, n=20, seed=0):
    rng = np.random.default_rng(seed)
    # Brownian bridge from open to close, constrained by the bar's high/low
    ...
```

then step through the micro prices and take the first level touched. Seed by
`bar.index` for determinism. This notebook includes a compact version to show
the mechanics (section 5.6).

### 3.5 Signal vs execution: the same idea, three outcomes

| Execution | Fill | Fill rate | Typical bias |
|---|---|---|---|
| Market at next open | always, with slippage | 100% | pays spread, no chase risk |
| Limit at the signal price | only if revisited | 30–70% | adverse selection: fills when wrong |
| Limit at FVG midpoint | only on pullback | 20–60% | better price, misses runners |

The limit versions usually *look* better per trade and worse in total, because
they systematically miss the trades that never come back. Always report fill
rate alongside expectancy.
"""
    )

    nb.md(section(4, "Data and API conventions"))
    nb.md(
        """
### Order fields

| Field | Type | Notes |
|---|---|---|
| `side` | `buy`/`sell` | direction of the *order* |
| `qty` | float > 0 | always positive; direction is `side` |
| `type` | `market`/`limit` | market fills next open; limit only if touched |
| `limit_price` | float or None | required for limit |
| `stop_price` | float or None | attached bracket after the entry fills |
| `take_profit_price` | float or None | must be on the profitable side |
| `tag` | str | `entry:<reason>` or `exit:<reason>` |
| `expires_after` | int or None | bars until cancellation |

### Fill record

| Field | Meaning |
|---|---|
| `timestamp`, `bar_index` | when it filled (bar-open time) |
| `side`, `qty`, `price` | what traded |
| `notional` | `qty × price` |
| `fee` | commission charged |
| `slippage_cost` | `|price − reference| × qty` |
| `reason` | `market`, `limit`, `stop`, `take_profit` |
| `tag` | strategy label |

### Trade record

`entry_time, exit_time, side, qty, entry_price, exit_price, gross_pnl, fees,
net_pnl, return_pct, bars_held, entry_reason, exit_reason`.

### `ExecutionModel` defaults

| Parameter | Default | Meaning |
|---|---|---|
| `fee_bps` | 2.0 | taker fee |
| `maker_fee_bps` | 0.0 | passive fee (can be negative = rebate) |
| `min_fee` | 0.0 | per-fill minimum |
| `slippage_bps` | 1.0 | market orders |
| `stop_slippage_bps` | 3.0 | stop exits |

Change them for your venue. Crypto spot is often 5–10 bps taker with 1–2 bps
slippage on liquid pairs; US equities can be near zero commission with 1–3 bps
of spread cost; futures are per-contract.
"""
    )

    nb.md(section(5, "Minimal runnable code"))
    nb.md("### 5.1 Sizing: fixed fraction vs ATR")
    nb.code(
        """
equity, entry, stop, price = 100_000.0, 100.0, 98.0, 100.0
fixed = FixedFractionSizer(risk_pct=0.01, max_leverage=1.0)
atr_s = AtrSizer(risk_pct=0.01, atr_mult=1.5, max_leverage=1.0)

atr_value = 0.8   # from bars <= t
q_fixed = fixed.size(equity=equity, entry_price=entry, stop_price=stop)
q_atr = atr_s.size(equity=equity, entry_price=entry, stop_price=stop, atr=atr_value)

print(f"fixed-fraction: qty={q_fixed:,.2f}  risk=${q_fixed*(entry-stop):,.2f}  notional=${q_fixed*price:,.0f}")
print(f"ATR-based     : qty={q_atr:,.2f}  risk=${q_atr*(entry-stop):,.2f}  notional=${q_atr*price:,.0f}")
print(f"ATR stop distance = {1.5*atr_value:.2f} vs structural {entry-stop:.2f}")
print("-> when both are given, the LARGER distance is used, so realised risk stays <= budget")

for a in (0.4, 0.8, 2.0):
    q = atr_s.size(equity=equity, entry_price=entry, atr=a)
    print(f"ATR={a:>4}: qty={q:>10,.2f}  notional/equity={q*price/equity:>5.1%}")
"""
    )
    nb.md("### 5.2 The cost of a trade, in R\n\nThis is the number that decides whether a 1.5R target is real.")
    nb.code(
        """
def cost_in_R(entry: float, stop: float, qty: float, model: ExecutionModel) -> dict:
    \"\"\"Round-trip commission + slippage expressed in R (risk units).\"\"\"
    notional = qty * entry
    fee_in = model.commission(notional)
    fee_out = model.commission(qty * entry)          # approximate exit notional
    slip_in = notional * model.slippage_bps / 10_000
    slip_out = notional * model.stop_slippage_bps / 10_000
    risk = qty * abs(entry - stop)
    total = fee_in + fee_out + slip_in + slip_out
    return {"notional": notional, "risk": risk, "total_cost": total,
            "cost_R": total / risk, "stop_pct": abs(entry - stop) / entry}

model = ExecutionModel(fee_bps=2, slippage_bps=1, stop_slippage_bps=4)
rows = []
for stop_pct in (0.001, 0.002, 0.005, 0.01, 0.02):
    stop = 100 * (1 - stop_pct)
    qty = FixedFractionSizer(risk_pct=0.01).size(100_000, 100.0, stop)
    r = cost_in_R(100.0, stop, qty, model)
    rows.append({"stop_%": stop_pct * 100, "qty": qty, "cost_$": r["total_cost"], "cost_R": r["cost_R"]})

pd.DataFrame(rows).round(4)
"""
    )
    nb.md(
        """
**Read the table.** At a 0.1% stop, round-trip costs eat 0.9R of a 1R risk
budget — an entire unit of risk, per trade. No target multiple survives that.
This is why scalping strategies need institutional costs — or no costs at all in
the backtest, which is a fantasy. (Note the quantity is capped at 1x leverage, so
the dollar cost plateaus while the stop distance shrinks; the *cost in R* is what
matters and it worsens as the stop tightens.)
"""
    )
    nb.md("### 5.3 Break-even win rate, before and after costs")
    nb.code(
        """
def breakeven_win_rate(r_multiple: float, cost_r: float = 0.0) -> float:
    \"\"\"Win rate needed for zero expectancy when a win pays R and a loss costs 1R.\"\"\"
    win = r_multiple - cost_r
    loss = 1.0 + cost_r
    return loss / (win + loss)

for r in (1.0, 1.5, 2.0, 3.0):
    print(f"R={r:>3}: no costs {breakeven_win_rate(r):>6.1%} | 0.10R costs {breakeven_win_rate(r, 0.10):>6.1%} | 0.25R costs {breakeven_win_rate(r, 0.25):>6.1%}")
"""
    )
    nb.md("### 5.4 Intrabar ambiguity, on a bar built for it\n\nEntry at 100, stop at 95, target at 110. The fill bar trades 94–112, so both levels are inside it. The engine cannot know the order; the conservative assumption fills the stop first.")
    nb.code(
        """
idx = pd.date_range("2024-01-02 14:00", periods=5, freq="5min", tz="UTC")
amb = pd.DataFrame(
    {"open": [100, 100, 100, 100, 100],
     "high": [100.5, 100.5, 100.5, 112.0, 101.0],
     "low":  [99.5, 99.5, 99.5, 94.0, 99.0],
     "close": [100, 100, 100, 100, 100],
     "volume": 1000},
    index=idx,
)

class OnceLong(BaseStrategy):
    warmup = 1
    def generate(self, ctx):
        if ctx.bar.index == 2 and ctx.is_flat:
            return {"side": "buy", "stop": 95.0, "target": 110.0, "reason": "ambiguity_demo"}
        return None

model0 = ExecutionModel(fee_bps=0, slippage_bps=0, stop_slippage_bps=0, min_fee=0)
for label in ("conservative", "optimistic"):
    res = BacktestEngine.build(amb, OnceLong(sizer=FixedFractionSizer(risk_pct=0.01)),
                               initial_cash=10_000, model=model0, ambiguity=label).run()
    t = res.trades.iloc[0]
    print(f"{label:>12}: exit {t['exit_reason']:<12} at {t['exit_price']:.2f}  net {t['net_pnl']:>8.2f}")
print("\\nDifference between the two assumptions is the price of not knowing the path.")
"""
    )
    nb.md("### 5.5 Gap through the stop\n\nOvernight gaps and news bars do not fill you at the stop. They fill you at the open — and the loss is larger than the risk budget.")
    nb.code(
        """
gap = pd.DataFrame(
    {"open": [100, 100, 100, 100, 90],
     "high": [100.5, 100.5, 100.5, 101, 91],
     "low":  [99.5, 99.5, 99.5, 99, 89],
     "close": [100, 100, 100, 100, 90],
     "volume": 1000},
    index=pd.date_range("2024-01-02 14:00", periods=5, freq="5min", tz="UTC"),
)
res = BacktestEngine.build(gap, OnceLong(sizer=FixedFractionSizer(risk_pct=0.01)),
                           initial_cash=10_000, model=model0).run()
print(res.fills[["bar_index", "reason", "side", "qty", "price"]].to_string(index=False))
print("\\nRealised loss:", round(res.trades.iloc[0]["net_pnl"], 2),
      "| nominal risk budget:", round(10_000 * 0.01, 2))
"""
    )
    nb.md("### 5.6 Upgrade path: a seeded microbar path\n\nOHLC gives four numbers; a microbar path invents the missing order *deterministically*. This helper is deliberately simple (random bridge constrained by the bar's high/low). It is not a substitute for real tick data — it is a way to test how sensitive your results are to the assumption.")
    nb.code(
        """
def micro_path(bar: Bar, n: int = 20, seed=None) -> np.ndarray:
    \"\"\"Generate `n` deterministic sub-bar prices between open and close.

    A Brownian bridge is scaled so it touches the bar's high and low exactly;
    the seed derives from the bar index by default -> reproducible.
    \"\"\"
    rng = np.random.default_rng(bar.index if seed is None else seed)
    t = np.linspace(0, 1, n + 2)[1:-1]
    bridge = rng.normal(0, 1, n)
    bridge = np.cumsum(bridge - bridge.mean())
    bridge -= np.linspace(bridge[0], bridge[-1], n)
    span = max(bridge.max() - bridge.min(), 1e-9)
    path = bar.open + (bar.close - bar.open) * t + bridge / span * (bar.high - bar.low) * 0.5
    path = np.clip(path, bar.low, bar.high)
    # force the extremes in, so the path respects the OHLC envelope
    path[int(np.argmax(path))] = bar.high
    path[int(np.argmin(path))] = bar.low
    return path


def first_touch(path: np.ndarray, stop: float, target: float, is_long: bool = True) -> str:
    \"\"\"Which level the path touches first? Ties resolve to the stop.\"\"\"
    for price in path:
        if is_long and price <= stop:
            return "stop"
        if not is_long and price >= stop:
            return "stop"
        if is_long and price >= target:
            return "target"
        if not is_long and price <= target:
            return "target"
    return "none"

b = Bar(3, amb.index[3], 100, 112, 94, 100, 1000)
outcomes = [first_touch(micro_path(b, n=50, seed=s), 95, 110) for s in range(5)]
print("micro-path outcomes over 5 seeds:", outcomes)
print("conservative engine says      : stop")
print("\\nIf most seeds say 'target', your conservative rule is expensive;")
print("if they say 'stop', it is protecting you. Either way, now you can quantify it.")
"""
    )
    nb.md("### 5.7 Costs change the answer: the same strategy at four cost levels")
    nb.code(
        """
df = load_ohlcv_csv(str(DATA / "sample_5min_equity_1m.csv"))
rows = []
for fee, slip, stop_slip in [(0, 0, 0), (2, 1, 3), (5, 2, 6), (10, 4, 12)]:
    strategy = SweepBosFvgStrategy(SweepBosFvgParams(), sizer=FixedFractionSizer(risk_pct=0.01))
    res = BacktestEngine.build(
        df, strategy, initial_cash=100_000,
        model=ExecutionModel(fee_bps=fee, slippage_bps=slip, stop_slippage_bps=stop_slip),
    ).run()
    s = res.summary()
    rows.append({"fee_bps": fee, "slip_bps": slip, "stop_slip": stop_slip,
                 "trades": s["trades"], "return": s["total_return"],
                 "fees_$": s["fees_paid"], "win_rate": s["win_rate"], "max_dd": s["max_drawdown"]})
pd.DataFrame(rows).round(4)
"""
    )
    nb.md(
        """
The trade count barely changes; the return can flip sign. **That is the lesson.**
A strategy whose edge lives inside the cost assumption is not a strategy.
"""
    )

    nb.md(
        """
**How to expand this code**

- [ ] move the cost model into a `CostModel` protocol (`commission`, `fill_price`);
- [ ] add per-venue models (per-share equities, per-contract futures, maker/taker tiers);
- [ ] add a spread model on top of bps slippage;
- [ ] add partial fills for size above a volume participation cap;
- [ ] add a trailing-stop module that owns its own state per position;
- [ ] replace the conservative tie-break with a `PathSimulator` (microbars/ticks);
- [ ] add a cost report (`cost_R` per trade) to every backtest run.

"""
    )
    nb.md(section(6, "Unit tests"))
    nb.md(
        """
Five properties every execution model must satisfy:

1. a market order fills at the next bar's open, not the signal close,
2. fees and slippage are charged and visible,
3. a bar that touches both levels resolves to the stop,
4. a gap through the stop fills at the open and loses more than 1R,
5. sizing risks exactly the budget when the stop distance is respected.
"""
    )
    nb.code(
        """
test_code = '''
import sys
from pathlib import Path
import pandas as pd
import pytest

BASE = next(p for p in (Path.cwd(), Path.cwd().parent) if (p / "intraday_engine").is_dir())
sys.path.insert(0, str(BASE))
from intraday_engine import (BacktestEngine, BaseStrategy, ExecutionModel,
                             FixedFractionSizer, AtrSizer, Portfolio, Side)
from intraday_engine.core import Fill

class OnceLong(BaseStrategy):
    warmup = 1
    def generate(self, ctx):
        if ctx.bar.index == 2 and ctx.is_flat:
            return {"side": "buy", "stop": 95.0, "target": 110.0, "reason": "t"}
        return None

def frame(rows):
    idx = pd.date_range("2024-01-02 14:00", periods=len(rows), freq="5min", tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 1000
    return df

@pytest.fixture
def ambiguous_bar():
    return frame([(100,100.5,99.5,100),(100,100.5,99.5,100),(100,100.5,99.5,100),
                  (100,112,94,100),(100,101,99,100)])

def test_stop_wins_tie(ambiguous_bar):
    m = ExecutionModel(fee_bps=0, slippage_bps=0, stop_slippage_bps=0, min_fee=0)
    res = BacktestEngine.build(ambiguous_bar, OnceLong(sizer=FixedFractionSizer()),
                               10_000, model=m, ambiguity="conservative").run()
    assert res.trades.iloc[0]["exit_reason"] == "stop"

def test_optimistic_is_not_the_default(ambiguous_bar):
    m = ExecutionModel(fee_bps=0, slippage_bps=0, stop_slippage_bps=0, min_fee=0)
    res = BacktestEngine.build(ambiguous_bar, OnceLong(sizer=FixedFractionSizer()),
                               10_000, model=m, ambiguity="optimistic").run()
    assert res.trades.iloc[0]["exit_reason"] == "take_profit"

def test_gap_loss_exceeds_budget():
    df = frame([(100,100.5,99.5,100),(100,100.5,99.5,100),(100,100.5,99.5,100),
                (100,101,99,100),(90,91,89,90)])
    m = ExecutionModel(fee_bps=0, slippage_bps=0, stop_slippage_bps=0, min_fee=0)
    res = BacktestEngine.build(df, OnceLong(sizer=FixedFractionSizer(risk_pct=0.01)), 10_000, model=m).run()
    assert res.fills[res.fills["reason"]=="stop"].iloc[0]["price"] == pytest.approx(90.0)
    assert res.trades.iloc[0]["net_pnl"] == pytest.approx(-200.0)   # 2x the 1% budget

def test_fees_charged():
    df = frame([(100,100.5,99.5,100)]*5)
    m = ExecutionModel(fee_bps=10, slippage_bps=0, min_fee=0)
    res = BacktestEngine.build(df, OnceLong(sizer=FixedFractionSizer()), 10_000, model=m).run()
    f = res.fills.iloc[0]
    assert f["fee"] == pytest.approx(f["notional"] * 10 / 10_000)

def test_sizing_risks_the_budget():
    q = FixedFractionSizer(risk_pct=0.02).size(50_000, 100, 95)
    assert q * 5 == pytest.approx(1_000)

def test_atr_sizing_shrinks_in_vol():
    s = AtrSizer(risk_pct=0.01, atr_mult=2)
    assert s.size(100_000, 100, atr=2.0) < s.size(100_000, 100, atr=0.5)
'''
path = Path(tempfile.mkdtemp()) / "test_lesson4.py"
path.write_text(test_code)
import subprocess
res = subprocess.run([sys.executable, "-m", "pytest", "-q", str(path)], capture_output=True, text=True)
print(res.stdout[-900:])
"""
    )

    nb.md(section(7, "Example input and expected output"))
    nb.md(
        """
### Hand-checkable example

Account \\$10,000, risk 1% (\\$100), entry 100, stop 95, target 110, fees 0,
slippage 0.

| Step | Calculation | Value |
|---|---|---|
| Risk per unit | `100 − 95` | \\$5 |
| Quantity | `100 / 5` | 20 units |
| Notional | `20 × 100` | \\$2,000 |
| Target in R | `(110 − 100) / 5` | 2R |
| Win at target | `20 × 10` | +\\$200 |
| Loss at stop | `20 × −5` | −\\$100 |

Now the same trade on the ambiguous bar (`low 94`, `high 112`):

| Assumption | Exit | PnL | Equity |
|---|---|---|---|
| Conservative (stop first) | 95 | −\\$100 | \\$9,900 |
| Optimistic (target first) | 110 | +\\$200 | \\$10,200 |

A \\$300 swing on a \\$100 risk budget — from a modelling choice, not a market move.

### Gap example

| Bar | OHLC | What happens |
|---|---|---|
| 2 | 100 / 100.5 / 99.5 / 100 | signal generated at the close |
| 3 | 100 / 101 / 99 / 100 | entry fills at the open 100, bracket armed |
| 4 | 90 / 91 / 89 / 90 | opens below the 95 stop ⇒ fill at **90**, not 95 |

Realised loss = 20 × (100 − 90) = −\\$200 = **2R**, double the intended risk.
That is gap risk, and no amount of backtesting discipline removes it — only
position sizing and event awareness do.
"""
    )

    nb.md(section(8, "Exercises"))
    nb.md(
        """
### Exercise 4.1 — trailing stop
Implement a trailing stop that ratchets to `close − 1.5 × ATR` once the trade is
1R in profit, never moving backwards. Where does it belong: strategy or execution
engine? Justify your choice, then implement it in the place you chose.

### Exercise 4.2 — partial exits
Exit half at 1R and the rest at 2R. Update the trade record to support two exits
(or emit two trade records). What happens to expectancy and to fees in R?

### Exercise 4.3 — spread instead of slippage
Model a fixed spread of 2 bps (buy at mid + 1 bp, sell at mid − 1 bp) and compare
with the bps slippage model on the same strategy. Which is more conservative on
limit entries?

### Exercise 4.4 — cost sensitivity report
Produce a table of expectancy (in R) for fee/slippage pairs {0, 2, 5, 10} × {0, 1,
3, 8} bps. Find the level at which the demo strategy stops being profitable. What
would you need to believe about your broker to trust the backtest?

### Exercise 4.5 — sizing switch
Run the demo strategy with `sizing_mode="fixed"` and `"atr"`. Compare max
drawdown, average position notional and the distribution of realised R. Which
mode would you prefer if the exchange raises margin requirements?

### Exercise 4.6 — capacity
Assume your order moves the price by `0.1 bp per 1% of bar volume` traded. At what
position size does the cost exceed 0.2R on a 0.5% stop? (Use median volume from
the sample.) This is a first, crude capacity estimate.

### Exercise 4.7 — microbar honesty
Replace the conservative rule with the `micro_path` simulator and run it with 20
seeds per trade. Report the distribution of total PnL. How wide is the interval?
Would you trust a single seed?
"""
    )
    nb.md(
        note(
            "The most dangerous sentence in backtesting is 'it's only 2 bps'. "
            "Two basis points on a 0.2% stop is 10% of R, per side. Do the arithmetic "
            "for *your* stop before you believe *any* equity curve.",
            kind="Coach's note",
        )
    )

    nb.md(section(9, "Common pitfalls and debugging"))
    nb.md(
        """
| Pitfall | Symptom | Fix / test |
|---|---|---|
| Fees on notional vs per-share | crypto equity curve unrealistically smooth | pick a convention, document it, test one fill |
| Slippage applied in the favourable direction | too-good fills | assert `buy_fill >= reference`, `sell_fill <= reference` |
| Stop on the wrong side | instant exit or no exit | engine rejects `stop >= fill` for longs |
| Sizing from the target distance | 2–3× intended risk | size from `|entry − stop|`, always |
| Ignoring gaps | 1R loss assumed, 2R realised | tested in this lesson |
| Ignoring fees in R | break-even win rate understated | `cost_R = cost / (qty × D)` |
| Limit order assumed to fill at the touch | optimistic fill rate | fill only when traded through; no improvement |
| Same-bar entry and exit | impossible round trips | orders active from `t+1` |
| Leverage unaccounted | notional > equity | cap with `max_leverage` |
| Survivorship of open trades | metrics ignore the position still open | flatten at the end or mark and report |
"""
    )

    nb.md(section(10, "Recommended logging and diagnostics"))
    nb.md(
        """
Log every fill with costs split out:

| Field | Why |
|---|---|
| `reason` (`market`/`limit`/`stop`/`take_profit`) | tells you which assumption is doing the work |
| `slippage_cost`, `fee` | cost attribution |
| `qty`, `price`, `notional` | reconciliation |
| `bar_index`, `timestamp` | intrabar and session analysis |

Per-trade report to build once:

```python
t = result.trades.copy()
t["cost_R"] = t["fees"] / (t["qty"] * (t["entry_price"] - t["entry_price"] * 0.99))
print(t.groupby("exit_reason")["net_pnl"].agg(["count", "mean", "sum"]))
print("cost as % of gross:", (t["fees"].sum() / t["gross_pnl"].abs().sum()))
```

**Run a cost audit before a performance review:**

1. Gross vs net expectancy by exit reason.
2. Fees as a share of gross PnL.
3. Fill rate for limit orders (orders sent vs filled).
4. Slippage distribution (mean and 95th percentile).

**Next lesson:** put the pieces together into an engine you can reuse — and audit
it for the mistakes this lesson just priced.
"""
    )
    return nb
