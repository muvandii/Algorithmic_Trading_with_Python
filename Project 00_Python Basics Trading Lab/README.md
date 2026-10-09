# Project 00 · Python Basics Trading Lab

A guided practice project for **Lecture 00 – Introduction to Python** in *Algorithmic Trading with Python*.

You build a small backtester for a **moving-average crossover** strategy, one step at a time. Each step practices a Lecture 00 topic: variables, strings, lists, dictionaries, functions, classes, exceptions, modules, NumPy, file I/O, and matplotlib.

> **Simulated data.** AAA, BBB, and CCC are fictional tickers. The prices come from a random generator (`data/generate_prices.py`). They are **not real market data**, and nothing here is **investment advice**.

## Files

| Path | What it is |
|---|---|
| `Project 00_Python Basics Trading Lab.ipynb` | **Start here.** The student notebook. Replace each `...` with your code, then run the checks. |
| `data/prices.csv` | 252 simulated trading days (2025-01-02 to 2025-12-19) for AAA, BBB, and CCC. One value is blank on purpose. |
| `data/generate_prices.py` | Creates `prices.csv`. Fixed seed, so the same file is produced every time. |
| `solutions/Project 00 - Solutions.ipynb` | The answer key, already run. Open it only after you have tried the tasks. The folder can be deleted without affecting the student notebook. |

## How to run

1. Install Python 3 (tested with Python 3.11, NumPy 2.4, and matplotlib 3.11), plus the packages below. Use JupyterLab, Jupyter Notebook, or VS Code with the Jupyter extension.

   ```bash
   pip install numpy matplotlib notebook
   ```

2. Open the project folder in Jupyter, then open `Project 00_Python Basics Trading Lab.ipynb`. Open the notebook from the project folder, because it reads `data/prices.csv` by a relative path.
3. Run the cells from top to bottom. For each task:
   - Fill in the `...` placeholders.
   - Run the **Check** cell. A passing check prints ✅. A failing check stops with an error message that says what to look at.
   - Open the 💡 hints when you are stuck.
4. When you finish, choose **Kernel → Restart & Run All**. Every cell should run without errors.

Some cells are intentionally incomplete. Errors in a cell you have not finished are expected.

### What the notebook creates

- `trading_tools.py` in the project folder. Task 11.2 writes this module with `%%writefile`, the same way Lecture 00 wrote `mymodule.py`.
- `output/` with the saved price array, the equity-curve CSV, and two charts.

Both are generated when you run the notebook. `output/` is listed in `.gitignore`. `trading_tools.py` is not, because it is your own code.

### Expected results (for checking your work)

With the default settings (short window 10, long window 30, fee 1.00, starting cash 10,000):

| Ticker | Final value | Strategy return | Buy & hold | Trades |
|---|---|---|---|---|
| AAA | 9,594.00 | −4.06% | −4.35% | 9 |
| BBB | 10,144.74 | +1.45% | −45.56% | 6 |
| CCC | 10,944.68 | +9.45% | −2.70% | 8 |

## Course alignment

| Syllabus section (course README) | Where this project practices it |
|---|---|
| 2. Python Programming for Algorithmic Trading | Parts 0–15: core Python, NumPy, and plotting |
| 3. Data Handling and Preparation | Parts 3, 13, 14: loading CSV data, handling missing values, saving and reloading arrays |
| 4. Trend and Technical-Analysis Strategies | Parts 6, 7, 16: moving averages and crossover signals |
| 5. Strategy Testing and Evaluation | Parts 9, 10, 16: backtesting, object-oriented design, performance metrics, parameter sweeps |

### Learning objectives

By the end of the project you should be able to:

1. Use variables, the basic types, operators, and type conversion correctly (Parts 1–2).
2. Work with strings, lists, tuples, and dictionaries, and format output (Parts 3–5).
3. Write conditional logic, loops, list comprehensions, and functions with docstrings, default arguments, and `lambda` (Parts 6–8).
4. Model an account with a class and reject invalid orders with exceptions (Parts 9–10).
5. Write a module, import it, and use the standard library (Part 11).
6. Create, index, and reshape NumPy arrays, and use masks, axes, and vectorized calculations (Parts 12, 14).
7. Load and clean CSV data, and save and reload arrays (Part 13).
8. Plot data with the object-oriented matplotlib API (Part 15).
9. Backtest a rule-based strategy without look-ahead bias, compare it with buy and hold, and explain why one simulated year is not enough evidence (Part 16).

### Scope

- **Included:** the Lecture 00 topics listed in the notebook's roadmap table. The project uses only NumPy and matplotlib, and the only file input is a CSV file.
- **Mentioned only:** SciPy (imported in Lecture 00, not used here). pandas, `yfinance`, `backtrader`, and broker APIs are used in later lectures and are not needed here.
- **Next step:** Lecture 01 (Data Handling) loads real prices with pandas. Stretch goal 6 in Part 17 points there.

## Regenerating the data

```bash
python data/generate_prices.py
```

This rewrites `data/prices.csv`. The output is identical on every run.

## Git notes

`.gitignore` ignores `output/`, `__pycache__/`, `.ipynb_checkpoints/`, and `solutions/trading_tools.py`.
