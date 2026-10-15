# Data folder — real market data only

This folder is a **local cache**, not a dataset shipped with the lab.

- The notebook downloads daily OHLCV from **Yahoo Finance via `yfinance`** (SPY 2015-01-01–2024-12-31 primary; AAPL and KO/PEP later) and caches the cleaned result here, e.g. `spy_daily.csv`.
- Cached CSVs are **git-ignored** (`.gitignore`): Yahoo data is revised and split/dividend-adjusted retroactively, so a committed copy would silently go stale and could be mistaken for ground truth. Always record your download date in the notebook's Module 0 reflection.
- **No synthetic, seeded, simulated, or hand-written price file belongs here.** If a file in this folder did not come from a real market-data source, delete it and re-download.

## Fallback: loading a real CSV export instead of `yfinance`

Only if Yahoo Finance is genuinely unreachable: obtain a real daily export (e.g. from your broker, Nasdaq.com, or another reputable provider) and save it here with exactly this schema, then load it in Module 0 in place of the download and document the provider + export date:

```csv
Date,Open,High,Low,Close,Volume
2015-01-02,...
```

`Date` must parse to a DatetimeIndex; prices must be the provider's real historical values (note whether they are split/dividend adjusted — Module 0's price-convention discussion applies). The Module 0 validation and `CHECK 0` cell must pass unchanged.
