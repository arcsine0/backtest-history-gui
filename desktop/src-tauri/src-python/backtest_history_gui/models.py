"""Local contracts for the Freqtrade strategy studio."""

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
    source: str = ""
    workspace_path: str = DEFAULT_WORKSPACE
    template_id: str
    parameters: list[StrategyParameter] = Field(default_factory=list)
    freqtrade_payload: dict[str, Any] = Field(default_factory=dict)
    strategy_file: str | None = None


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


class FreqtradeTemplateRequest(BaseModel):
    name: str
    template_id: str
    workspace_path: str = DEFAULT_WORKSPACE
    entry_id: str = ""
    exit_id: str = ""


class FreqtradeExportRequest(StrategyFileRequest):
    destination: str


class FreqtradeBacktestRequest(BaseModel):
    strategy: StrategySetup
    config_path: str = ""
    exchange: str
    trading_mode: str = "futures"
    pairs: str
    timeframes: str
    timerange: str = ""
    hyperopt_epochs: int = Field(default=0, ge=0, le=10000)


class ValidationSlice(BaseModel):
    label: str
    timerange: str
    backtest: StoredBacktest


class ValidationRun(BaseModel):
    training: ValidationSlice
    tests: list[ValidationSlice]
    stability_score: float
    mean_return: float
    return_stddev: float
    coverage: str
    output: str
