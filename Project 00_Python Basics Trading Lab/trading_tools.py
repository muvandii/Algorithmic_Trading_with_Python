"""trading_tools.py: helper functions and the Portfolio class for Project 00."""
import math
import numpy as np

def daily_returns(prices):
    """Return the list of simple daily returns: prices[t] / prices[t - 1] - 1."""
    # TODO: paste your code from Task 8.1
    return [(prices[i] / prices[i - 1]) - 1 for i in range(1, len(prices))]


def total_return(start_value, end_value):
    """Return the decimal return from start_value to end_value (0.10 means +10%)."""
    # TODO: paste your code from Task 8.2
    return (end_value / start_value) - 1

def position_size(cash, price, fee=1.0):
    """Return how many whole shares you can buy with `cash` at `price`, after paying `fee`."""
    # TODO: paste your code from Task 8.3
    return (cash - fee) // price


def max_drawdown(values):
    """Return the worst fall from a previous peak, as a negative decimal (-0.25 means -25%)."""
    # TODO: paste your code from Task 8.4
    peak = 0
    mdd = 0
    for value in values:
        if value > peak:
            peak = value
        else:
            dd = value / peak - 1
            if dd < mdd:
                mdd = dd
    return mdd


def simple_moving_average(prices, window):
    """Return a list the same length as prices. Item i is the average of the last `window` prices, or NaN."""
    # TODO: paste your code from Task 8.5
    sma = []
    for i in range(len(prices)):
        if i < window -1:
            print("true")
            sma.append(float("nan"))
        else:
            s = prices[i - window + 1 : i + 1]
            sma.append(sum(s) / window)
    return sma


def annualized_volatility(daily_rets):
    """Return the annualized volatility of daily returns: sample standard deviation * sqrt(252)."""
    # TODO 11.2: write this function. Hint in the box above.
    return np.std(daily_rets, ddof=1) * math.sqrt(252)


# TODO 11.2: paste your finished Portfolio class (Parts 9 and 10) here, at the top level of the file.
class Portfolio:
    """A cash account that holds shares. Methods change the account; prices are passed in."""

    def __init__(self, starting_cash):
        self.cash = starting_cash       # money not yet invested
        self.holdings = {}              # ticker -> number of shares owned
        self.trade_log = []             # one (ticker, side, shares, price, fee) tuple per trade

    def __str__(self):
        # TODO 9.1: return text such as "Cash: 8986.50 | Holdings: {'AAA': 10}"
        #           Hint: "%.2f" % self.cash formats the cash with 2 decimals.
        return f"Cash: {self.cash:.2f} | Hodings: {self.holdings}"

    def total_value(self, prices):
        """Return cash plus the market value of every holding. `prices` maps ticker -> price."""
        # TODO 9.2: start from self.cash, then add shares * prices[ticker] for each holding.
        #           Loop over self.holdings.items().
        values = [prices[holding] * share for holding, share in self.holdings.items()]
        return self.cash + sum(values)

    def buy(self, ticker, price, shares, fee):
        """Buy `shares` of `ticker` at `price` and pay `fee`."""
        # Part 10 adds two checks here, before the account changes.
        # TODO 9.3: 1) subtract shares * price + fee from self.cash
        #           2) add shares to self.holdings (start from 0 if the ticker is new)
        #           3) append (ticker, "BUY", shares, price, fee) to self.trade_log
        if shares <= 0:
            raise ValueError("Shares must be greater than 0")
        if (shares * price + fee) > self.cash:
            raise ValueError("Total cost cannot exceed available cash")
        self.cash -= (shares * price + fee)
        if ticker in self.holdings.keys():
            self.holdings[ticker] += shares
        else:
            self.holdings[ticker] = shares
        self.trade_log.append((ticker, "BUY", shares, price, fee))

    def sell(self, ticker, price, shares, fee):
        """Sell `shares` of `ticker` at `price` and pay `fee`."""
        # TODO 10.2: write sell() (see Task 10.2)
        if shares <= 0:
          raise ValueError("Shares must be greater than 0")
        if shares > self.holdings[ticker]:
            raise ValueError("Cannot sell more than you own")
        self.cash += (shares * price - fee)
        self.holdings[ticker] -= shares
        if self.holdings[ticker] == 0:
            del self.holdings[ticker]
        self.trade_log.append((ticker, "SELL", shares, price, fee))
