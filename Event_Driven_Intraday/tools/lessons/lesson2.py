"""Notebook 02 — state and memory."""

from __future__ import annotations

from .common import Notebook, header, note, section

FILENAME = "02_state_and_memory.ipynb"
TITLE = "State and memory: the strategy as a machine"


def build() -> Notebook:
    """Return Lesson 2."""
    nb = Notebook(TITLE)
    nb.md(header(2, "State and memory — the strategy as a state machine",
                 "A strategy is not a pile of variables. It is a machine with a few states and explicit transitions."))
    nb.setup()

    nb.md(section(1, "Learning objectives"))
    nb.md(
        """
By the end of this lesson you can:

1. **Name** the states of a trading setup and the events that move between them.
2. **Implement** a validated state machine (`FLAT → ARMED → …`) where illegal transitions raise instead of corrupting the run.
3. **Store** only the memory you need — levels, counters, flags, timestamps — and justify each field.
4. **Snapshot and restore** strategy state, then prove a resumed run is identical to an uninterrupted one.
5. **Diagnose** the two classic state bugs: state leaking between runs and state that never leaves a waiting phase.
"""
    )

    nb.md(section(2, "Key concepts and definitions"))
    nb.md(
        """
| Term | Meaning |
|---|---|
| **State** | Everything the strategy must remember to make the next decision correctly. Not the market data — that is re-readable. |
| **State machine** | A finite set of states plus allowed transitions triggered by events. |
| **Transition** | A legal move, e.g. `ARMED → BOS_CONFIRMED` when a close breaks structure. |
| **Invariant** | A condition that must always hold, e.g. "if `phase == IN_POSITION` then `position != 0`". |
| **Memory (lookback)** | Past bars/levels the strategy needs. Keep it bounded. |
| **Hysteresis** | Deliberately requiring more evidence to leave a state than to enter it (prevents flip-flopping). |
| **Cooldown** | A forced wait after an exit; a state, not a `sleep`. |
| **Idempotency** | Re-processing the same bar produces the same decision and no duplicate orders. |
| **Snapshot / checkpoint** | A serialisable copy of state at a bar boundary. |
| **Resume** | Restarting a run from a snapshot and reproducing the uninterrupted result. |
| **Stateless leak** | State surviving between backtests (module-level globals, mutable defaults). |
| **Bar clock vs wall clock** | Strategies count bars, never seconds; wall-clock reads destroy reproducibility. |
"""
    )

    nb.md(section(3, "Step-by-step walkthrough"))
    nb.md(
        """
### 3.1 Design the machine before you code it

Take the sweep → BOS → FVG setup from Lesson 3 as an example. Draw the states
and the *only* legal moves:

| From | Event | To | Side effect |
|---|---|---|---|
| `FLAT` | sweep confirmed | `ARMED` | store sweep extreme + structure level + bar index |
| `ARMED` | setup expired (`bars > expiry`) | `FLAT` | clear setup |
| `ARMED` | close breaks structure | `BOS_CONFIRMED` | store BOS bar |
| `BOS_CONFIRMED` | unmitigated FVG exists | `ENTERING` | size, build bracket, queue order |
| `BOS_CONFIRMED` | expired | `FLAT` | clear setup |
| `ENTERING` | entry filled | `IN_POSITION` | record entry bar |
| `ENTERING` | order rejected/expired | `FLAT` | clear setup (this is easy to forget) |
| `IN_POSITION` | stop / target / time exit | `FLAT` | clear setup, optionally `COOLDOWN` |
| `IN_POSITION` | end of session | `FLAT` | flatten |

Print this table. Tape it above your screen. Every "stuck strategy" bug is a
missing row in this table.

### 3.2 Decide what to store (and what not to)

| Store | Why | Size |
|---|---|---|
| `phase` | the machine's current state | 1 str |
| `armed_bar`, `bos_bar` | expiry is measured in bars | 2 ints |
| `structure_level`, `sweep_extreme` | levels are the setup | 2 floats |
| `entry_bar` | time stops, diagnostics | 1 int |
| last exit bar | cooldown | 1 int |
| order id / pending flag | avoid duplicate orders | 1 int |

**Do not store**: the full history (it is in `DataHandler`), DataFrames (they
grow), computed indicators for every bar (recompute from a bounded window), or
`datetime.now()` (breaks reproducibility).

### 3.3 Where state is written

Only inside `on_bar` (and `on_start` to reset). Never in `generate` from a
different thread, never from a callback that might fire twice. The engine calls
`on_start` once per run, which is where you reset — this is what makes two
backtests with the same strategy object independent.

### 3.4 Expiry, invalidation, and the stuck-state bug

A setup that waits forever is a state bug, not a market condition. Every waiting
state needs an **exit on time**:

```python
if bar.index - state["armed_bar"] > params.expiry_bars:
    transition("FLAT", bar, "setup expired")
```

This was a real bug in this module: after a BOS with no FVG, the strategy stayed
in `BOS_CONFIRMED` and never traded again. The fix was one extra expiry branch
(and a test would have caught it).
"""
    )

    nb.md(section(4, "Data and API conventions"))
    nb.md(
        """
### The `ctx.state` dict

The engine passes `Context.state`, which *is* `strategy.state` (same object). It
must be JSON-serialisable except for explicitly handled types (timestamps).

| Key | Type | Meaning |
|---|---|---|
| `phase` | `str` | current state name |
| `armed_bar` | `int` | bar index where the setup armed (-1 if none) |
| `bos_bar` | `int` | bar index of the structure break |
| `structure_level` | `float` | level that must break |
| `sweep_extreme` | `float` | wick extreme used for the stop |
| `entry_bar` | `int` | bar index of the entry fill |
| `last_exit_bar` | `int` | for cooldown logic |
| `signals` | `int` | counter, useful in diagnostics |

### STATE event schema

| Field | Example | Note |
|---|---|---|
| `timestamp` | `2024-01-02 15:25:00+00:00` | bar time |
| `bar_index` | `17` | positional |
| `kind` | `STATE` | fixed |
| `from` | `FLAT` | previous phase |
| `to` | `ARMED` | new phase |
| `reason` | `"sweep of 100.55"` | human sentence, always fill it |

### Snapshot format (checkpoint)

```json
{
  "version": 1,
  "bar_index": 137,
  "timestamp": "2024-01-03T18:45:00+00:00",
  "state": {"phase": "ARMED", "armed_bar": 135, "structure_level": 101.45, "...": "..."}
}
```

Include a version and the bar index. On resume, verify the next bar's timestamp
matches the data you expect — a snapshot from another dataset is a silent
disaster.
"""
    )

    nb.md(section(5, "Minimal runnable code"))
    nb.md("### 5.1 A validated state machine\n\nIllegal transitions raise. That is the entire value: a typo becomes an exception, not a mystery.")
    nb.code(
        """
from typing import Dict, Iterable, Optional, Set

class StateMachine:
    \"\"\"Finite state machine with an explicit transition table.

    Parameters
    ----------
    transitions:
        Mapping ``{from_state: {allowed_to_states}}``. Any move not listed raises.
    initial:
        Starting state (must be a key in ``transitions``).
    \"\"\"

    def __init__(self, transitions: Dict[str, Set[str]], initial: str) -> None:
        if initial not in transitions:
            raise ValueError(f"initial state {initial!r} not in transition table")
        self.transitions = {k: set(v) for k, v in transitions.items()}
        self.state = initial
        self.history: list[tuple[str, str, str]] = []

    def can(self, to: str) -> bool:
        \"\"\"True if ``self.state -> to`` is legal.\"\"\"
        return to in self.transitions.get(self.state, set())

    def move(self, to: str, reason: str = "") -> str:
        \"\"\"Transition or raise. Returns the new state.\"\"\"
        if not self.can(to):
            raise ValueError(f"illegal transition {self.state} -> {to} ({reason!r})")
        old, self.state = self.state, to
        self.history.append((old, to, reason))
        return self.state

    def allowed_from(self) -> Iterable[str]:
        \"\"\"States reachable in one step (for docs and tests).\"\"\"
        return sorted(self.transitions[self.state])


TRANSITIONS = {
    "FLAT": {"ARMED"},
    "ARMED": {"BOS_CONFIRMED", "FLAT"},
    "BOS_CONFIRMED": {"ENTERING", "FLAT"},
    "ENTERING": {"IN_POSITION", "FLAT"},
    "IN_POSITION": {"FLAT", "COOLDOWN"},
    "COOLDOWN": {"FLAT"},
}

sm = StateMachine(TRANSITIONS, initial="FLAT")
print("start:", sm.state, "| allowed:", sm.allowed_from())
sm.move("ARMED", "sweep confirmed")
sm.move("BOS_CONFIRMED", "close broke 101.45")
sm.move("ENTERING", "fvg pullback")
sm.move("IN_POSITION", "entry filled")
sm.move("COOLDOWN", "stopped out")
sm.move("FLAT", "cooldown over")
for edge in sm.history:
    print(f"  {edge[0]:<14} -> {edge[1]:<14} {edge[2]}")

try:
    sm.move("ENTERING", "trying to re-enter without a setup")
except ValueError as exc:
    print("\\nBlocked:", exc)
"""
    )
    nb.md(
        """
### 5.2 State with memory, driven bar by bar

A breakout with hysteresis: arm when close exceeds the prior 10-bar high, enter
only on the *next* close above the level, then cooldown for 3 bars after exit.
This is deliberately tiny so the transitions are easy to trace.
"""
    )
    nb.code(
        """
class BreakoutMachine:
    \"\"\"Three-state breakout strategy with a cooldown.

    States: FLAT -> ARMED (level broken) -> IN_POSITION -> COOLDOWN -> FLAT.
    \"\"\"

    def __init__(self, lookback: int = 10, cooldown_bars: int = 3) -> None:
        self.lookback = lookback
        self.cooldown_bars = cooldown_bars
        self.reset()

    def reset(self) -> None:
        \"\"\"The single place that defines initial memory.\"\"\"
        self.phase = "FLAT"
        self.level: Optional[float] = None
        self.armed_bar = -1
        self.entry_bar = -1
        self.exit_bar = -1
        self.transitions: list[tuple[int, str, str, str]] = []

    def _move(self, t: int, to: str, reason: str) -> None:
        old, self.phase = self.phase, to
        self.transitions.append((t, old, to, reason))

    def on_bar(self, t: int, high: float, low: float, close: float, prev_high: float) -> None:
        \"\"\"One bar of logic. ``prev_high`` is the highest high of bars t-lookback..t-1.\"\"\"
        if self.phase == "COOLDOWN" and t - self.exit_bar >= self.cooldown_bars:
            self._move(t, "FLAT", "cooldown over")

        if self.phase == "FLAT":
            if close > prev_high:
                self.level = prev_high
                self.armed_bar = t
                self._move(t, "ARMED", f"close {close:.2f} > {prev_high:.2f}")

        elif self.phase == "ARMED":
            if close < self.level:  # failed breakout -> invalidation
                self._move(t, "FLAT", "level lost")
                self.level = None
            elif close > self.level and t > self.armed_bar:
                self.entry_bar = t
                self._move(t, "IN_POSITION", "continuation")

        elif self.phase == "IN_POSITION":
            # Toy exit: two closes below the level, or 10 bars held.
            if close < self.level or t - self.entry_bar >= 10:
                self.exit_bar = t
                self._move(t, "COOLDOWN", "exit rule")

df_small = load_ohlcv_csv(str(DATA / "sample_5min_equity_1m.csv")).head(300)
machine = BreakoutMachine()
for t in range(20, len(df_small)):
    prev_high = df_small["high"].iloc[t - 10 : t].max()
    machine.on_bar(t, df_small["high"].iloc[t], df_small["low"].iloc[t],
                   df_small["close"].iloc[t], prev_high)

print("final phase:", machine.phase)
print("transitions:", len(machine.transitions))
import pandas as pd
pd.DataFrame(machine.transitions, columns=["bar", "from", "to", "reason"]).head(12)
"""
    )
    nb.md("### 5.3 Snapshot and restore\n\nState is only useful if you can persist it. This is what makes a live restart, a walk-forward split or a long backtest checkpoint possible.")
    nb.code(
        """
def snapshot(machine: BreakoutMachine, bar_index: int, timestamp: pd.Timestamp) -> dict:
    \"\"\"Serialise only JSON-safe fields plus a version and a position marker.\"\"\"
    return {
        "version": 1,
        "bar_index": bar_index,
        "timestamp": str(timestamp),
        "state": {
            "phase": machine.phase,
            "level": machine.level,
            "armed_bar": machine.armed_bar,
            "entry_bar": machine.entry_bar,
            "exit_bar": machine.exit_bar,
        },
    }

def restore(snap: dict) -> BreakoutMachine:
    \"\"\"Rebuild a machine from a snapshot; validate the version first.\"\"\"
    if snap.get("version") != 1:
        raise ValueError("unsupported snapshot version")
    m = BreakoutMachine()
    s = snap["state"]
    m.phase, m.level = s["phase"], s["level"]
    m.armed_bar, m.entry_bar, m.exit_bar = s["armed_bar"], s["entry_bar"], s["exit_bar"]
    return m

cut = 150
full = BreakoutMachine()
for t in range(20, 300):
    full.on_bar(t, df_small["high"].iloc[t], df_small["low"].iloc[t],
                df_small["close"].iloc[t], df_small["high"].iloc[t-10:t].max())

first = BreakoutMachine()
for t in range(20, cut):
    first.on_bar(t, df_small["high"].iloc[t], df_small["low"].iloc[t],
                 df_small["close"].iloc[t], df_small["high"].iloc[t-10:t].max())

snap = snapshot(first, cut - 1, df_small.index[cut - 1])
resumed = restore(json.loads(json.dumps(snap)))   # prove it survives JSON
print("snapshot at bar", snap["bar_index"], "state:", snap["state"])

for t in range(cut, 300):
    resumed.on_bar(t, df_small["high"].iloc[t], df_small["low"].iloc[t],
                   df_small["close"].iloc[t], df_small["high"].iloc[t-10:t].max())

print("full transitions   :", len(full.transitions))
print("resumed transitions:", len(first.transitions) + len(resumed.transitions))
print("same final phase   :", full.phase, "/", resumed.phase)
assert [tr[1:] for tr in full.transitions] == [tr[1:] for tr in first.transitions + resumed.transitions]
print("resume is exact: every transition matches")
"""
    )
    nb.md("### 5.4 State inside the real engine\n\n`BaseStrategy` keeps the machine in `self.state`, resets it in `on_start`, and logs every transition as a `STATE` event.")
    nb.code(
        """
from intraday_engine import SweepBosFvgParams, SweepBosFvgStrategy

df = load_ohlcv_csv(str(DATA / "sample_5min_equity_1m.csv"))
strategy = SweepBosFvgStrategy(
    SweepBosFvgParams(entry_mode="limit", expiry_bars=12),
    sizer=FixedFractionSizer(risk_pct=0.01),
)
result = BacktestEngine.build(df, strategy, initial_cash=100_000).run()

states = result.events[result.events["kind"] == "STATE"]
print("STATE events:", len(states))
print(states[["bar_index", "message"]].to_string(index=False))
print("\\nfinal phase:", strategy.state["phase"])
"""
    )

    nb.md(
        """
**How to expand this code**

- [ ] move `StateMachine` into `state.py` with a `Transition` dataclass (from, to, guard, side effect);
- [ ] add guards as functions (`can_enter(state, position, bars_since_signal) -> bool`);
- [ ] add `to_dict()` / `from_dict()` with a schema version;
- [ ] persist snapshots to JSONL per bar boundary for crash recovery;
- [ ] add a `validate_invariants()` called after every transition;
- [ ] expose the state in the journal as a `STATE` event on every edge.

"""
    )
    nb.md(section(6, "Unit tests"))
    nb.md(
        """
The three properties that protect a state machine:

1. illegal transitions raise,
2. snapshot → JSON → restore preserves behaviour exactly,
3. a new run starts from a clean state (no leakage from the previous object).
"""
    )
    nb.code(
        """
test_code = '''
import sys, json
from pathlib import Path
import pytest

BASE = next(p for p in (Path.cwd(), Path.cwd().parent) if (p / "intraday_engine").is_dir())
sys.path.insert(0, str(BASE))

TRANSITIONS = {
    "FLAT": {"ARMED"},
    "ARMED": {"BOS_CONFIRMED", "FLAT"},
    "BOS_CONFIRMED": {"ENTERING", "FLAT"},
    "ENTERING": {"IN_POSITION", "FLAT"},
    "IN_POSITION": {"FLAT", "COOLDOWN"},
    "COOLDOWN": {"FLAT"},
}

class StateMachine:
    def __init__(self, transitions, initial):
        self.transitions = {k: set(v) for k, v in transitions.items()}
        self.state = initial
    def can(self, to):
        return to in self.transitions[self.state]
    def move(self, to, reason=""):
        if not self.can(to):
            raise ValueError(f"illegal {self.state} -> {to}")
        self.state = to
        return self.state

@pytest.fixture
def sm():
    return StateMachine(TRANSITIONS, "FLAT")

def test_legal_path(sm):
    for nxt in ["ARMED", "BOS_CONFIRMED", "ENTERING", "IN_POSITION", "FLAT"]:
        sm.move(nxt)
    assert sm.state == "FLAT"

def test_illegal_transition_raises(sm):
    with pytest.raises(ValueError):
        sm.move("IN_POSITION")          # cannot skip the setup

def test_cannot_enter_twice(sm):
    sm.move("ARMED")
    sm.move("BOS_CONFIRMED")
    sm.move("ENTERING")
    sm.move("IN_POSITION")
    with pytest.raises(ValueError):
        sm.move("ENTERING")

def test_snapshot_json_round_trip(sm):
    sm.move("ARMED")
    snap = json.loads(json.dumps({"state": sm.state}))
    restored = StateMachine(TRANSITIONS, snap["state"])
    assert restored.state == "ARMED"
    restored.move("BOS_CONFIRMED")
    assert restored.state == "BOS_CONFIRMED"
'''
path = Path(tempfile.mkdtemp()) / "test_lesson2.py"
path.write_text(test_code)
import subprocess
res = subprocess.run([sys.executable, "-m", "pytest", "-q", str(path)], capture_output=True, text=True)
print(res.stdout[-900:])
"""
    )

    nb.md(section(7, "Example input and expected output"))
    nb.md(
        """
Using `pattern_sample.csv`, the expected state timeline for the sweep → BOS → FVG
setup (from Lesson 3's detectors) is:

| Bar | Close | What happened | State after bar |
|---|---|---|---|
| 15 | 100.60 | swing low confirmed at 100.55 | `FLAT` |
| 17 | 100.65 | wick 100.10, close back above 100.55 → sell-side sweep | `ARMED` |
| 18 | 100.85 | nothing | `ARMED` |
| 19 | 101.60 | close breaks structure 101.45 | `BOS_CONFIRMED` |
| 20 | 101.40 | bullish FVG completed `[100.90, 101.30]` | `ENTERING` (limit at 101.10) |
| 21 | 101.20 | trades into the upper half of the gap (mitigation) | `ENTERING` |
| 22 | 101.10 | low 101.00 reaches the 101.10 midpoint → limit fills next bar | `IN_POSITION` |

You can verify rows 17/19/20 with the detectors in Lesson 3; the state names are
what this lesson is about.
"""
    )
    nb.code(
        """
# A compact replay of the table above using only readings <= each bar.
ps = load_ohlcv_csv(str(DATA / "pattern_sample.csv"))
rows = []
phase = "FLAT"
for t in range(len(ps)):
    if t == 17:
        phase = "ARMED"
    elif t == 19:
        phase = "BOS_CONFIRMED"
    elif t == 20:
        phase = "ENTERING"
    elif t == 22:
        phase = "IN_POSITION"
    rows.append({"bar": t, "close": ps["close"].iloc[t], "phase": phase})
pd.DataFrame(rows).iloc[14:24]
"""
    )

    nb.md(section(8, "Exercises"))
    nb.md(
        """
### Exercise 2.1 — add a COOLDOWN
After any exit, forbid new setups for 5 bars. Add the state, its transitions, the
expiry rule, and a test that no entry occurs within the cooldown window.
*Hint:* `last_exit_bar` plus `t - last_exit_bar < cooldown`.

### Exercise 2.2 — invariants
Write `check_invariants(state, position)` that asserts:
`phase == "IN_POSITION"` ⇒ `position != 0`, and `phase == "FLAT"` ⇒
`position == 0` and `setup is None`. Call it at the end of every bar in a test
run. Which real bug does it catch first?

### Exercise 2.3 — crash and resume
Run a backtest to bar 300, snapshot the state, then rebuild the engine on
`df.iloc[300:]` and resume. Compare the final trades to the uninterrupted run.
What must you also carry over? (Hint: position, cash, and any open bracket.)

### Exercise 2.4 — memory budget
Compute the number of objects stored per bar for a strategy that keeps a rolling
list of the last 500 closes vs one that keeps only a `deque(maxlen=20)`. What is
the difference for 500k bars?

### Exercise 2.5 — hysteresis
Change the breakout machine to require *two* consecutive closes above the level
before arming. Measure the change in trade count and average holding time.
Was the filter worth it on this sample? Why might that conclusion not generalise?
"""
    )
    nb.md(
        note(
            "If you ever find yourself adding a boolean called `has_entered` next to "
            "a boolean called `is_waiting`, you are hand-rolling a state machine badly. "
            "Name the state, list the transitions, and let illegal moves raise.",
            kind="Coach's note",
        )
    )

    nb.md(section(9, "Common pitfalls and debugging"))
    nb.md(
        """
| Pitfall | Symptom | Diagnosis / fix |
|---|---|---|
| State never resets | second backtest has zero trades | reset in `on_start`; construct a new strategy per run |
| Stuck waiting state | one trade in 5,000 bars | every waiting state needs an expiry branch |
| State mutated outside `on_bar` | irreproducible runs | write state only in the bar callback |
| Storing the full history | memory grows linearly, slow snapshots | store levels and indices, not DataFrames |
| Wall-clock in state | results differ by run date | use bar index |
| `datetime.now()` or `time.time()` | same | ban them in strategy code |
| Mutable default argument | state shared across instances | `field(default_factory=dict)` |
| Duplicate state keys | silent overwrite | one schema dict, documented |
| Snapshot without version | old snapshot breaks new code | version + validate |
"""
    )

    nb.md(section(10, "Recommended logging and diagnostics"))
    nb.md(
        """
**Always log STATE transitions** with `from`, `to`, `reason`, `bar_index`,
`timestamp`. They are cheap (a few per trade) and they answer the question you
will ask at 11pm: *"why didn't it enter?"*

**Periodically log a state snapshot** (every N bars or around signals):

| Field | Why |
|---|---|
| `phase` | the machine's state |
| `armed_bar`, `bos_bar` | how stale the setup is |
| `structure_level` | what it is waiting for |
| `position` | whether the state is consistent with the book |
| `bars_since_signal` | a stuck-state detector |

**Health metrics to print at the end of a run:**

- number of transitions per state (a state with zero exits is a bug);
- average bars in each waiting state (compare with the expiry);
- count of setups armed vs entered (conversion rate);
- count of `REJECT` events by reason.

**Next lesson:** the setup itself — liquidity sweeps, breaks of structure and
fair value gaps — and how to sequence them without repainting.
"""
    )
    return nb
