"""Starter strategy for the future local Backtesting.py engine.

The uppercase class variables are the optimizer's parameter contract. Keep
strategy logic here; snapshots will only store values, never execute code.
"""

import numpy as np
import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover


def _vwap(close: np.ndarray, volume: np.ndarray, window: int) -> pd.Series:
    prices = pd.Series(close)
    volumes = pd.Series(volume).replace(0, np.nan)
    return (prices * volumes).rolling(window).sum() / volumes.rolling(window).sum()


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> pd.Series:
    previous_close = pd.Series(close).shift()
    true_range = pd.concat([pd.Series(high) - pd.Series(low), (pd.Series(high) - previous_close).abs(), (pd.Series(low) - previous_close).abs()], axis=1).max(axis=1)
    return true_range.rolling(period).mean()


class MainStrategy(Strategy):
    """VWAP entry with an ATR trailing stop; edit this to match your strategy."""

    VWAP_WINDOW = 20
    ATR_PERIOD = 14
    ATR_MULTIPLIER = 3.0

    def init(self) -> None:
        self.vwap = self.I(_vwap, self.data.Close, self.data.Volume, self.VWAP_WINDOW)
        self.atr = self.I(_atr, self.data.High, self.data.Low, self.data.Close, self.ATR_PERIOD)

    def next(self) -> None:
        if not np.isfinite(self.atr[-1]):
            return
        stop = self.data.Close[-1] - self.atr[-1] * self.ATR_MULTIPLIER
        if crossover(self.data.Close, self.vwap):
            self.position.close()
            self.buy(sl=stop)
        if self.position.is_long:
            for trade in self.trades:
                trade.sl = max(trade.sl or -np.inf, stop)
