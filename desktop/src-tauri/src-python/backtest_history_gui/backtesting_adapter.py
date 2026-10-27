"""Adapt a saved single-symbol Vibe SignalEngine to Backtesting.py."""

import ast
import types
import warnings
from pathlib import Path

import pandas as pd
from backtesting import Backtest, Strategy
from backtesting.lib import FractionalBacktest

from .market_data import cached_ccxt_ohlcv, reference_ohlcv
from .models import StrategyParameter, StrategySetup
from .auto_workflow import _score


def optimize_saved_vibe(setup: StrategySetup, cache_root: Path, max_tries: int, baseline: dict | None = None, targets: list[str] | None = None, ohlcv_path: Path | None = None, references_root: Path | None = None) -> tuple[dict, list[StrategyParameter], dict]:
    payload = setup.vibe_payload
    if payload.get("format") != "vibe-signal-engine-v1":
        raise ValueError("This snapshot has no saved Vibe signal engine. Run it once through Vibe-Trading to create a convertible snapshot.")
    config, source = payload.get("config"), payload.get("signal_engine")
    if not isinstance(config, dict) or not isinstance(source, str):
        raise ValueError("The saved Vibe strategy payload is incomplete.")
    data = reference_ohlcv(ohlcv_path, references_root) if ohlcv_path and references_root else cached_ccxt_ohlcv(config, cache_root)
    values = {parameter.name: number for parameter in setup.parameters if (number := _number(parameter.value)) is not None and parameter.enabled and not parameter.locked}
    if not values:
        raise ValueError("Select an unlocked numeric parameter before running Backtesting.py optimization.")
    strategy = _adapter_class(source, config, values, data)
    # Crypto prices exceed a typical cash balance, so use Backtesting.py's
    # native fractional broker instead of rounding every BTC order to zero.
    backtest = FractionalBacktest(data, strategy, cash=float(config.get("initial_cash", 10_000)), commission=float(config.get("commission", 0)), exclusive_orders=True, finalize_trades=True)
    ranges = {name: _range(value) for name, value in values.items() if _range(value)}
    if not ranges:
        raise ValueError("The saved Vibe strategy has no usable numeric parameter ranges.")
    baseline = baseline or {}
    targets = targets or []
    objective = (lambda stats: _score({str(key): _plain(value) for key, value in stats.items() if not str(key).startswith("_")}, baseline, targets)) if baseline else "SQN"
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="If you want to use multi-process optimization.*", category=RuntimeWarning)
        stats, heatmap = backtest.optimize(maximize=objective, method="grid", max_tries=max_tries, return_heatmap=True, random_state=42, **ranges)
    chosen = [StrategyParameter(name=name, value=str(getattr(stats["_strategy"], name)), notes="Backtesting.py optimized parameter") for name in ranges]
    history = [{"parameters": {name: _plain(value) for name, value in zip(ranges, index if isinstance(index, tuple) else (index,))}, "score": float(score)} for index, score in heatmap.items()]
    return _payload(stats), chosen, {"optimization_history": history, "cache_rows": len(data)}


def _adapter_class(source: str, config: dict, values: dict[str, float | int], signal_data: pd.DataFrame) -> type[Strategy]:
    tree = ast.parse(source)
    if not any(isinstance(node, ast.ClassDef) and node.name == "SignalEngine" for node in tree.body):
        raise ValueError("Saved Vibe code does not define SignalEngine.")
    code = compile(tree, "saved_vibe_signal_engine.py", "exec")
    symbol = str(config["codes"][0])

    def init(self):
        namespace = types.ModuleType("saved_vibe_signal_engine").__dict__
        exec(code, namespace)
        for name in values:
            namespace[name] = getattr(self, name)
        signals = namespace["SignalEngine"]().generate({symbol: signal_data.rename(columns=str.lower)}).get(symbol)
        if signals is None:
            raise ValueError("SignalEngine did not return a signal for its configured symbol.")
        self.signal = self.I(lambda: pd.Series(signals).reindex(self.data.df.index).fillna(0).to_numpy())

    def next(self):
        signal = float(self.signal[-1])
        if signal > 0 and not self.position.is_long:
            self.buy(size=.95)
        elif signal < 0 and not self.position.is_short:
            self.sell(size=.95)
        elif signal == 0 and self.position:
            self.position.close()

    return type("SavedVibeSignalAdapter", (Strategy,), {**values, "init": init, "next": next})


def _number(value: str) -> float | int | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return int(numeric) if numeric.is_integer() else numeric


def _range(value: float | int) -> list[float | int]:
    if isinstance(value, int):
        low, high = max(1, round(value * .6)), max(2, round(value * 1.4))
        return list(range(low, high + 1, max(1, round((high - low) / 4))))
    return [round(value * factor, 8) for factor in (.7, .85, 1, 1.15, 1.3)] if value > 0 else []


def _payload(stats: pd.Series) -> dict:
    metrics = {str(key): _plain(value) for key, value in stats.items() if not str(key).startswith("_")}
    equity, trades = stats["_equity_curve"], stats["_trades"]
    return {"metrics": metrics, "equity_curve": [float(value) for value in equity["Equity"]], "equity_timestamps": [str(index) for index in equity.index], "trades": [{key: _plain(value) for key, value in row.items()} for _, row in trades.iterrows()]}


def _plain(value):
    return value.item() if hasattr(value, "item") else str(value) if isinstance(value, (pd.Timestamp, pd.Timedelta)) else value
