"""Local contracts for the Vibe-Trading GUI."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

PROJECT_ROOT = str(Path(__file__).resolve().parents[4])
DEFAULT_WORKSPACE = str(Path(PROJECT_ROOT) / "data")


class StrategyParameter(BaseModel):
    name: str
    value: str = ""
    notes: str = ""
    enabled: bool = True
    locked: bool = False


class StrategySetup(BaseModel):
    id: int | None = None
    name: str
    source: str
    workspace_path: str = DEFAULT_WORKSPACE
    parameters: list[StrategyParameter] = Field(default_factory=list)
    strategy_file: str | None = None


class ImportedBacktest(BaseModel):
    name: str
    payload: dict[str, Any]


class StoredBacktest(BaseModel):
    id: int
    name: str
    imported_at: str
    metrics: dict[str, Any]
    trades: list[dict[str, Any]]
    equity_curve: list[float]
    equity_timestamps: list[str] = Field(default_factory=list)


class StrategyRun(BaseModel):
    strategy: StrategySetup
    backtest: StoredBacktest | None = None
    output: str
    error: str | None = None


class StrategyFileRequest(BaseModel):
    path: str


class AutoOptimizeRequest(BaseModel):
    strategy: StrategySetup
    metrics: dict[str, Any]


# These contracts keep the existing Backtesting.py and CCXT seams usable while
# Vibe-Trading remains an optional, separately installed companion.
class MarketDataRequest(BaseModel):
    exchange: str
    symbol: str
    timeframe: str


class BacktestRequest(BaseModel):
    market_data: MarketDataRequest
    strategy_name: str


class LocalBacktestResult(BaseModel):
    request: BacktestRequest
    metrics: dict[str, Any]
    trades: list[dict[str, Any]] = Field(default_factory=list)
