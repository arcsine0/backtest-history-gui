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
    optimization_goal: str = ""
    parameters: list[StrategyParameter] = Field(default_factory=list)
    vibe_payload: dict[str, Any] = Field(default_factory=dict)
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
    optimization_history: list[dict[str, Any]] = Field(default_factory=list)


class StrategyFileRequest(BaseModel):
    path: str


class RecycleStrategyFileRequest(BaseModel):
    original_path: str
    recycle_path: str


class RecycledStrategyFile(BaseModel):
    original_path: str
    recycle_path: str
    previous_path: str | None = None


class AutoOptimizeRequest(BaseModel):
    strategy: StrategySetup
    metrics: dict[str, Any]
    goal: str = ""


class RedoRequest(AutoOptimizeRequest):
    run_type: str
    redo_source: str


class AutoWorkflowRequest(BaseModel):
    strategy: StrategySetup
    baseline: StoredBacktest | None = None
    prompt_limit: int = Field(default=5, ge=1, le=50)
    target_metrics: list[str] = Field(default_factory=list)
    start_path: str = ""
    engine: str = "vibe"
    ohlcv_path: str = ""


class AutoTrial(BaseModel):
    number: int
    status: str
    score: float | None = None
    parameters: list[StrategyParameter] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    snapshot_path: str = ""
    backtest_id: int | None = None


class AutoWorkflow(BaseModel):
    id: str
    name: str
    path: str
    status: str
    prompt_limit: int
    target_metrics: list[str] = Field(default_factory=list)
    completed_trials: int = 0
    stop_requested: bool = False
    best_trial: AutoTrial | None = None
    best_backtest: StoredBacktest | None = None
    trials: list[AutoTrial] = Field(default_factory=list)


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
