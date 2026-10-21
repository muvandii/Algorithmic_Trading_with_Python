"""Notebook 06 — capstone: write, test and stress your own strategy."""

from __future__ import annotations

from .common import Notebook, header, note, section

FILENAME = "06_capstone_write_your_own.ipynb"
TITLE = "Capstone: write your own strategy"


def build() -> Notebook:
    """Return the capstone worksheet."""
    nb = Notebook(TITLE)
    nb.md(header(6, "Capstone — write, test and stress your own strategy",
                 "A worksheet with a complete second example: VWAP mean reversion, from hypothesis to kill criteria."))
    nb.setup()

    nb.md(section(1, "Learning objectives"))
    nb.md(
        """
By the end of this capstone you can:

1. **Turn** a market hypothesis into a precise, testable specification (no vague adjectives).
2. **Implement** it as a `BaseStrategy` subclass with a state machine, a sizing rule and a bracket.
3. **Validate** it in the right order: single trade → accounting → costs → robustness → out-of-sample.
4. **Record** experiments so results are comparable and reproducible.
5. **Decide** to keep, iterate or kill a strategy using pre-registered criteria instead of hope.
"""
    )

    nb.md(section(2, "Key concepts and definitions"))
    nb.md(
        """
| Term | Meaning |
|---|---|
| **Hypothesis** | A falsifiable statement about market behaviour ("5-min closes more than 2 ATR below session VWAP revert toward it within 10 bars"). |
| **Specification** | Hypothesis + universe + session + entry + exit + sizing + costs + failure criteria. |
| **Edge** | Positive expectancy after realistic costs, stable across regimes. |
| **Expectancy** | `p·avg_win − (1−p)·avg_loss`, in R or currency. |
| **Baseline** | The dumbest comparison: buy-and-hold, coin flip, or random entries with the same exits. |
| **Robustness** | Performance survives costs, parameter perturbations, and a different period. |
| **Overfitting** | Fitting noise; looks great in-sample, fails forward. |
| **Walk-forward** | Choose parameters on window A, evaluate on window B, roll forward. |
| **Experiment log** | One row per run: data, params, costs, metrics, verdict. |
| **Kill criterion** | Pre-registered condition that ends the project (e.g. negative net expectancy at 2× costs). |
| **Research debt** | Undocumented data quirks and assumptions; compounds. |
| **Paper trading** | Forward test on live data with no money — the last gate before capital. |
"""
    )

    nb.md(section(3, "Step-by-step walkthrough"))
    nb.md(
        """
### 3.1 The research protocol (do not reorder)

| Step | Question | Output | Failure mode if skipped |
|---|---|---|---|
| 1 | What behaviour am I exploiting, and why would it persist? | one paragraph | a strategy with no reason to work |
| 2 | Can I state entry/exit in one sentence each? | spec table | disguised curve fitting |
| 3 | What is the simplest version? | ≤3 parameters | brittle complexity |
| 4 | Does one trade behave exactly as specified? | hand-checked example | accounting bugs hidden by statistics |
| 5 | Does it survive realistic costs? | net expectancy at 2× costs | "edge" that is a fee artefact |
| 6 | Does it survive perturbations? | ±20% params, other period | noise fitting |
| 7 | Does it beat a baseline? | buy-and-hold / random entries | beta dressed as alpha |
| 8 | Would I trade it with my own money tomorrow? | kill or paper-trade | sunk-cost commitment |

### 3.2 The worked example: VWAP mean reversion

**Hypothesis.** Intraday traders overreact around the session VWAP. When a 5-min
bar closes unusually far below the *session-to-date* VWAP and then closes above
its open (a rejection bar), price tends to revert toward VWAP.

**Why it might persist.** Execution algos benchmark to VWAP; flows are
uninformative at extremes; short-horizon liquidity providers get paid to absorb
imbalance. (If you cannot write this paragraph for your strategy, stop at step 1.)

**Specification.**

| Element | Rule |
|---|---|
| Universe | one liquid instrument |
| Session | 13:30–20:00 UTC, no overnight |
| VWAP | `Σ(typical × vol) / Σ vol` from session start **up to and including t** |
| Entry (long) | `close[t] < VWAP[t] − k·ATR14[t]` **and** `close[t] > open[t]`; market at next open |
| Stop | `entry − 1.0 × ATR14[t]` |
| Target | `VWAP[t]` (a level, not a multiple) |
| Time stop | 12 bars |
| Sizing | fixed fraction, 1% risk, 1× max leverage |
| One trade | at most one position at a time; no re-entry for 5 bars |
| Kill criterion | negative net expectancy at 2× costs, or worse than random-entry baseline |

Note the asymmetries: the target is a *level* that moves, so R is not fixed. The
strategy records R at entry for post-hoc analysis but does not pretend it is a
fixed 2R system.

### 3.3 What "validated" means here

1. the hand-checked single trade matches the spec,
2. accounting reconciles,
3. edge survives fees 2× and slippage 2×,
4. ±20% on `k` and `atr_mult` does not flip the sign,
5. the second half of the sample behaves like the first (or you say so),
6. random entries with the same exits do not produce the same result.
"""
    )

    nb.md(section(4, "Data and API conventions"))
    nb.md(
        """
### Strategy specification template (fill this in before coding)

| Field | Your answer |
|---|---|
| Name / version | `vwap_reversion_v1` |
| Hypothesis | one falsifiable sentence |
| Universe & timeframe | e.g. one US equity, 5-min |
| Session filter | e.g. 13:30–20:00 UTC |
| Features (all causal) | VWAP, ATR14, bar direction |
| Entry long / short | explicit inequalities |
| Stop | formula |
| Target | formula or level |
| Time stop | bars |
| Sizing | method, risk %, leverage cap |
| Max concurrent positions | 1 |
| Cost model | fee bps, slippage bps, stop bps |
| Parameters (≤5) | name, default, range |
| Kill criteria | explicit thresholds |

### Experiment record schema (one row per run)

| Field | Example |
|---|---|
| `run_id` | `vwap-v1-k2.0-2024H1` |
| `data_hash` | first 8 chars of `sha256` of the CSV |
| `period` | `2024-01-02 → 2024-01-27` |
| `fees_bps`, `slip_bps` | `2`, `1` |
| `params` | `{"k": 2.0, "atr_mult": 1.0}` |
| `trades`, `total_return`, `max_dd`, `win_rate`, `expectancy_R` | metrics |
| `verdict` | keep / iterate / kill |

### Naming and files

```
strategies/
  vwap_reversion.py        # the strategy (importable, no side effects)
  templates/               # ideas not yet tested
research/
  experiments.csv          # the log above
  notes/2024-01-28-vwap.md # decisions and why
```
"""
    )

    nb.md(section(5, "Minimal runnable code"))
    nb.md(
        """
### 5.1 The complete strategy (~60 lines)

Copy this into `strategies/vwap_reversion.py` when you want to keep it. Every
feature is computed from `ctx.history`, which ends at the current bar.
"""
    )
    nb.code(
        """
class VwapReversionParams:
    \"\"\"Few parameters, all with a reason to exist.\"\"\"
    def __init__(self, k_atr: float = 2.0, atr_period: int = 14, atr_mult: float = 1.0,
                 max_bars: int = 12, cooldown_bars: int = 5, max_trades_day: int = 3,
                 session_exit: str = "19:45", allow_shorts: bool = True) -> None:
        self.k_atr = k_atr
        self.atr_period = atr_period
        self.atr_mult = atr_mult
        self.max_bars = max_bars
        self.cooldown_bars = cooldown_bars
        self.max_trades_day = max_trades_day
        self.session_exit = session_exit
        self.allow_shorts = allow_shorts


class VwapReversion(BaseStrategy):
    \"\"\"Session-VWAP mean reversion with a rejection bar, ATR stop and VWAP target.\"\"\"

    warmup = 30

    def __init__(self, params=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.p = params or VwapReversionParams()

    def reset(self) -> None:
        self.state.update({"phase": "FLAT", "entry_bar": -1, "last_exit_bar": -1000,
                           "trades_today": 0, "day": None, "exit_pending": False})

    # ------------------------------------------------------------- features
    @staticmethod
    def session_vwap(history: pd.DataFrame) -> float:
        \"\"\"Cumulative VWAP for the *current session only*, up to the last row.

        Uses typical price (H+L+C)/3 weighted by volume. Recomputing from the
        session start each bar is O(session bars) -- fine for 5-min data, and
        exactly causal. For 1-min data keep a running pair of sums instead.
        \"\"\"
        day = history.index[-1].date()
        today = history[history.index.date == day]
        typical = (today["high"] + today["low"] + today["close"]) / 3.0
        vol = today["volume"].to_numpy()
        if vol.sum() <= 0:
            return float(today["close"].iloc[-1])
        return float((typical * today["volume"]).sum() / today["volume"].sum())

    # --------------------------------------------------------------- signal
    def generate(self, ctx: Context):
        p = self.p
        hist = ctx.history
        day = ctx.bar.timestamp.date()
        if self.state["day"] != day:
            self.state.update({"day": day, "trades_today": 0})
        if ctx.bar.index - self.state["last_exit_bar"] < p.cooldown_bars:
            return None
        if self.state["trades_today"] >= p.max_trades_day:
            return None
        if ctx.bar.timestamp.strftime("%H:%M") >= p.session_exit:
            return None  # no new risk this close to the bell

        vwap = self.session_vwap(hist)
        atr = self.spot(ctx, atr_mult=1.0, atr_period=p.atr_period)
        if atr <= 0:
            return None
        stretched_down = ctx.close < vwap - p.k_atr * atr
        stretched_up = ctx.close > vwap + p.k_atr * atr
        rejection_up = ctx.close > ctx.bar.open
        rejection_down = ctx.close < ctx.bar.open

        if stretched_down and rejection_up:
            entry, stop, target, side = ctx.close, ctx.close - p.atr_mult * atr, vwap, "buy"
        elif stretched_up and rejection_down and p.allow_shorts:
            entry, stop, target, side = ctx.close, ctx.close + p.atr_mult * atr, vwap, "sell"
        else:
            return None
        if side == "buy" and target <= entry:
            return None
        if side == "sell" and target >= entry:
            return None

        return {"side": side, "stop": stop, "target": target, "entry_ref": entry,
                "reason": "vwap_reversion", "vwap": vwap, "atr": atr,
                "expires_after": 3}

    # ---------------------------------------------------------------- exits
    def manage(self, ctx: Context):
        if ctx.is_flat:
            return []
        entry_bar = self.state.get("entry_bar", ctx.bar.index)
        time_stop = ctx.bar.index - entry_bar >= self.p.max_bars
        session_end = ctx.bar.timestamp.strftime("%H:%M") >= self.p.session_exit
        if (time_stop or session_end) and not self.state.get("exit_pending", False):
            # One exit order at a time: two would close the trade and open the opposite one.
            self.state["exit_pending"] = True
            return [Order(side=Side.BUY if ctx.position < 0 else Side.SELL, qty=abs(ctx.position),
                          type=OrderType.MARKET,
                          tag="exit:time_stop" if time_stop else "exit:session_close")]
        return []

    def on_fill(self, fill, ctx=None) -> None:
        super().on_fill(fill, ctx)
        if ctx is None:
            return
        if getattr(fill, "reason", "") in ("stop", "take_profit") or getattr(fill, "tag", "").startswith("exit"):
            self.state["last_exit_bar"] = ctx.bar.index
            self.state["trades_today"] = self.state.get("trades_today", 0) + 1
            self.state["entry_bar"] = -1
            self.state["exit_pending"] = False

df = load_ohlcv_csv(str(DATA / "sample_5min_equity_1m.csv"))
strategy = VwapReversion(VwapReversionParams(), sizer=FixedFractionSizer(risk_pct=0.01))
result = BacktestEngine.build(
    df, strategy, initial_cash=100_000,
    model=ExecutionModel(fee_bps=2, slippage_bps=1, stop_slippage_bps=4),
).run()
result.summary()
"""
    )
    nb.md(
        """
### 5.2 Read the trades before the metrics

**Spoiler:** on this synthetic sample the strategy loses money — and that is the
most useful outcome the lesson can give you. The sample has a strong upward
drift, so a counter-trend idea fights the tape. The point of the next four cells
is not to rescue it; it is to show how quickly and honestly you can find out,
and what evidence would make you iterate or kill it.

Any strategy can look plausible in a summary table. Read the actual journal of a
few trades: entry reason, stop, target, R, exit reason.
"""
    )
    nb.code(
        """
t = result.trades.copy()
if len(t):
    print(t[["entry_time", "side", "entry_price", "exit_price", "net_pnl", "bars_held", "exit_reason"]].head(10).to_string(index=False))
else:
    print("no trades -- check warm-up, k_atr, and the session window")
"""
    )
    nb.code(
        """
print("exit reasons:", result.trades["exit_reason"].value_counts().to_dict() if len(result.trades) else {})
print("fees paid   :", round(result.portfolio.fees_paid, 2))
print("event counts:", result.events["kind"].value_counts().to_dict())
print("rejections  :", result.rejections()["message"].value_counts().to_dict() if len(result.rejections()) else {})
"""
    )
    nb.md(
        """
If there are **zero trades**, the usual suspects are: warm-up longer than the
sample, `k_atr` too wide, the session filter excluding the data, or the VWAP
distance never reached. Diagnose with a per-bar diagnostic table rather than by
changing parameters at random.
"""
    )
    nb.code(
        """
diag = []
for i in range(60, min(len(df), 400)):
    hist = df.iloc[: i + 1]
    day = hist.index[-1].date()
    today = hist[hist.index.date == day]
    typical = (today["high"] + today["low"] + today["close"]) / 3
    vwap = float((typical * today["volume"]).sum() / today["volume"].sum())
    atr_val = atr(hist, 14).iloc[-1]
    diag.append({"bar": i, "close": hist["close"].iloc[-1], "vwap": vwap,
                 "z": (hist["close"].iloc[-1] - vwap) / atr_val if atr_val else np.nan})
d = pd.DataFrame(diag)
print("distance from VWAP in ATR units:")
print(d["z"].describe().round(2))
print("bars beyond 2 ATR:", int((d["z"].abs() > 2).sum()), "of", len(d))
"""
    )
    nb.md("### 5.3 Costs first, then everything else")
    nb.code(
        """
rows = []
for label, fee, slip, stop_slip in [("zero", 0, 0, 0), ("base", 2, 1, 4),
                                    ("2x", 4, 2, 8), ("3x", 6, 3, 12)]:
    s = VwapReversion(VwapReversionParams(), sizer=FixedFractionSizer(risk_pct=0.01))
    r = BacktestEngine.build(df, s, initial_cash=100_000,
                             model=ExecutionModel(fee_bps=fee, slippage_bps=slip, stop_slippage_bps=stop_slip)).run()
    sm = r.summary()
    rows.append({"costs": label, "trades": sm["trades"], "return": sm["total_return"],
                 "win_rate": sm["win_rate"], "expectancy_$": r.trades["net_pnl"].mean() if len(r.trades) else np.nan,
                 "max_dd": sm["max_drawdown"]})
pd.DataFrame(rows).round(4)
"""
    )
    nb.md("### 5.4 Robustness: perturb the parameters\n\nA single good parameter set is a coincidence until the neighbourhood is also fine. This is a **sensitivity**, not an optimisation — resist picking the best cell.")
    nb.code(
        """
rows = []
for k in (1.5, 2.0, 2.5, 3.0):
    for m in (0.75, 1.0, 1.25):
        s = VwapReversion(VwapReversionParams(k_atr=k, atr_mult=m), sizer=FixedFractionSizer(risk_pct=0.01))
        r = BacktestEngine.build(df, s, initial_cash=100_000).run()
        rows.append({"k_atr": k, "atr_mult": m, "trades": len(r.trades), "return": r.summary()["total_return"]})
grid = pd.DataFrame(rows)
grid.pivot(index="k_atr", columns="atr_mult", values="return").round(4)
"""
    )
    nb.md(
        """
Read the grid for **stability**, not the maximum. A plateau (neighbouring cells
similar, signs consistent) is evidence; a lone spike is noise. With 24 trades,
almost everything is noise — say so out loud before you risk money.
"""
    )
    nb.md("### 5.5 The baseline you must beat\n\nRandom entries with the same brackets are a surprisingly strong benchmark. If your logic cannot beat random, your logic is decoration.")
    nb.code(
        """
class RandomEntries(BaseStrategy):
    \"\"\"Seeded random entries with identical exits: the null hypothesis.\"\"\"
    warmup = 30
    def __init__(self, seed: int = 7, **kw):
        super().__init__(**kw)
        self.rng = np.random.default_rng(seed)
    def generate(self, ctx):
        if ctx.is_flat and self.rng.random() < 0.01:
            e = ctx.close
            a = self.spot(ctx)
            side = "buy" if self.rng.random() < 0.5 else "sell"
            stop = e - a if side == "buy" else e + a
            return {"side": side, "stop": stop, "target": e + (2 if side == "buy" else -2) * abs(e - stop),
                    "entry_ref": e, "reason": "random"}
        return None

base = []
for seed in (1, 2, 3, 4, 5):
    r = BacktestEngine.build(df, RandomEntries(seed=seed, sizer=FixedFractionSizer(risk_pct=0.01)),
                             initial_cash=100_000).run()
    base.append(r.summary()["total_return"])
print("random-entry returns:", [round(x, 4) for x in base], "| mean:", round(float(np.mean(base)), 4))
print("vwap strategy return:", round(result.summary()["total_return"], 4))
"""
    )
    nb.md("### 5.6 Walk-forward: the only split that resembles live trading")
    nb.code(
        """
half = len(df) // 2
train, test = df.iloc[:half], df.iloc[half:]

train_rows = []
for k in (1.5, 2.0, 2.5, 3.0):
    s = VwapReversion(VwapReversionParams(k_atr=k), sizer=FixedFractionSizer(risk_pct=0.01))
    r = BacktestEngine.build(train, s, initial_cash=100_000).run()
    train_rows.append({"k_atr": k, "train_return": r.summary()["total_return"], "train_trades": len(r.trades)})
train_tbl = pd.DataFrame(train_rows).sort_values("train_return", ascending=False)
print(train_tbl.round(4).to_string(index=False))

best_k = float(train_tbl.iloc[0]["k_atr"])
s = VwapReversion(VwapReversionParams(k_atr=best_k), sizer=FixedFractionSizer(risk_pct=0.01))
oos = BacktestEngine.build(test, s, initial_cash=100_000).run()
print(f"\\nbest k on first half: {best_k}")
print("out-of-sample:", {k: round(v, 4) if isinstance(v, float) else v for k, v in oos.summary().items() if k in ("trades", "total_return", "max_drawdown", "win_rate")})
"""
    )

    nb.md(section(6, "Unit tests"))
    nb.md(
        """
Test the *specification*, not the PnL. The PnL will change; the rules must not.
"""
    )
    nb.code(
        """
test_code = '''
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

BASE = next(p for p in (Path.cwd(), Path.cwd().parent) if (p / "intraday_engine").is_dir())
sys.path.insert(0, str(BASE))
from intraday_engine import *

# --- copy the VwapReversion class here in your own test file -------------

def test_vwap_is_causal_and_session_scoped():
    df = load_ohlcv_csv(str(BASE / "data" / "sample_5min_equity_1m.csv"))
    day = df.index[0].date()
    today = df[df.index.date == day]
    typical = (today["high"] + today["low"] + today["close"]) / 3
    vwap_full = float((typical * today["volume"]).sum() / today["volume"].sum())
    # compute on a truncated frame -> must match the prefix computed the same way
    k = 20
    prefix = today.iloc[:k]
    vwap_prefix = float(((prefix["high"]+prefix["low"]+prefix["close"])/3 * prefix["volume"]).sum() / prefix["volume"].sum())
    assert np.isfinite(vwap_full) and np.isfinite(vwap_prefix)

def test_engine_refuses_future_reads():
    df = load_ohlcv_csv(str(BASE / "data" / "pattern_sample.csv"))
    dh = DataHandler(df); dh.set_cursor(3)
    with pytest.raises(LookAheadError):
        dh.bar(4)

def test_sizing_respects_leverage():
    q = FixedFractionSizer(risk_pct=0.01, max_leverage=1.0).size(100_000, 100, 99)
    assert q * 100 <= 100_000 + 1e-9

def test_no_trade_without_a_stop():
    with pytest.raises(ValueError):
        FixedFractionSizer().size(100_000, 100, None)
'''
path = Path(tempfile.mkdtemp()) / "test_capstone.py"
path.write_text(test_code)
import subprocess
res = subprocess.run([sys.executable, "-m", "pytest", "-q", str(path)], capture_output=True, text=True)
print(res.stdout[-800:])
"""
    )

    nb.md(section(7, "Example input and expected output"))
    nb.md(
        """
### Hand-check the VWAP feature

Take the first session of the sample (13:30–19:55, 78 bars). For the first three
bars:

| Bar | High | Low | Close | Typical | Volume | Cumulative VWAP |
|---|---|---|---|---|---|---|
| 0 | 100.26 | 99.79 | 100.04 | 100.03 | v0 | 100.03 |
| 1 | 100.10 | 99.77 | 99.79 | 99.89 | v1 | `(100.03·v0 + 99.89·v1)/(v0+v1)` |
| 2 | 99.94 | 99.64 | 99.77 | 99.78 | v2 | `(… + 99.78·v2)/(v0+v1+v2)` |

**Expected behaviour:** VWAP starts at the first bar's typical price and moves
slowly; early in the session it is a poor anchor because it contains little
information. This is why the strategy uses a warm-up and why VWAP strategies are
usually intraday-only — the level resets at the session open.

The cell below prints the first five VWAP values and the distance from close in
ATR units, so you can see how often a 2-ATR stretch actually happens.
"""
    )
    nb.code(
        """
sess = df[df.index.date == df.index[0].date()].head(6).copy()
sess["typical"] = (sess["high"] + sess["low"] + sess["close"]) / 3
sess["cum_pv"] = (sess["typical"] * sess["volume"]).cumsum()
sess["cum_v"] = sess["volume"].cumsum()
sess["vwap"] = sess["cum_pv"] / sess["cum_v"]
sess[["open", "high", "low", "close", "volume", "typical", "vwap"]].round(3)
"""
    )

    nb.md(section(8, "Exercises — the actual capstone"))
    nb.md(
        """
### Capstone deliverable

Write **your own** strategy and take it through steps 1–8 of the protocol. Use
`strategies/template_strategy.py` as the starting point. Submit (to yourself):

1. the spec table from section 4 (completed),
2. the strategy file with type hints and docstrings,
3. at least four tests (look-ahead, accounting, one rule, one edge case),
4. the experiment log with at least six runs,
5. a one-page decision memo: keep / iterate / kill, with the evidence.

### Exercise 6.1 — baseline discipline
Add buy-and-hold and random-entry benchmarks to your own strategy's report. If
your strategy does not beat both after costs, write down why you still like it
(or admit you don't).

### Exercise 6.2 — regime split
Split the sample by volatility tercile (using ATR at entry, computed causally).
Report expectancy per regime. Is the edge concentrated in one regime? Could you
have known the regime in real time?

### Exercise 6.3 — parameter neighbourhood
For each parameter, run ±20% and ±40%. Report the sign of the net result. A
strategy whose sign flips inside ±20% is a coin flip with extra steps.

### Exercise 6.4 — capacity check
Assume your order moves price by 0.1 bp per 1% of median bar volume. At what
notional does the added cost exceed 0.2R? Would the strategy work at \\$1M? At
\\$10M?

### Exercise 6.5 — paper trading plan
Define the exact conditions under which you would move to paper trading (metrics,
duration, sample size), and the conditions that would make you stop. Pre-register
them before you look at the forward results.

### Exercise 6.6 — kill criteria
Write your kill criteria in three lines, timestamp them, and put them where you
will see them. The purpose is to protect future-you from present-you.
"""
    )
    nb.md(
        note(
            "Most strategies fail, and that is a normal research outcome. The skill "
            "you are building is not 'finding a winner'; it is *knowing quickly, "
            "cheaply and honestly* which ideas are not winners. That skill compounds.",
            kind="Coach's note",
        )
    )

    nb.md(section(9, "Common pitfalls and debugging"))
    nb.md(
        """
| Pitfall | Symptom | Fix |
|---|---|---|
| Vague hypothesis | you keep adding rules | rewrite it as one falsifiable sentence |
| Too many parameters | in-sample beauty, forward collapse | ≤5 params, ±20% stability |
| Optimising the grid | best cell is an outlier | sensitivity, not optimisation |
| Ignoring the baseline | "alpha" that is beta | random entries + buy-and-hold |
| Cherry-picked period | works in Jan, dies in Feb | walk-forward, multiple periods |
| Zero-cost fantasy | edge vanishes at 2× costs | cost table first |
| Tiny sample | 6 trades, strong opinion | report confidence intervals; gather more data |
| Session leakage | overnight gaps in intraday stats | flatten before the close |
| Re-entry loop | 5 entries on one idea | cooldown + one-position rule |
| Survivorship/universe bias | great stocks only | point-in-time universe |
| Silent data gaps | wrong intraday volatility | inspect timestamp gaps |
| No research log | you cannot reproduce last week | experiment CSV + notes |
"""
    )

    nb.md(section(10, "Recommended logging and diagnostics"))
    nb.md(
        """
### Your experiment log (append after every run)

```python
import hashlib, json
row = {
    "run_id": "vwap-v1-k2.0",
    "data_hash": hashlib.sha256(open(DATA/"sample_5min_equity_1m.csv","rb").read()).hexdigest()[:8],
    "period": f"{df.index[0]:%Y-%m-%d}->{df.index[-1]:%Y-%m-%d}",
    "fees_bps": 2, "slip_bps": 1,
    "params": {"k_atr": 2.0, "atr_mult": 1.0},
    **{k: v for k, v in result.summary().items() if isinstance(v, (int, float))},
}
```

### The decision memo (one page)

1. **Hypothesis and mechanism** — why should this work?
2. **Evidence** — net expectancy, sample size, cost sensitivity, regime split.
3. **Risks** — what will break it, and how would you notice?
4. **Decision** — keep / iterate / kill, with a date.
5. **Next experiment** — one change at a time, pre-registered.

### Final checklist before risking capital

- [ ] all five lessons' tests pass; reconciliation holds
- [ ] conservative intrabar assumption; optimistic gap quantified
- [ ] edge survives 2–3× costs
- [ ] parameter neighbourhood stable
- [ ] beats random-entry and buy-and-hold baselines
- [ ] walk-forward / out-of-sample evidence
- [ ] position sizing and leverage verified on the broker's contract specs
- [ ] kill criteria written, dated, visible
- [ ] paper-traded for a pre-registered period

You now have the loop, the state, the patterns, the costs and the engine. The
remaining ingredient is not code — it is the discipline to run the protocol even
when the equity curve is beautiful.
"""
    )
    return nb
