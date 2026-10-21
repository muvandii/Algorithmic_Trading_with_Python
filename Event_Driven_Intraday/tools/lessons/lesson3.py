"""Notebook 03 — events and multi-stage entries."""

from __future__ import annotations

from .common import Notebook, header, note, section

FILENAME = "03_events_and_multi_stage_entries.ipynb"
TITLE = "Events and multi-stage entries"


def build() -> Notebook:
    """Return Lesson 3."""
    nb = Notebook(TITLE)
    nb.md(header(3, "Events and multi-stage entries",
                 "Liquidity sweeps, breaks of structure and fair value gaps — detected causally, sequenced explicitly."))
    nb.setup()

    nb.md(section(1, "Learning objectives"))
    nb.md(
        """
By the end of this lesson you can:

1. **Define** a confirmed swing, a liquidity sweep, a break of structure (BOS) and a fair value gap (FVG) precisely enough to implement and test.
2. **Detect** each pattern using only bars `≤ t`, and state the exact bar on which the pattern becomes knowable.
3. **Sequence** the three patterns into a multi-stage entry with explicit arming, confirmation, expiry and invalidation.
4. **Log** each stage as a structured event with levels, direction and reason, so a trade can be replayed from the journal alone.
5. **Recognise repainting**: the difference between a pivot that *will* be a swing and one that *is* confirmed.
"""
    )

    nb.md(section(2, "Key concepts and definitions"))
    nb.md(
        """
| Term | Definition used in this module |
|---|---|
| **Swing high (confirmed)** | `high[k] == max(high[k-left : k+right+1])`, knowable only at bar `k+right`. |
| **Swing low** | Mirror image for lows. |
| **Liquidity** | Resting stop/limit orders above highs and below lows. |
| **Liquidity sweep** | Price trades beyond a confirmed swing level and closes back inside it: stops were taken, the move failed. Sell-side sweep = wick below swing low, close above it (bullish intent). |
| **Break of structure (BOS)** | A close beyond the most recent confirmed opposite swing, confirming direction. A close, not a wick. |
| **Change of character (CHoCH)** | The first BOS against the prevailing trend; often used as the reversal signal. Same mechanics, different context. |
| **Fair value gap (FVG) / imbalance** | Three-bar inefficiency: `low[t] > high[t-2]` (bullish) or `high[t] < low[t-2]` (bearish). Zone = `[high[t-2], low[t]]`. |
| **Mitigation** | Price returning into an FVG. A bullish gap is "mitigated" when a later low trades into the zone. |
| **Consequent encroachment** | The 50% level of an FVG; a common limit-entry price. |
| **Confluence** | Two or more independent reasons for the same trade. |
| **Arming** | Recording a sweep and waiting for confirmation. |
| **Confirmation bar** | The bar whose *close* completes the pattern. |
| **Invalidation** | The condition that cancels the setup (time, level, opposite BOS). |
| **Repainting** | A signal whose historical location changes as new bars arrive. |
| **Expiry** | A bar-count limit on how long a setup may wait for the next stage. |
"""
    )

    nb.md(section(3, "Step-by-step walkthrough"))
    nb.md(
        """
### 3.1 The sequence (long side)

| Stage | Condition (all at bar `t`, using rows ≤ t) | Becomes knowable | If false |
|---|---|---|---|
| 0. Context | enough history for pivots (`≥ lookback + right + 2`) | `t` | wait |
| 1. Sweep | `low[t] < swing_low` **and** `close[t] > swing_low`, where `swing_low` is confirmed by `t-1` | close of `t` | stay `FLAT` |
| 2. Arm | store sweep extreme (the wick low) and the nearest confirmed swing high (structure level) | `t` | expire after `expiry_bars` |
| 3. BOS | `close[t-1] <= level < close[t]` | close of `t` | expire |
| 4. FVG | an unmitigated bullish FVG exists in the last `fvg_lookback` bars | close of the FVG's third bar | wait until expiry |
| 5. Entry | limit at FVG midpoint, or market at next open | next bar's open | expire |
| 6. Bracket | stop below sweep extreme minus buffer; target = entry + `R × (entry − stop)` | at entry | exit |

For shorts, mirror every comparison. The code does not use `if long ... else ...`
in the detectors; direction is explicit and returned with the event.

### 3.2 Why a *confirmed* swing matters

A pivot found with `right=0` at bar `k` is "the high so far". At bar `k+1` it may
stop being a high. If your detector uses it, your backtest will place a sweep at a
price that, historically, only looked like a swing later. That is repainting.

| `right` | Swing at row 10 known at row… | Cost |
|---|---|---|
| 0 | 10 | repaints; do not use |
| 1 | 11 | fastest honest confirmation |
| 2 | 12 | fewer, stronger swings |
| 3+ | 13+ | slower entries, fewer false pivots |

### 3.3 The FVG has three bars, and only the third completes it

At bar `t`, the pattern uses `t-2`, `t-1`, `t`. If you evaluate the gap at `t-1`
you are reading one bar that has not closed. The completion bar is part of the
event: log `fvg_completed_index = t`.

### 3.4 Sequencing without a tangle of booleans

The state machine from Lesson 2 is the right tool. `generate()` advances one
stage per bar at most, stores its context, and returns an order when — and only
when — all preconditions are true. Every stage gets its own `STATE` event so the
journal reads like a story.
"""
    )

    nb.md(section(4, "Data and API conventions"))
    nb.md(
        """
### Detector contracts

| Function | Input | Returns | Guarantee |
|---|---|---|---|
| `swing_points(df, left, right)` | frame ending at `t` | `list[Swing(index, confirmed_index, ...)]` | only pivots confirmed by the last row |
| `detect_sweep(df, lookback, left, right, ...)` | frame ending at `t` | `dict` or `None` | the sweep is confirmed by the last row's close |
| `detect_bos(df, short_len, left, right)` | frame ending at `t` | `dict` or `None` | close-based, uses prior confirmed swings |
| `detect_fvg(df)` | frame ending at `t`, ≥3 rows | `Fvg` or `None` | completed by the last row |
| `active_fvgs(df, direction, lookback)` | frame ending at `t` | `list[Fvg]` | unmitigated as of the last row |

### Event schema for signals

| Field | Type | Example | Required |
|---|---|---|---|
| `timestamp`, `bar_index` | UTC ts, int | `2024-01-02 15:25` / `17` | yes |
| `kind` | str | `SIGNAL` | yes |
| `side` | `buy`/`sell` | `buy` | yes |
| `reason` | str | `"sellside sweep + BOS + FVG"` | yes |
| `entry_ref` | float | `101.10` | yes |
| `stop`, `target` | float | `99.95`, `103.40` | yes |
| `sweep_level`, `sweep_extreme` | float | `100.55`, `100.10` | recommended |
| `fvg_lower`, `fvg_upper` | float | `100.90`, `101.30` | recommended |
| `structure_level` | float | `101.45` | recommended |
| `qty` | float | `640.2` | added by sizing |
| `expires_after` | int | `12` | for limit orders |

### Frame requirements

Same as Lesson 1: UTC `DatetimeIndex`, ascending, `open/high/low/close/volume`.
The detectors never mutate their input and never look past the last row.
"""
    )

    nb.md(section(5, "Minimal runnable code"))
    nb.md("### 5.1 Swings — knowability is part of the output")
    nb.code(
        """
ps = load_ohlcv_csv(str(DATA / "pattern_sample.csv"))

for end in (11, 12, 13):
    swings = swing_points(ps.iloc[:end], left=2, right=2)
    print(f"rows 0..{end-1:2d}:", [(s.index, s.kind, s.price, f"known@{s.confirmed_index}") for s in swings])

print("\\nRow 10's high is 101.45. With right=2 it becomes a confirmed swing only at row 12.")
print("A detector that assumes it knows at row 10 is repainting.")
"""
    )
    nb.md("### 5.2 The three detectors on the hand-planted sample")
    nb.code(
        """
print("FVG at row 10 :", detect_fvg(ps.iloc[:11]))
print("FVG before    :", detect_fvg(ps.iloc[:10]))
print()
print("Sweep at row 17:", detect_sweep(ps.iloc[:18], lookback=20, left=2, right=1))
print("Sweep at row 16:", detect_sweep(ps.iloc[:17], lookback=20, left=2, right=1))
print()
print("BOS at row 19  :", detect_bos(ps.iloc[:20], short_len=10, left=2, right=1))
print("BOS at row 18  :", detect_bos(ps.iloc[:19], short_len=10, left=2, right=1))
"""
    )
    nb.md("### 5.3 Scan the sample bar by bar\n\nThis is the honest way to see a detector: at each bar, print what was knowable *then*. Nothing is allowed to appear twice, and nothing may move.")
    nb.code(
        """
rows = []
for t in range(3, len(ps)):
    window = ps.iloc[: t + 1]
    fvg = detect_fvg(window)
    sweep = detect_sweep(window, lookback=20, left=2, right=1)
    bos = detect_bos(window, short_len=10, left=2, right=1)
    if fvg or sweep or bos:
        rows.append({
            "bar": t,
            "time": window.index[-1].strftime("%H:%M"),
            "close": window["close"].iloc[-1],
            "event": "FVG" if fvg else ("SWEEP" if sweep else "BOS"),
            "direction": (fvg.direction if fvg else (sweep or bos)["direction"]),
            "detail": (f"[{fvg.lower:.2f}, {fvg.upper:.2f}]" if fvg else
                       (f"level {sweep['level']:.2f} wick {sweep['extreme']:.2f}" if sweep else
                        f"level {bos['level']:.2f}")),
        })
pd.DataFrame(rows)
"""
    )
    nb.md(
        """
Read the table carefully. Each pattern appears on its **completion bar** and
never moves afterwards: the gap at row 10, the sweep at row 17, the BOS at row 19,
the gap at row 20. You will also see smaller gaps at rows 3 and 6 and a bearish
sweep at row 21 — that is real data, and it is why the *sequence* and the filters
matter. A detector that re-reports the same pattern on every later bar would let
your strategy "discover" one idea dozens of times and size into it repeatedly.
"""
    )
    nb.md("### 5.4 FVG lifecycle: formation, mitigation, invalidation")
    nb.code(
        """
gaps = active_fvgs(ps.iloc[:21], direction="bullish", lookback=12)
for g in gaps:
    print(f"gap formed at {g.index} ({g.timestamp:%H:%M}) zone=[{g.lower:.2f}, {g.upper:.2f}] mid={g.midpoint:.2f} size={g.size:.2f}")

later = ps.iloc[:23]
g = detect_fvg(ps.iloc[:21])
mitigated = later["low"].iloc[21:] <= g.midpoint
print("\\nRow 21 low:", later['low'].iloc[21], "| row 22 low:", later['low'].iloc[22],
      "| midpoint reached:", bool(mitigated.any()))
print("Gap after mitigation is no longer tradable as a fresh imbalance.")
"""
    )
    nb.md("### 5.5 From detectors to a multi-stage strategy\n\nThe strategy stores its stage and only advances one step per bar. Run it on 2,000 equity bars and inspect the journal.")
    nb.code(
        """
df = load_ohlcv_csv(str(DATA / "sample_5min_equity_1m.csv"))
strategy = SweepBosFvgStrategy(
    SweepBosFvgParams(entry_mode="limit", expiry_bars=12, r_multiple=2.0),
    sizer=FixedFractionSizer(risk_pct=0.01),
)
result = BacktestEngine.build(df, strategy, initial_cash=100_000,
                              model=ExecutionModel(fee_bps=2, slippage_bps=1, stop_slippage_bps=4)).run()
print(result.summary()["trades"], "trades")
print(result.events["kind"].value_counts().to_dict())
"""
    )
    nb.code(
        """
# The story of the first signal: signal -> order -> fill -> exit
ev = result.events
first_signal_idx = ev.index[ev["kind"] == "SIGNAL"][0]
window = ev.iloc[max(0, first_signal_idx - 2): first_signal_idx + 6]
window[["timestamp", "bar_index", "kind", "message", "side", "qty", "entry_ref", "stop", "target", "reason"]]
"""
    )
    nb.code(
        """
signals = result.events[result.events["kind"] == "SIGNAL"].copy()
signals["timestamp"] = signals["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
signals[["timestamp", "bar_index", "side", "entry_ref", "stop", "target", "fvg_lower", "fvg_upper", "reason"]].head(10)
"""
    )

    nb.md(
        """
**How to expand this code**

- [ ] move the detectors into `structure.py` (done in the package) and keep them pure;
- [ ] add an `Event` dataclass for detections instead of dicts, with a schema version;
- [ ] add ATR-normalised filters (`min_penetration_atr`, `min_gap_atr`);
- [ ] add equal-highs/equal-lows clustering for real liquidity levels;
- [ ] add a `Setup` object that carries the three stages and serialises to JSON;
- [ ] add a replay tool that re-renders the bars around any signal from the journal.

**Complexity note:** `swing_points` is O(n·(left+right)) per call; `detect_sweep`
calls it on a `lookback` window, so each bar costs O(lookback). If you call the
detector on the whole growing history every bar you have built an O(n²) strategy.
Always pass a bounded window (`ctx.history.tail(warmup)`), or maintain the swings
incrementally.

"""
    )
    nb.md(section(6, "Unit tests"))
    nb.md(
        """
The pattern sample exists so these tests can assert **exact rows**. A detector
that is "roughly right" is not testable; an exact index is.
"""
    )
    nb.code(
        """
test_code = '''
import sys
from pathlib import Path
import pytest

BASE = next(p for p in (Path.cwd(), Path.cwd().parent) if (p / "intraday_engine").is_dir())
sys.path.insert(0, str(BASE))
from intraday_engine import load_ohlcv_csv, detect_fvg, detect_sweep, detect_bos, swing_points

@pytest.fixture
def ps():
    return load_ohlcv_csv(str(BASE / "data" / "pattern_sample.csv"))

def test_fvg_completes_at_row_10(ps):
    assert detect_fvg(ps.iloc[:10]) is None          # needs bars 8,9,10
    fvg = detect_fvg(ps.iloc[:11])
    assert fvg.index == 10
    assert (fvg.lower, fvg.upper) == (101.00, 101.20)

def test_sweep_only_after_close_back_inside(ps):
    assert detect_sweep(ps.iloc[:17], lookback=20) is None
    sweep = detect_sweep(ps.iloc[:18], lookback=20)
    assert sweep["direction"] == "bullish"
    assert sweep["level"] == pytest.approx(100.55)

def test_bos_is_close_based(ps):
    assert detect_bos(ps.iloc[:19], short_len=10) is None   # row 18 close 100.85
    bos = detect_bos(ps.iloc[:20], short_len=10)
    assert bos["level"] == pytest.approx(101.45)

def test_swing_needs_confirmation_bars(ps):
    unconfirmed = {s.index for s in swing_points(ps.iloc[:12], left=2, right=2)}
    assert 10 not in unconfirmed
    confirmed = {s.index for s in swing_points(ps.iloc[:13], left=2, right=2)}
    assert 10 in confirmed

def test_detectors_do_not_mutate_input(ps):
    before = ps.copy()
    detect_fvg(ps); detect_sweep(ps); detect_bos(ps)
    assert ps.equals(before)
'''
path = Path(tempfile.mkdtemp()) / "test_lesson3.py"
path.write_text(test_code)
import subprocess
res = subprocess.run([sys.executable, "-m", "pytest", "-q", str(path)], capture_output=True, text=True)
print(res.stdout[-900:])
"""
    )

    nb.md(section(7, "Example input and expected output"))
    nb.md(
        """
The planted sample, rows 8–21 (all times UTC):

| Row | Time | Open | High | Low | Close | What is knowable at this close |
|---|---|---|---|---|---|---|
| 8 | 14:40 | 100.95 | 101.00 | 100.85 | 100.95 | — |
| 9 | 14:45 | 100.95 | 101.40 | 100.95 | 101.35 | — |
| 10 | 14:50 | 101.35 | 101.45 | 101.20 | 101.25 | **bullish FVG `[101.00, 101.20]`** |
| 15 | 15:15 | 100.75 | 100.80 | 100.55 | 100.60 | swing low 100.55 confirmed (with right=1) |
| 17 | 15:25 | 100.70 | 100.85 | 100.10 | 100.65 | **sell-side sweep of 100.55** (wick 100.10, close back above) |
| 18 | 15:30 | 100.65 | 100.90 | 100.55 | 100.85 | still armed |
| 19 | 15:40 | 100.85 | 101.70 | 100.80 | 101.60 | **BOS**: close > structure 101.45 |
| 20 | 15:45 | 101.60 | 101.75 | 101.30 | 101.40 | **bullish FVG `[100.90, 101.30]`** (from the impulse) |
| 21 | 15:50 | 101.40 | 101.50 | 101.25 | 101.20 | trades into the gap; midpoint 101.10 not yet reached |

**Expected detector outputs**

| Call | Expected |
|---|---|
| `detect_fvg(df.iloc[:11])` | `Fvg(index=10, direction='bullish', lower=101.00, upper=101.20)` |
| `detect_sweep(df.iloc[:18], lookback=20)` | `{'direction': 'bullish', 'level': 100.55, 'extreme': 100.10, 'index': 17}` |
| `detect_bos(df.iloc[:20], short_len=10)` | `{'direction': 'bullish', 'level': 101.45, 'close': 101.60}` |
| `detect_sweep(df.iloc[:19], lookback=20)` | `None` (row 18 has no sweep) |
| `detect_fvg(df.iloc[:21])` | `Fvg(index=20, lower=100.90, upper=101.30)` |
"""
    )
    nb.code(
        """
expected = pd.DataFrame({
    "bar": [10, 17, 19, 20],
    "event": ["FVG", "SWEEP", "BOS", "FVG"],
    "direction": ["bullish"] * 4,
    "zone_or_level": ["[101.00, 101.20]", "100.55", "101.45", "[100.90, 101.30]"],
})
expected
"""
    )

    nb.md(section(8, "Exercises"))
    nb.md(
        """
### Exercise 3.1 — equal highs
Add a filter so a sweep only counts if the swept level was touched at least twice
in the lookback (equal highs/lows, i.e. real liquidity). *Hint:* cluster swing
prices within `0.1 × ATR` and require `len(cluster) >= 2`.

### Exercise 3.2 — FVG entry variants
Compare three entries on the same setups over 2,000 bars: (a) limit at the
midpoint, (b) limit at the proximal edge (the gap's upper bound for a bullish
gap), (c) market at the next open. Report fill rate, average R and expectancy.
Which one *looks* best and which one is most robust to doubling slippage?

### Exercise 3.3 — invalidation
Add "invalidate the setup if price closes back below the sweep extreme before the
BOS". Count how many signals disappear. What does that tell you about the quality
of the sweep filter?

### Exercise 3.4 — non-repainting proof
Write a test that, for every `t`, computes the detectors on `df.iloc[:t+1]` and
then again on `df.iloc[:t+5]`; the detection **for bar `t`** must be identical in
both. Fix any function that fails.

### Exercise 3.5 — one event per idea
Your strategy must not enter twice on the same FVG. Add the gap's completion bar
to the state and reject signals whose `fvg_completed_index` was already traded.
Test it on a sample where price revisits the same gap twice.

### Exercise 3.6 — multi-timeframe confluence
Resample the 5-min bars to 15-min inside the strategy (using only completed 15-min
bars) and only take sweeps aligned with the 15-min trend. Measure the change in
trade count and hit rate.
"""
    )
    nb.md(
        note(
            "Pattern names are cheap; definitions are expensive. If you cannot state "
            "the exact bar on which your 'sweep' is knowable, you do not have a "
            "signal — you have a story you can only tell after the fact.",
            kind="Coach's note",
        )
    )

    nb.md(section(9, "Common pitfalls and debugging"))
    nb.md(
        """
| Pitfall | Symptom | Diagnosis / fix |
|---|---|---|
| Unconfirmed pivots (`right=0`) | entries at prices that never traded | require `right >= 1`; test the confirmation bar |
| Wick-based BOS | too many fake breaks | use closes for structure, wicks for sweeps |
| Gap definition off-by-one | FVGs everywhere / nowhere | require `low[t] > high[t-2]` strictly |
| Detector fires every bar | duplicated entries | return the completion index; deduplicate |
| Sweep without close-back | entering into a genuine breakdown | require `close > level` for a sell-side sweep |
| No expiry | stuck `ARMED` state | bar-count expiry, tested |
| Lookback shorter than confirmation | silent `None`s early in the data | warm-up >= `lookback + right + 2` |
| Mitigated gaps reused | entering on stale information | track mitigation with future *known* bars only |
| Same idea, three sizes | correlated risk | one position, one setup id |
"""
    )

    nb.md(section(10, "Recommended logging and diagnostics"))
    nb.md(
        """
For every stage, log the evidence, not just the conclusion:

| Event | Must contain |
|---|---|
| `SWEEP` | `level`, `extreme`, `close`, `lookback`, `confirmation_bar` |
| `BOS` | `level`, `close`, `prev_close`, `direction` |
| `FVG` | `lower`, `upper`, `midpoint`, `completion_bar`, `direction` |
| `STATE` | `from`, `to`, `reason`, the setup dict |
| `SIGNAL` | entry, stop, target, R, qty, confluence fields |
| `REJECT` | why (expired, duplicate, wrong side, size 0) |

Diagnostics worth running once per dataset:

```python
counts = result.events["kind"].value_counts()
arms = counts.get("STATE", 0)
signals = counts.get("SIGNAL", 0)
fills = counts.get("FILL", 0)
print(f"armed -> signal conversion: {signals / max(arms, 1):.1%}")
```

A conversion rate near 0% means the sequence is too strict; near 100% means the
"confirmation" is not filtering anything.

**Next lesson:** the signal is not the trade. Sizing, stops, fees and slippage
decide whether the idea survives contact with a broker.
"""
    )
    return nb
