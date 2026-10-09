"""Create the simulated price file used by Project 00.

Run either of these from the project folder:

    python data/generate_prices.py

It always writes prices.csv next to this file. The random seed is fixed, so every
run writes the same prices.csv.
AAA, BBB and CCC are fictional tickers and the prices are simulated.
They are for practice only and do not represent real market data.
"""
import csv
import datetime as dt
import os

import numpy as np

SEED = 2025
N_DAYS = 252                      # trading days in the sample (weekdays only)
START_DATE = dt.date(2025, 1, 2)
TRADING_DAYS_PER_YEAR = 252

# ticker: (first price, annual drift, annual volatility)
STOCKS = {
    "AAA": (100.00, 0.08, 0.18),   # drift +8% a year, volatility 18% a year
    "BBB": (50.00, -0.05, 0.35),   # drift -5% a year, volatility 35% a year
    "CCC": (200.00, 0.15, 0.22),   # drift +15% a year, volatility 22% a year
}

# One blank cell, so students can practice finding and fixing missing values.
MISSING_CELL = ("BBB", 58)        # (ticker, row index counted from 0)


def trading_days(start, n):
    """Return the first n weekdays on or after `start`."""
    days = []
    day = start
    while len(days) < n:
        if day.weekday() < 5:     # Monday = 0 ... Friday = 4
            days.append(day)
        day += dt.timedelta(days=1)
    return days


def simulate_prices(first_price, drift, vol, n_days):
    """Geometric random walk: each day's log return is a random shock with the given drift and volatility."""
    step = 1.0 / TRADING_DAYS_PER_YEAR
    shocks = np.random.randn(n_days - 1)
    log_returns = (drift - 0.5 * vol ** 2) * step + vol * np.sqrt(step) * shocks
    path = first_price * np.exp(np.concatenate(([0.0], np.cumsum(log_returns))))
    return np.round(path, 2)


def main():
    np.random.seed(SEED)
    days = trading_days(START_DATE, N_DAYS)
    series = {name: simulate_prices(p0, mu, sigma, N_DAYS) for name, (p0, mu, sigma) in STOCKS.items()}

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prices.csv")
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["date"] + list(STOCKS))
        for i, day in enumerate(days):
            row = [day.isoformat()]
            for name in STOCKS:
                if (name, i) == MISSING_CELL:
                    row.append("")                  # empty cell = missing value
                else:
                    row.append("%.2f" % series[name][i])
            writer.writerow(row)
    print("Wrote %s (%d rows)" % (out_path, N_DAYS))


if __name__ == "__main__":
    main()
