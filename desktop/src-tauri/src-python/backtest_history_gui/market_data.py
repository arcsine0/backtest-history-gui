"""CCXT market-data adapter."""

import pandas as pd

from .models import MarketDataRequest


async def fetch_ohlcv(request: MarketDataRequest) -> pd.DataFrame:
    """TODO: Create the CCXT exchange and normalize OHLCV for Backtesting.py.

    Backtesting.py expects a datetime index and Open, High, Low, Close, Volume
    columns. Decide here how pagination, rate limits, and local candle caching
    should work before wiring this function to a PyTauri command.
    """
    del request
    raise NotImplementedError("Implement CCXT OHLCV retrieval here.")
