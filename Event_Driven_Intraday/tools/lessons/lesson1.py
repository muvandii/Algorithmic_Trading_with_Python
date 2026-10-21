"""Notebook 01 — the bar-by-bar loop and indexing."""

from __future__ import annotations

from .common import Notebook, header, note, section

FILENAME = "01_bars_and_indexing.ipynb"
TITLE = "Bars, indexing and the shape of a backtest loop"


def build() -> Notebook:
    """Return Lesson 1."""
    nb = Notebook(TITLE)
    nb.md(header(1, "Bar-by-bar loop and indexing (t, t-1, t+1)",
                 "The loop is the whole ballgame. Get the indices right and everything else can be debugged."))
    nb.setup()

    # ------------------------------------------------------------------ 1
    nb.md(section(1, "Learning objectives"))
    nb.md(
        """
By the end of this lesson you can:

1. **Explain** why an event-driven backtest processes one completed bar at a time and what "completed" means for a bar stamped 14:05.
2. **Access** bar `t`, `t-1` and `t+1` correctly by position and by timestamp, and state which of those a live strategy may use.
3. **Implement** a loop that computes a per-bar quantity (return, range, signal) with no future data, and reproduce it with vectorised `shift`.
4. **Detect** the three classic indexing bugs: `iloc[-1]` inside a loop, `shift(-1)` in a decision, and label slicing that includes tomorrow.
5. **Guard** a strategy with a warm-up period and a cursor so that look-ahead raises an error instead of silently inflating the PnL.
"""
    )

    # ------------------------------------------------------------------ 2
    nb.md(section(2, "Key concepts and definitions"))
    nb.md(
        """
| Term | Meaning in this module |
|---|---|
| **Bar** | One OHLCV row for a fixed interval. Immutable once closed. |
| **Bar-open timestamp** | The index label of a bar = the *start* of its interval. A 14:05 five-minute bar covers 14:05:00–14:09:59.999 and is only complete at 14:10. |
| **t** | The positional index of the bar currently being processed. Never a timestamp inside strategy logic. |
| **t−1** | The previous, fully closed bar. Always legal to read. |
| **t+1** | The next bar. **Never** legal in a decision. Allowed only in hindsight diagnostics ("what happened next"). |
| **Cursor** | The engine's pointer to the current bar. Reads above it raise `LookAheadError`. |
| **Warm-up** | The first *N* bars where indicators are `NaN` and no signals are allowed. |
| **Look-ahead bias** | Using information that did not exist at decision time. The most expensive bug in backtesting. |
| **Vectorised** | Computing a column for all rows at once with pandas. Fast for research, but it is easy to shift in the wrong direction. |
| **Session** | The tradable window of a day (e.g. 13:30–20:00 UTC for NYSE). Crypto has none. |
| **Timezone-aware index** | A `DatetimeIndex` with `tz` set. We standardise on UTC. |
| **Repainting** | A signal that changes as new bars arrive (e.g. an unconfirmed swing). |
| **Signal bar vs fill bar** | The bar where the decision was made vs the bar where the order could actually execute. |
"""
    )

    # ------------------------------------------------------------------ 3
    nb.md(section(3, "Step-by-step walkthrough"))
    nb.md(
        """
### The loop, in order

| Step | What you do | Data you may read | Why |
|---|---|---|---|
| 0 | Validate and sort the frame; make the index UTC | all rows (setup only) | a disordered index makes every later index wrong |
| 1 | `set_cursor(t)` | row `t` becomes visible | the guard's "now" |
| 2 | Build the bar's context (`history` = rows `0..t`) | ≤ t | the strategy's entire world |
| 3 | Compute indicators on that view | ≤ t | values must be causal |
| 4 | Decide and **queue** orders | ≤ t | no fills yet |
| 5 | Let the execution engine fill orders from *earlier* bars | prices of bar `t` | fills happen after the decision |
| 6 | Mark the portfolio to `close[t]` | row `t` | one equity point per bar |
| 7 | Advance to `t+1` and repeat | | |

### Allowed / not allowed at bar `t`

| Expression | Allowed in a decision? | Comment |
|---|---|---|
| `df.iloc[t]` | ✅ | the current, completed bar |
| `df.iloc[t-1]` | ✅ | previous bar |
| `df.iloc[t-2:t+1]` | ✅ | a trailing window ending at `t` |
| `df.shift(1).iloc[t]` | ✅ | same as `t-1` |
| `df.shift(-1).iloc[t]` | ❌ | tomorrow |
| `df.iloc[-1]` inside a loop over `t` | ❌ | always the last row of the whole frame |
| `df.loc[:timestamp_of_t]` | ⚠️ | inclusive label slicing; safe only if you build it from `t`, never from `.max()` |
| `data.bar(t+1)` | ❌ | raises `LookAheadError` |

### The one-sentence rule

> A strategy at bar `t` is a function of rows `0..t` and of its own past decisions.
> Nothing else.

### Where `t+1` *is* allowed

- plotting "entry → next 20 bars" after the run,
- labelling a supervised-learning target (`y = return_{t+1}`),
- debugging: "did the pattern resolve after we entered?"

Those are *descriptions of the future*, not inputs to a decision. Keep them in a
separate function that the strategy never calls.
"""
    )

    # ------------------------------------------------------------------ 4
    nb.md(section(4, "Data and API conventions"))
    nb.md(
        """
### The frame contract

| Property | Requirement | Enforced by |
|---|---|---|
| Index type | `pd.DatetimeIndex`, `tz='UTC'` | `DataHandler` raises `ValueError` |
| Ordering | strictly increasing, no duplicates | `DataHandler` raises |
| Columns | `open, high, low, close, volume` (lowercase) | `DataHandler` raises |
| Row meaning | bar **open** time; bar is complete at `timestamp + timeframe` | convention (documented) |
| Missing data | no NaNs, no `high < low`, no close outside `[low, high]` | `DataHandler` raises |
| Volume | units of the asset (shares/coins), not notional | convention |

### Access patterns

```python
bar   = dh.bar(t)                 # Bar(index, timestamp, o, h, l, c, v)
prev  = dh.bar(t - 1)             # t-1, always legal
nowin = dh.window(t, 20)          # last 20 bars ending at t (inclusive)
before = dh.window_before(t, 20)  # 20 bars ending at t-1
bar   = dh.at_timestamp(ts)       # by timestamp (must be <= cursor)
```

`window(t, n)` never returns `t+1`. That is the whole point: it is impossible to
leak the future through the history API.

### Event/logging format (used from Lesson 3 onwards)

Every decision produces an event with at least:

| Field | Type | Example |
|---|---|---|
| `timestamp` | UTC timestamp | `2024-01-02 14:05:00+00:00` |
| `bar_index` | int | `7` |
| `kind` | str | `BAR`, `SIGNAL`, `STATE`, `ORDER`, `FILL`, `REJECT`, `TRADE`, `NOTE` |
| `message` | str | `"close 100.42 > swing high 100.31"` |
| payload | extra columns | `close`, `position`, `stop`, `qty`, ... |

For Lesson 1 the only payload we need is `close` and `position`.
"""
    )

    # ------------------------------------------------------------------ 5
    nb.md(section(5, "Minimal runnable code"))
    nb.md(
        """
### 5.1 Load and inspect

`load_ohlcv_csv` normalises column names and parses the timestamp as UTC. Nothing
downstream ever has to guess.
"""
    )
    nb.code(
        """
df = load_ohlcv_csv(str(DATA / "sample_5min_equity_1m.csv"))
print(type(df.index).__name__, df.index.tz, "| rows:", len(df))
print("timeframe:", (pd.Series(df.index).diff().median()))
df.head(6)
"""
    )
    nb.md("### 5.2 The smallest honest loop\n\nCompute a 3-bar return and print `t-1`, `t`, `t+1` around the first bars. The `t+1` column exists **only** to make the indexing visible — no decision uses it.")
    nb.code(
        """
def three_bar_return_loop(df: pd.DataFrame, n: int = 6) -> pd.DataFrame:
    \"\"\"Walk bars by position, computing close[t] / close[t-3] - 1.

    At bar t we read t and t-3. Both are <= t. No shift(-1), no .iloc[-1].
    \"\"\"
    rows = []
    for t in range(len(df)):
        ret = np.nan
        if t >= 3:
            ret = df["close"].iloc[t] / df["close"].iloc[t - 3] - 1.0
        rows.append(
            {
                "t": t,
                "timestamp": df.index[t],
                "close_t-1": df["close"].iloc[t - 1] if t >= 1 else np.nan,
                "close_t": df["close"].iloc[t],
                "close_t+1": df["close"].iloc[t + 1] if t + 1 < len(df) else np.nan,
                "ret_3": ret,
            }
        )
    return pd.DataFrame(rows).set_index("t")

out = three_bar_return_loop(df, 6)
out.head(10)
"""
    )
    nb.md(
        """
Read the first rows out loud:

- row 0 has no `t-1` and no `t+1` value for its return,
- row 3 is the first row with a legal 3-bar return (it uses rows 0 and 3),
- `close_t+1` in row 3 is row 4's close — **display only**.

### 5.3 The same thing, vectorised

`pct_change(3)` and the loop must agree exactly. Vectorisation is not a licence to
shift the wrong way; it is the same rule, expressed once for all rows.
"""
    )
    nb.code(
        """
vec = df["close"].pct_change(3)
pd.testing.assert_series_equal(
    vec.iloc[3:].reset_index(drop=True),
    out["ret_3"].iloc[3:].reset_index(drop=True),
    check_names=False,
)
print("loop == vectorised for", len(vec) - 3, "rows")
vec.tail(3)
"""
    )
    nb.md("### 5.4 How a bug looks\n\nThree versions of \"the next bar's return\". Only one is legal as a *label*, none is legal as a *feature*.")
    nb.code(
        """
legal_past = df["close"].pct_change(1)          # ret over (t-1, t]  -> known at t
future     = df["close"].pct_change(1).shift(-1)  # ret over (t, t+1] -> NOT known at t

print("past  (t-1 -> t)   :", round(legal_past.iloc[100], 6))
print("future(t   -> t+1) :", round(future.iloc[100], 6))
print("same number?       :", bool(np.isclose(legal_past.iloc[101], future.iloc[100])))
print("\\nIf a 'strategy' uses the second column as a signal, it is reading tomorrow.")
"""
    )
    nb.md(
        note(
            "A useful habit: when you write `shift`, say the direction out loud. "
            "`shift(1)` moves yesterday into today (safe). `shift(-1)` moves tomorrow "
            "into today (cheating).",
            kind="Coach's note",
        )
    )
    nb.md("### 5.5 `DataHandler`: the guard that makes peeking impossible")
    nb.code(
        """
dh = DataHandler(df, symbol="SYNTH")
dh.set_cursor(10)          # we are processing bar 10

print("bar 10     :", dh.bar(10).as_dict())
print("previous   :", dh.bar(9).close)
print("window(10,5):\\n", dh.window(10, 5)[["close"]])
print("window_before(10,3):\\n", dh.window_before(10, 3)[["close"]])
"""
    )
    nb.code(
        """
try:
    dh.bar(11)                 # tomorrow
except LookAheadError as exc:
    print("LookAheadError:", exc)

try:
    dh.window(15, 3)           # a window ending in the future
except LookAheadError as exc:
    print("LookAheadError:", exc)
"""
    )
    nb.md("### 5.6 Warm-up, sessions, and a strategy skeleton\n\nThis is the shape every later strategy takes: skip the warm-up, then act on a trailing window only.")
    nb.code(
        """
def first_breakout_signals(df: pd.DataFrame, warmup: int = 20, lookback: int = 10) -> pd.DataFrame:
    \"\"\"Mark bars where close[t] exceeds the highest high of the previous `lookback` bars.

    Uses rows t-lookback .. t-1 for the level and row t for the trigger.
    \"\"\"
    signals = []
    for t in range(warmup, len(df)):
        window = df.iloc[t - lookback : t]        # ends at t-1
        level = window["high"].max()
        signals.append(
            {
                "t": t,
                "timestamp": df.index[t],
                "level": level,
                "close": df["close"].iloc[t],
                "signal": bool(df["close"].iloc[t] > level),
            }
        )
    return pd.DataFrame(signals).set_index("t")

sig = first_breakout_signals(df)
print("signals:", int(sig["signal"].sum()), "of", len(sig), "eligible bars")
sig[sig["signal"]].head(5)
"""
    )
    nb.md(
        """
### 5.7 Equity sessions vs 24/7 crypto

The same loop runs on crypto, but there is no session to filter. That difference
is not cosmetic: overnight gaps change stop behaviour and volatility.
"""
    )
    nb.code(
        """
crypto = load_ohlcv_csv(str(DATA / "sample_1min_crypto_3d.csv"))
print("crypto bars per day:", crypto.groupby(crypto.index.date).size().to_dict())
print("equity bars per day:", df.groupby(df.index.date).size().head(3).to_dict())

ny = session_filter(df, start="13:30", end="20:00", tz="UTC")
print("after session filter:", len(ny), "of", len(df), "bars")
"""
    )
    nb.md(
        """
### 5.8 Loop vs vectorised: the honest performance note

A Python loop over 5,000 bars is fine. A loop over 5 years of 1-minute bars
(~500k rows) with DataFrame slicing per row is not. Measure before you optimise.
"""
    )
    nb.code(
        """
import time

def timeit(fn, *a, repeat: int = 3) -> float:
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter(); fn(*a); best = min(best, time.perf_counter() - t0)
    return best

small = df.head(1000).copy()
t_loop = timeit(lambda: [small["close"].iloc[i] > small["close"].iloc[i-1] for i in range(1, len(small))])
t_vec  = timeit(lambda: (small["close"] > small["close"].shift(1)).sum())
print(f"python loop : {t_loop*1000:8.2f} ms / 1,000 bars")
print(f"vectorised  : {t_vec*1000:8.2f} ms / 1,000 bars")
print(f"extrapolated to 500k bars: loop {t_loop*500:6.1f}s vs vector {t_vec*500:5.2f}s")
print("\\nRule: research with vectorised pandas, *verify* one bar at a time, and")
print("backtest event-driven. The loop is the specification; vectorisation is an optimisation.")
"""
    )

    nb.md(
        """
**How to expand this code into a production module**

- [ ] move `load_ohlcv_csv` + validation into `data.py` (already done in `intraday_engine/data.py`);
- [ ] add `session_filter` and `resample_ohlcv` helpers (already in the package);
- [ ] add a `DataHandler` cursor and make every accessor go through it;
- [ ] add gap/duplicate/timestamp-frequency checks to the loader;
- [ ] add a streaming `Feed` class exposing `next_bar()` with the same accessors;
- [ ] keep the notebook's loop as the executable specification for the class.

"""
    )
    # ------------------------------------------------------------------ 6
    nb.md(section(6, "Unit tests"))
    nb.md(
        """
Three properties are worth testing before any strategy exists:

1. a window ending at `t` contains exactly the rows you think it does,
2. reading `t+1` raises,
3. the loop and the vectorised version agree.

The cell writes a pytest file and runs it with the same interpreter as the
notebook. This is exactly how `tests/test_engine.py` is organised.
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
from intraday_engine import DataHandler, LookAheadError, load_ohlcv_csv

@pytest.fixture
def dh():
    df = load_ohlcv_csv(str(BASE / "data" / "sample_5min_equity_1m.csv")).head(60)
    d = DataHandler(df)
    d.set_cursor(30)
    return d, df

def test_window_ends_at_t(dh):
    d, df = dh
    w = d.window(30, 5)
    assert w.index[-1] == df.index[30]
    assert len(w) == 5
    assert df.index[31] not in w.index

def test_previous_bar_is_allowed(dh):
    d, df = dh
    assert d.window_before(30, 1)["close"].iloc[-1] == df["close"].iloc[29]

def test_future_bar_raises(dh):
    d, _ = dh
    with pytest.raises(LookAheadError):
        d.bar(31)

def test_naive_index_rejected():
    df = load_ohlcv_csv(str(BASE / "data" / "pattern_sample.csv")).head(10)
    naive = df.tz_localize(None)
    with pytest.raises(ValueError):
        DataHandler(naive)
'''
path = Path(tempfile.mkdtemp()) / "test_lesson1.py"
path.write_text(test_code)
import subprocess
res = subprocess.run([sys.executable, "-m", "pytest", "-q", str(path)], capture_output=True, text=True)
print(res.stdout[-1200:])
"""
    )

    # ------------------------------------------------------------------ 7
    nb.md(section(7, "Example input and expected output"))
    nb.md(
        """
A 10-row slice of the hand-crafted `pattern_sample.csv`. We ask a simple
question: **what is the previous close for each bar?** This is the smallest
possible test of `t-1` access, and the one that catches most off-by-one bugs.
"""
    )
    nb.code(
        """
ps = load_ohlcv_csv(str(DATA / "pattern_sample.csv"))
sample = ps.head(10).copy()
sample["prev_close"] = sample["close"].shift(1)          # legal: t-1
sample["next_close_DISPLAY_ONLY"] = sample["close"].shift(-1)  # never use in a decision
sample
"""
    )
    nb.md(
        """
**Expected values to verify by hand:**

| Row | Close | `prev_close` (t−1) | `next_close` (display) |
|---|---|---|---|
| 0 | 100.10 | NaN (no previous bar) | 100.30 |
| 1 | 100.30 | 100.10 | 100.55 |
| 5 | 101.00 | 100.80 | 101.00 |
| 9 | 101.35 | 100.95 | 101.25 |

The first row has no `t-1`; this is why warm-up exists. A strategy that treats
`NaN` as zero will trade on bar 1 and lose money to noise.
"""
    )

    # ------------------------------------------------------------------ 8
    nb.md(section(8, "Exercises"))
    nb.md(
        """
### Exercise 1.1 — loop without `shift`
Implement `pct_change_manual(series, lag)` using a for-loop over positions.
Return a `pd.Series` aligned with the input. Test that it equals
`series.pct_change(lag)` for `lag=1` and `lag=5`.

*Hint:* the first `lag` values are `NaN`. Do not silently fill them.

### Exercise 1.2 — find the bug
The following "strategy" reports a suspiciously high hit rate. Explain why and
fix it:

```python
for t in range(20, len(df)):
    window = df.iloc[t-20:]        # <-- look carefully
    level = window["high"].max()
    if df["close"].iloc[t] > level:
        hits += 1
```

*Hint:* count how many rows the slice returns and whether row `t` is inside
the "previous" high.

### Exercise 1.3 — session guard
Write `in_session(ts, start="13:30", end="20:00", tz="UTC") -> bool`.
Use it to filter the equity sample, then show that crypto (24/7) has roughly
1,440 bars/day at 1-minute frequency while equities have 78 (6.5 h × 12 bars/h).

### Exercise 1.4 — warm-up audit
Pick any indicator (`atr(df, 14)`). For how many bars is it `NaN`? What happens
to a strategy that starts trading at bar 0? Add an assertion to your loop that
refuses to emit a signal while any required indicator is `NaN`.

### Exercise 1.5 — replay by timestamp
Given a `DataHandler`, write `row_as_of(dh, timestamp)` that returns the most
recent bar at or before `timestamp` **without** exceeding the cursor. Test it
with a timestamp between two bars.

"""
    )
    nb.md(
        note(
            "Do Exercise 1.2 on paper first. `df.iloc[t-20:]` looks like a trailing "
            "window but it includes rows up to the end of the frame — including `t+1`. "
            "This single bug has produced more fake edges than any other line of pandas.",
            kind="Coach's note",
        )
    )

    # ------------------------------------------------------------------ 9
    nb.md(section(9, "Common pitfalls and debugging"))
    nb.md(
        """
| Pitfall | Symptom | How to test |
|---|---|---|
| `.iloc[-1]` inside a loop | impossible accuracy; signals at every bar | replace with `.iloc[t]`; assert max index accessed `<= t` |
| `shift(-1)` in a feature | win rate > 70% on noise | grep for `shift(-`; add a test that mutates `df.iloc[t+1]` and asserts unchanged signals |
| Label slicing `.loc[:ts]` | includes one bar more than you think | compare with `.iloc[:t+1]` |
| NaNs treated as 0 | trades during warm-up | assert `notna()` before signalling |
| Naive timestamps | session filter off by hours; DST bugs | `assert df.index.tz is not None` |
| Duplicate timestamps | doubled bars, wrong volatility | `assert not df.index.has_duplicates` |
| Off-by-one in `range` | last bar never processed or first bar processed twice | log first/last index processed |
| Using `datetime.now()` | non-reproducible results | ban clock reads in strategy code |

**The mutation test** is the strongest anti-look-ahead test you can write:

```python
df2 = df.copy()
df2.iloc[t+1:, :] *= 10          # destroy the future
# signals produced up to bar t must be identical
```

Run it as a property test over a handful of `t` values. If a future change leaks
in, the test fails immediately.
"""
    )

    # ------------------------------------------------------------------ 10
    nb.md(section(10, "Recommended logging and diagnostics"))
    nb.md(
        """
Log per bar (only for the bars you are debugging — a full bar log is large):

| Field | Why |
|---|---|
| `bar_index`, `timestamp` | replay and join with trades |
| `open/high/low/close` | reconstruct decisions |
| `position` | know whether a signal was actionable |
| `close_t-1` or the indicator values used | prove what the strategy saw |
| `cursor` | catch any access beyond it |

Diagnostics that pay for themselves:

```python
print(df.index.is_monotonic_increasing, df.index.has_duplicates, df.index.tz)
print(df.isna().sum())
print(df.index.to_series().diff().value_counts().head())    # gaps and frequency changes
```

The last one catches missing bars, early closes and half-days — all of which
change results silently.

**Next lesson:** once the loop is trustworthy, the question becomes *what does
the strategy remember between bars?* That is where state machines enter.
"""
    )
    return nb
