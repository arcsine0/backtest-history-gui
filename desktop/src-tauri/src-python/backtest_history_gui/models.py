"""Typed boundaries between GUI, market-data, backtesting, and storage code."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketDataRequest:
    """TODO: Add exchange-specific options (market type, limit, retries) here."""

    exchange_id: str
    symbol: str
    timeframe: str
    since_ms: int | None = None
    until_ms: int | None = None


@dataclass(frozen=True)
class BacktestRequest:
    """TODO: Add cash, commission, and strategy parameters as the GUI needs them."""

    market_data: MarketDataRequest
    strategy_name: str
    cash: float = 10_000
    commission: float = 0.0


@dataclass(frozen=True)
class BacktestResult:
    """TODO: Replace flexible dictionaries with your final result schema."""

    request: BacktestRequest
    statistics: dict[str, Any]
    trades: list[dict[str, Any]]
