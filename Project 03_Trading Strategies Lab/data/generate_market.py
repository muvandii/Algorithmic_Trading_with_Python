"""
Generates simulated multi-regime OHLCV market data for Project 03.
Reproducible with fixed random seed (42).
"""
import os
import numpy as np
import pandas as pd

def generate_market_data(output_path="data/simulated_market.csv"):
    np.random.seed(42)
    dates = pd.date_range("2023-01-02", periods=500, freq="B")

    # Regime 1: Bullish Trend (200 days)
    r1 = np.random.normal(loc=0.0012, scale=0.011, size=200)
    # Regime 2: Sideways Mean-Reverting Chop (150 days)
    r2 = np.random.normal(loc=0.0000, scale=0.014, size=150)
    # Regime 3: Volatile Trend (150 days)
    r3 = np.random.normal(loc=0.0007, scale=0.020, size=150)

    shocks = np.concatenate([r1, r2, r3])
    close_prices = 100.0 * np.cumprod(1 + shocks)

    df = pd.DataFrame(index=dates)
    df.index.name = "Date"
    df["Close"] = np.round(close_prices, 2)
    df["High"] = np.round(df["Close"] * (1 + np.abs(np.random.normal(0, 0.006, len(df)))), 2)
    df["Low"] = np.round(df["Close"] * (1 - np.abs(np.random.normal(0, 0.006, len(df)))), 2)
    df["Open"] = np.round(df["Close"].shift(1).fillna(df["Close"].iloc[0]), 2)
    df["High"] = np.maximum(df["High"], np.maximum(df["Open"], df["Close"]))
    df["Low"] = np.minimum(df["Low"], np.minimum(df["Open"], df["Close"]))
    df["Volume"] = np.random.randint(500000, 2500000, size=len(df))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path)
    print(f"Saved {len(df)} rows of simulated market data to: {output_path}")

if __name__ == "__main__":
    generate_market_data()
