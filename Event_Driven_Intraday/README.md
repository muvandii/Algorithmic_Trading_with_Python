# Event-Driven Intraday Trading — a five-lesson, hands-on module

**Build an intraday strategy the way a desk actually does it:** one bar at a time,
with explicit state, explicit costs, and a hard wall between "what happened" and
"what I wish had happened".

This module is a companion to the main course notebooks. It is written for
someone who can write Python and read a pandas DataFrame, but has never built a
backtester that they *trust*. Everything here is runnable offline with pandas and
numpy only — no API keys, no data subscriptions.

> **Coach's note.** You will not learn this by reading. Each lesson ends with
> exercises; do them in a scratch notebook *before* opening the next lesson.
> The goal is not a profitable strategy (nobody can promise that). The goal is a
> research process where you can tell the difference between an edge and a bug.

---

## 1. What you get

```
Event_Driven_Intraday/
├── notebooks/                     five lessons + overview + capstone
│   ├── 00_module_overview.ipynb
│   ├── 01_bars_and_indexing.ipynb
│   ├── 02_state_and_memory.ipynb
│   ├── 03_events_and_multi_stage_entries.ipynb
│   ├── 04_execution_and_risk.ipynb
│   ├── 05_reusable_backtest_engine.ipynb
│   └── 06_capstone_write_your_own.ipynb
├── intraday_engine/               the library the lessons build up to
│   ├── core.py                    Bar, Order, Fill, TradeRecord, Event, Side
│   ├── data.py                    DataHandler + look-ahead guard + loaders
│   ├── journal.py                 EventLogger (structured journal)
│   ├── portfolio.py               cash/position accounting, equity curve
│   ├── execution.py               fees, slippage, brackets, intrabar rules
│   ├── sizing.py                  fixed-fraction + ATR sizing
│   ├── structure.py               swings, BOS, sweeps, fair value gaps
│   ├── strategies.py              demo: sweep → BOS → FVG pullback
│   ├── review.py                  thin, swappable detector façade for strategies
│   ├── strategy.py                BaseStrategy (state machine + hooks)
│   ├── engine.py                  BacktestEngine + BacktestResult
│   └── synthetic.py               seeded data + a hand-planted pattern sample
├── strategies/template_strategy.py  copy me to write your own (ORB example)
├── data/                          small committed CSVs (reproducible)
├── tools/make_sample_data.py      regenerate the CSVs
├── tests/test_engine.py           23 tests encoding the lessons' promises
├── Makefile                        make test / data / notebooks
├── requirements.txt
└── README.md
```

The notebooks teach the ideas by building small pieces; the package is the same
code, assembled and tested. Read both: notebooks for *why*, package for *how*.

---

## 2. Quickstart

```bash
cd Event_Driven_Intraday
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest -q                                             # 23 passed
jupyter lab notebooks/
# or, with make:
make test && make notebooks
```

Run the demo strategy and the ORB template from the command line:

```bash
python strategies/template_strategy.py
python -c "from intraday_engine import *; \
df = load_ohlcv_csv('data/sample_5min_equity_1m.csv'); \
print(BacktestEngine.build(df, SweepBosFvgStrategy(sizer=FixedFractionSizer()), 100000).run().summary())"
```

**Defaults used throughout (industry-typical for retail/small fund research):**

| Setting | Default | Why |
|---|---|---|
| Instrument | liquid US equity, 5-min bars | spreads are small, sessions matter |
| Session | 13:30–20:00 UTC (09:30–16:00 NY) | regular hours only |
| Timezone | UTC everywhere (`DatetimeIndex`, tz-aware) | no DST bugs |
| Account | \$100,000 | round number, readable PnL |
| Risk per trade | 1% of equity | standard survival budget |
| ATR period | 14 (Wilder) | classic, well understood |
| Fees | 2 bps taker, 0 bps maker, \$0 min | equities/futures-ish; make it yours |
| Slippage | 1 bp market, 3 bp stop | conservative retail estimate |
| Intrabar | conservative: stop before target | never flatter yourself |
| Randomness | seeded (`numpy.random.default_rng`) | reproducibility |

Change them in `ExecutionModel(...)`, `FixedFractionSizer(...)`, `AtrSizer(...)`.

---

## 3. The five lessons

| # | Notebook | You will be able to… | Core code |
|---|---|---|---|
| 1 | `01_bars_and_indexing` | loop bar-by-bar, index t / t−1 / t+1 correctly, and prove you never read the future | `DataHandler`, cursor, `LookAheadError` |
| 2 | `02_state_and_memory` | design a strategy state machine, store decisions, snapshot/resume state | `BaseStrategy`, `Context.state` |
| 3 | `03_events_and_multi_stage_entries` | detect sweeps, breaks of structure and fair value gaps; sequence multi-stage entries; log events | `structure.py`, `strategies.py` |
| 4 | `04_execution_and_risk` | size with fixed-fraction and ATR, bracket SL/TP, charge fees/slippage, resolve intrabar ambiguity | `sizing.py`, `execution.py`, `portfolio.py` |
| 5 | `05_reusable_backtest_engine` | separate data/strategy/execution/portfolio/logging, run a full backtest, audit for look-ahead | `engine.py` |

Every lesson follows the same ten sections:

1. Learning objectives
2. Key concepts and definitions (glossary)
3. Step-by-step walkthrough
4. Data and API conventions
5. Minimal runnable code
6. Unit tests (pytest)
7. Example input and expected output
8. Exercises
9. Common pitfalls and debugging
10. Logging and diagnostics

---

## 4. The one rule that matters

> **When handling bar `t`, a strategy may only read data with index ≤ `t`.**
> Everything else is look-ahead.

The engine enforces it in three places:

1. `DataHandler.set_cursor(t)` before the strategy is called; reads above the
   cursor raise `LookAheadError` (tested).
2. Orders created at `t` are not eligible until `t+1`; market orders fill at the
   **next** open, never the signal bar's close (tested).
3. Bracket exits are evaluated intrabar with a conservative tie-break (tested).

`t+1` references are allowed only in *descriptive* code — plots, hindsight
labels, "what happened next" diagnostics — never in a decision path.

---

## 5. Write your own strategy (the point of all this)

1. `cp strategies/template_strategy.py strategies/my_strategy.py`
2. Rename the class and its `Params` dataclass.
3. Implement `generate(ctx)` and, if needed, `manage(ctx)`.
4. Set `warmup` (bars needed before any signal).
5. Choose a sizer and a mode:

```python
strategy = MyStrategy(
    sizer=FixedFractionSizer(risk_pct=0.01, max_leverage=1.0),
    sizing_mode="fixed",           # or "atr" for volatility sizing
)
engine = BacktestEngine.build(df, strategy, initial_cash=100_000,
                              model=ExecutionModel(fee_bps=2, slippage_bps=1))
result = engine.run()
print(result.summary())
```

Rules of thumb for a first strategy:

- One instrument, one timeframe, one session.
- Entry rule must be expressible in one sentence; exits must be pre-defined.
- If it needs more than ~5 parameters, you are fitting noise.
- Compare against "no fees", "double fees", and "optimistic intrabar" before
  celebrating.

---

## 6. Integration checklist (wire the five lessons together)

**Files to create (in this order):**

| Order | File | Depends on | Purpose |
|---|---|---|---|
| 1 | `data.py` | — | validated OHLCV + cursor guard |
| 2 | `core.py` | — | Bar/Order/Fill/Trade/Event vocabulary |
| 3 | `journal.py` | `core.py` | structured event log |
| 4 | `portfolio.py` | `core.py` | cash, position, equity, trades |
| 5 | `execution.py` | `core.py`, `data.py`, `portfolio.py` | fills, costs, brackets |
| 6 | `sizing.py` | — | risk → quantity |
| 7 | `strategy.py` | `core.py`, `data.py` | hooks + state machine |
| 8 | `structure.py` | — | sweep/BOS/FVG detectors |
| 9 | `engine.py` | all of the above | bar loop, wiring, results |
| 10 | `my_strategy.py` | `strategy.py`, `sizing.py` | your edge |

**Order of operations per bar (do not reorder):**

1. advance cursor to `t`
2. build `Context(history ≤ t)`
3. call `strategy.on_bar` → queue orders
4. run execution: existing brackets first, then pending orders (only those
   submitted before `t`), then same-bar brackets for fresh entries
5. mark the portfolio at the close
6. append events, dispatch fill/reject callbacks

**Verification steps that prove the engine is honest:**

- [ ] `pytest -q` → all tests pass, especially
      `test_strategy_cannot_read_the_future_during_a_full_run` and
      `test_order_submitted_at_t_never_fills_within_t`.
- [ ] Deliberately cheat: make a strategy read `data.bar(t+1)`; confirm it raises.
- [ ] Run the same backtest twice; equity arrays must be identical.
- [ ] Compare `ambiguity="conservative"` vs `"optimistic"`; the gap is the value
      of your ignorance about intrabar paths — record it.
- [ ] Multiply fees and slippage by 2–3×; if the edge disappears, it was costs.
- [ ] Reconcile: `initial_cash + Σ net_pnl == equity` at the end (the engine
      flattens any open position at the final close, so nothing is left unrealised).
- [ ] Shift every signal one extra bar forward (a `delay=1` experiment). If the
      result collapses, the strategy depends on immediacy you may not get.
- [ ] Run on a second data source/period before believing anything.

---

## 7. Modelling choices and honest limitations

- **Intrabar ambiguity** is resolved conservatively (stop before target when both
  are inside one bar). Upgrade path: feed 1-min or tick data and simulate the
  path, or decompose each bar into micro-bars with a seeded bridge. The engine's
  `ExecutionEngine` interface is where you plug that in.
- **Fills**: market orders at next open with adverse slippage; limit orders only
  if touched, filled at the limit (no improvement). No queue-position modelling.
- **Costs**: percentage fees + minimum fee + bps slippage. No borrow, funding,
  taxes, market impact or partial fills.
- **Accounting**: one symbol per portfolio, fractional quantities allowed, no
  leverage unless `max_leverage > 1`. Equity is marked per bar.
- **Open positions at the end** are liquidated at the final close (with slippage)
  by default (`run(flatten_at_end=True)`), so the trade log is complete. Pass
  `flatten_at_end=False` if you are deliberately studying overnight carry.
- **Annualised Sharpe** from intraday bars with sparse trading is noisy; the
  notebooks show why daily aggregation is safer.
- **No survivorship-bias-free universe, no corporate actions.** This is a
  research engine, not an exchange simulator.

---

## 8. Reproducibility

- All randomness goes through `numpy.random.default_rng(seed)`.
- `data/*.csv` are generated by `tools/make_sample_data.py` with fixed seeds; the
  files are committed so results do not drift.
- The engine has no wall-clock, no environment, and no network dependency.
- Tests assert determinism (`test_full_run_is_deterministic`).
- Timestamps are UTC; sessions are filtered explicitly.

Same code + same CSVs + same Python/pandas/numpy ⇒ same equity curve.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `LookAheadError` | strategy read `bar(t+1)` or `window` past cursor | use `history`/`window_before`; wait for confirmation |
| `ValueError: tz-aware` | naive index from CSV | `pd.to_datetime(..., utc=True)` |
| No trades at all | warm-up too long, limits never touched, state stuck | check `events["kind"].value_counts()` and `REJECT` reasons |
| Equity flat while trades exist | fills not applied to cash / marks missing | verify `Portfolio.apply_fill` and per-bar `mark` |
| Absurd Sharpe | sparse trades + annualisation | aggregate to daily returns first |
| Results differ run to run | dict/set ordering, RNG unseeded, `datetime.now()` | seed, sort, remove clock reads |
| Exits at next-day open | exit order submitted after the last bar of the session | submit exits earlier; reject stale exits (engine does) |

---

## 10. Where to go next

- Add a second symbol and portfolio-level risk (correlation caps, gross exposure).
- Replace `DataHandler` with a websocket feed and reuse the same `Strategy`
  (paper trading).
- Add microbar simulation for intrabar paths.
- Walk-forward: split by date, fit parameters on the first half, trade the second.
- Track every experiment (params, data hash, metrics) — a research log is part
  of the strategy, not an afterthought.

*Built to be read, run, broken, and improved. Start with Lesson 1.*
