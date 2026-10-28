"""Supported Freqtrade CLI boundary and result normalizer.

Freqtrade exposes Python classes, but its CLI/result format is the supported,
version-pinned contract for a desktop integration.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def download_data_command(exchange: str, trading_mode: str, pairs: list[str], timeframes: list[str], data_path: Path, timerange: str = "") -> list[str]:
    command = [sys.executable, "-m", "freqtrade", "download-data", "--exchange", exchange, "--trading-mode", trading_mode, "--pairs", *pairs, "--timeframes", *timeframes, "--datadir", str(data_path)]
    if timerange:
        command.extend(["--timerange", timerange])
    return command


def backtest_command(config_path: Path, strategy_name: str, strategy_path: Path, output_path: Path, data_path: Path, timerange: str = "") -> list[str]:
    command = [sys.executable, "-m", "freqtrade", "backtesting", "--config", str(config_path), "--strategy", strategy_name, "--strategy-path", str(strategy_path), "--datadir", str(data_path), "--export", "trades", "--backtest-directory", str(output_path)]
    if timerange:
        command.extend(["--timerange", timerange])
    return command


def hyperopt_command(config_path: Path, strategy_name: str, strategy_path: Path, data_path: Path, epochs: int, timerange: str = "") -> list[str]:
    command = [sys.executable, "-m", "freqtrade", "hyperopt", "--config", str(config_path), "--strategy", strategy_name, "--strategy-path", str(strategy_path), "--datadir", str(data_path), "--epochs", str(epochs), "--spaces", "enter", "exit", "--hyperopt-loss", "SharpeHyperOptLossDaily"]
    if timerange:
        command.extend(["--timerange", timerange])
    return command


def ensure_config(config_path: str, workspace: Path, exchange: str, trading_mode: str, pairs: list[str], timeframes: list[str]) -> Path:
    """Use an explicit config when supplied, otherwise create a local dry-run config."""
    if config_path.strip():
        target = Path(config_path).expanduser()
        if not target.is_file():
            raise ValueError("Freqtrade config file was not found.")
        return target
    target = workspace / "freqtrade" / "config.generated.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {
        "dry_run": True,
        "stake_currency": "USDT",
        "stake_amount": 100,
        "max_open_trades": 1,
        "timeframe": timeframes[0],
        "exchange": {"name": exchange, "key": "", "secret": "", "pair_whitelist": pairs, "pair_blacklist": []},
        "pairlists": [{"method": "StaticPairList"}],
    }
    if trading_mode == "futures":
        config.update({"trading_mode": "futures", "margin_mode": "isolated"})
    elif trading_mode == "margin":
        config["trading_mode"] = "margin"
    target.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return target


def run(command: list[str], working_directory: Path) -> str:
    result = subprocess.run(command, cwd=working_directory, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"Freqtrade exited with code {result.returncode}.\n{result.stdout[-4000:]}")
    return result.stdout


def data_is_available(data_path: Path) -> bool:
    return data_path.is_dir() and any(candidate.is_file() and candidate.suffix in {".feather", ".json", ".gz", ".parquet"} for candidate in data_path.rglob("*"))


def parse_backtest_directory(directory: Path) -> dict[str, Any]:
    latest = directory / ".last_result.json"
    candidates: list[Path] = []
    if latest.is_file():
        try:
            name = json.loads(latest.read_text(encoding="utf-8")).get("latest_backtest")
            if name:
                candidates.append(directory / name)
        except (OSError, json.JSONDecodeError):
            pass
    candidates.extend(sorted(directory.glob("backtest-result*.json*"), key=lambda item: item.stat().st_mtime, reverse=True))
    for candidate in candidates:
        if candidate.is_file():
            return normalise_result(_read_json(candidate))
    raise ValueError("Freqtrade completed but did not produce a backtest result JSON file.")


def normalise_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Freqtrade's exported result to the app's stable chart/table payload."""
    strategies = raw.get("strategy") or raw.get("strategies") or {}
    stats = next(iter(strategies.values()), raw) if isinstance(strategies, dict) else raw
    if not isinstance(stats, dict):
        raise ValueError("Freqtrade result has no strategy statistics.")
    metrics = {
        "P/L": stats.get("profit_total_abs"),
        "Return [%]": _percent(stats.get("profit_total")),
        "Win Rate [%]": _percent(stats.get("winrate")),
        "Total Trades": stats.get("total_trades"),
        "Profit Factor": stats.get("profit_factor"),
        "Sharpe Ratio": stats.get("sharpe"),
        "Sortino Ratio": stats.get("sortino"),
        "Max. Drawdown [%]": _percent(stats.get("max_drawdown_account")),
        "Avg. Drawdown [%]": _percent(stats.get("avg_drawdown_account")),
    }
    metrics = {key: value for key, value in metrics.items() if value is not None}
    trades = stats.get("trades") or raw.get("trades") or []
    trades = trades if isinstance(trades, list) else []
    equity, timestamps = _realized_equity(stats, trades)
    return {"metrics": metrics, "trades": trades, "equity_curve": equity, "equity_timestamps": timestamps, "freqtrade_result": raw}


def read_parameter_file(strategy_path: Path, strategy_name: str) -> dict[str, Any]:
    """Read Freqtrade's companion parameter export, when hyperopt created one."""
    path = strategy_path / f"{strategy_name}.json"
    if not path.is_file():
        return {}
    try:
        result = _read_json(path)
    except (OSError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("Freqtrade result must be a JSON object.")
    return value


def _percent(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return round(float(value) * 100, 6)
    return None


def _realized_equity(stats: dict[str, Any], trades: list[dict[str, Any]]) -> tuple[list[float], list[str]]:
    starting = stats.get("starting_balance")
    if not isinstance(starting, (int, float)):
        return [], []
    equity = [float(starting)]
    timestamps: list[str] = []
    for trade in sorted(trades, key=lambda item: str(item.get("close_date") or item.get("close_date_timestamp") or "")):
        profit = trade.get("profit_abs")
        if not isinstance(profit, (int, float)):
            continue
        equity.append(equity[-1] + float(profit))
        timestamps.append(str(trade.get("close_date") or trade.get("close_date_timestamp") or len(timestamps) + 1))
    return equity, timestamps
