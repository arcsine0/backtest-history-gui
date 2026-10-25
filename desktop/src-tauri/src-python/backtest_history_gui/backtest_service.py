"""Backtesting.py integration point."""

import pandas as pd
from backtesting import Strategy

from .models import BacktestRequest, LocalBacktestResult


def run_backtest(
    request: BacktestRequest,
    candles: pd.DataFrame,
    strategy_type: type[Strategy],
) -> LocalBacktestResult:
    """TODO: Construct Backtest, call run(), and map its output to LocalBacktestResult.

    Keep strategy classes in a dedicated module and pass their type here. This
    keeps UI input, candle retrieval, the backtesting engine, and persistence
    separate without committing to a strategy registry prematurely.
    """
    del request, candles, strategy_type
    raise NotImplementedError("Implement the Backtesting.py run here.")
