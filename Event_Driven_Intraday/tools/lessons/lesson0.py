"""Notebook 00 — module overview and setup."""

from __future__ import annotations

from .common import Notebook, header, note

FILENAME = "00_module_overview.ipynb"
TITLE = "Module overview"


def build() -> Notebook:
    """Return the overview notebook."""
    nb = Notebook(TITLE)
    nb.md(
        header(
            0,
            "Event-driven intraday trading in Python",
            "Five lessons, one engine, zero look-ahead. Start here, then open Lesson 1.",
        )
    )
    nb.md(
        """
## What you are about to build

By the end of Lesson 5 you will have a backtester you can explain line by line:
a bar loop that cannot see the future, a strategy with explicit state, a
conservative execution model with fees and slippage, honest portfolio
accounting, and a journal that answers *"why did it do that at 14:05?"*.

The five lessons are cumulative:

| Lesson | Question it answers | Artefact you write |
|---|---|---|
| 1 | How do I walk bars without peeking? | a safe bar loop + `DataHandler` |
| 2 | What does my strategy remember? | a state machine + state snapshots |
| 3 | How do I describe a multi-stage setup? | sweep / BOS / FVG detectors |
| 4 | What does a trade really cost? | sizing + bracket execution |
| 5 | How do I wire it all together? | the reusable engine |

"""
    )
    nb.md(
        note(
            "Resist the urge to jump to Lesson 5 and run a strategy. The people who "
            "lose money with backtests are almost never beaten by the market first — "
            "they are beaten by their own off-by-one errors. Lessons 1–4 exist to make "
            "those errors impossible to hide.",
            kind="Coach's note",
        )
    )
    nb.md(
        """
## The five rules of this module

1. **UTC everywhere.** A `DatetimeIndex`, tz-aware, ascending, unique.
2. **When processing bar `t`, read only data with index ≤ `t`.**
3. **An order created at `t` cannot fill at `t`.** Market orders fill at the next open.
4. **Costs are explicit and configurable**, never an afterthought.
5. **Ambiguity resolves against you** (stop before target inside one bar).

Rule 2 is enforced by code, not discipline: the data handler raises
`LookAheadError` if a strategy reaches past the cursor, and the tests prove it.

"""
    )
    nb.setup()
    nb.md(
        """
### Environment check

The cell above should print the module root, the package versions and the CSV
files. If it fails, run from the module folder (`Event_Driven_Intraday/`) or
install the requirements:

```bash
pip install -r requirements.txt
```

The entire module runs offline. There are no API keys, no downloads, no hidden
state. The three CSVs in `data/` are deterministic and committed.
"""
    )
    nb.code(
        """
from pathlib import Path
import pandas as pd

for name in ["pattern_sample.csv", "sample_5min_equity_1m.csv", "sample_1min_crypto_3d.csv"]:
    df = load_ohlcv_csv(str(DATA / name))
    print(f"{name:30s} {len(df):>6,d} bars  {df.index[0]}  ->  {df.index[-1]}  tz={df.index.tz}")
    print(" " * 30, "columns:", list(df.columns), "| monotonic:", df.index.is_monotonic_increasing)
"""
    )
    nb.md(
        """
## How the lessons are structured

Each lesson has the same ten sections, in this order:

1. Learning objectives (testable)
2. Key concepts and definitions
3. Step-by-step walkthrough
4. Data and API conventions
5. Minimal runnable code
6. Unit tests
7. Example input and expected output
8. Exercises
9. Common pitfalls and debugging
10. Logging and diagnostics

Sections 5–7 are executable: run them, change things, break them. Sections 8–10
are where the learning actually happens. Write your answers in a scratch
notebook; do not just read the exercises.

## What "practically" means here

Every example uses a real convention you will meet in production:

- bar-open timestamps (not close-stamped bars),
- session filtering for equities (and its absence for crypto),
- warm-up periods,
- orders that fill on the next bar,
- fees in basis points with a minimum,
- slippage that hurts you,
- stops that gap,
- a portfolio that marks to market every bar.

## Data you will use

| File | Frequency | Session | Bars | Use |
|---|---|---|---|---|
| `pattern_sample.csv` | 5 min | 14:00–15:55 UTC | 24 | hand-planted FVG, sweep, BOS — exact expected rows |
| `sample_5min_equity_1m.csv` | 5 min | 13:30–20:00 UTC | 2,000 | ORB, session logic, realistic noise |
| `sample_1min_crypto_3d.csv` | 1 min | 24/7 | 4,320 | 24/7 behaviour, more bars, smaller moves |

Regenerate them any time:

```bash
python tools/make_sample_data.py      # fixed seeds, byte-identical output
```

"""
    )
    nb.md(
        """
## Self-assessment before you start

You are ready if you can answer these without running code:

| # | Question | Answer |
|---|---|---|
| 1 | In a bar stamped 14:05 with 5-min bars, when is the bar complete? | at 14:10 |
| 2 | What does `df["close"].shift(1).iloc[t]` contain? | the close of bar `t-1` |
| 3 | Why is `df["close"].iloc[-1]` dangerous inside a loop? | it is always the *last* row of the frame, i.e. the future |
| 4 | If a bar's low pierces your stop and its high pierces your target, which filled first? | unknowable from OHLC — assume the stop |
| 5 | What is 1 basis point on a \\$50,000 trade? | \\$5 |

If any answer surprised you, that is exactly why the lesson exists.

## Reproducibility note

Randomness (synthetic data, microbar paths in exercises) goes through
`numpy.random.default_rng(seed)`. Nothing in the engine reads the clock, the
environment or the network. Running a notebook twice produces identical numbers.

## Ready?

Open `01_bars_and_indexing.ipynb`. Keep a scratch cell at the bottom of each
notebook for your own experiments — and keep your mistakes; they are the best
documentation you will ever write.
"""
    )
    return nb
