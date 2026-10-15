# Project 03 · Quantitative Trading Strategies Lab

A comprehensive, hands-on guided project for **Lecture 03 – Trading Strategies & Paradigms** in *Algorithmic Trading with Python*.

In this project, you build, test, and evaluate your own quantitative trading strategies from scratch using Python and `pandas`. Instead of merely running pre-built library commands, you translate plain-English trading hypotheses into mathematical rules, generate signals, prevent the critical pitfall of **lookahead bias**, account for **transaction fees & slippage**, and measure **risk-adjusted performance** (Sharpe Ratio, CAGR, and Maximum Drawdown).

---

## Files

| Path | Description |
|---|---|
| `Project 03_Trading Strategies Lab.ipynb` | **Start here.** The student exercise notebook with step-by-step guidance, concept notes, `# TODO` blocks, and automated `assert` checks. |
| `data/simulated_market.csv` | 500 trading days of simulated OHLCV data featuring three realistic regimes (uptrend, choppy sideways, volatile trend). |
| `data/generate_market.py` | Generator script creating the reproducible market dataset (`seed=42`). |
| `solutions/Project 03 - Solutions.ipynb` | Complete answer key and reference implementations with all charts and scorecards rendered. |

*(A copy of the student lab is also available in the repository root as `Lecture 03_Trading_Strategies_Lab.ipynb` for quick access.)*

---

## What You Build & Implement

### 1. Signal Architecture & Lookahead Prevention (Part 1)
- Demystifying the difference between a **Signal** ($S_t$) calculated at market close and an actionable **Position** ($P_t$) held overnight.
- Implementing the non-negotiable 1-bar execution delay: `df['Position'] = df['Signal'].shift(1)`.

### 2. Four Core Strategy Paradigms (Parts 2–5)
- **Donchian Breakout Strategy (Trend Following):** 20-day high/low channel breakouts inspired by the Turtle Traders.
- **Buffered Dual-EMA Crossover (Trend + Noise Filter):** 12/26 Exponential Moving Averages with a $+0.5\%$ threshold buffer to eliminate whipsaws.
- **Bollinger-Style Z-Score (Statistical Mean Reversion):** Standardized rolling deviations with asymmetric entries ($Z < -1.5$) and mean exits ($Z \ge 0.0$).
- **Pure-Pandas RSI (Momentum Oscillator):** Calculating Wilder's 14-period RSI from scratch without external dependencies, capturing momentum exhaustion.

### 3. Reusable Frictional Backtesting Engine (Part 6)
- Vectorized return modeling: $R_{net, t} = Position_t \times R_{asset, t} - \text{Fee}_t$.
- Modeling realistic transaction costs (10 basis points per trade change) and tracking portfolio equity curves.

### 4. Quantitative Performance Scorecard (Part 7)
- Vectorized metrics: **Total Return**, **CAGR (Compound Annual Growth Rate)**, **Annualized Volatility**, **Sharpe Ratio**, and **Maximum Drawdown (MDD)** using `.cummax()`.

### 5. Multi-Strategy Showdown & Benchmark (Part 8)
- Running all four strategies against a Buy-and-Hold benchmark across 500 trading days.
- Comparing risk vs. return across different market regimes (trending vs. chopping).

### 6. Capstone Challenge (Part 9)
- Designing and implementing your own proprietary hybrid strategy (e.g., Trend-Filtered RSI Dip Buying) from hypothesis to performance evaluation.

---

## How to Run

1. Open the project folder in JupyterLab, VS Code, or Jupyter Notebook:
   ```bash
   jupyter notebook "Project 03_Trading Strategies Lab.ipynb"
   ```
2. Run each cell sequentially. Replace each `...` placeholder in `# TODO` cells with your code.
3. Run the **Check** cells to verify your implementation. Passing checks display a confirmation message.

---

## Expected Benchmark Results (Net of 10 bps Fees)

| Strategy | Total Return (%) | CAGR (%) | Ann. Volatility (%) | Sharpe Ratio | Max Drawdown (%) |
|---|---|---|---|---|---|
| **Buy & Hold (Benchmark)** | +45.43% | +20.91% | 22.84% | 0.92 | −25.08% |
| **Donchian Breakout** | +11.90% | +5.83% | 19.07% | 0.31 | −19.86% |
| **Buffered Dual-EMA** | +11.45% | +5.62% | 18.06% | 0.31 | −27.14% |
| **Z-Score Mean Reversion** | +9.13% | +4.51% | 11.23% | 0.40 | −11.81% |
| **RSI Pullback** | +19.11% | +9.19% | 12.35% | 0.74 | −11.64% |
| **Hybrid (Capstone)** | +27.24% | +12.87% | 14.86% | 0.87 | −15.34% |

*Notice how the mean reversion and momentum pullback strategies achieve drastically lower drawdowns (~11-15%) compared to Buy & Hold (-25.08%) while avoiding the whipsaws of unconstrained trend following during sideways markets.*
