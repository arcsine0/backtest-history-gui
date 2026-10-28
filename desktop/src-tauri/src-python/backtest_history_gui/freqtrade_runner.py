"""Supported Freqtrade CLI boundary and result normalizer.

Freqtrade exposes Python classes, but its CLI/result format is the supported,
version-pinned contract for a desktop integration.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from datetime import datetime, timezone
from zipfile import ZipFile
from pathlib import Path
from typing import Any


def download_data_command(exchange: str, trading_mode: str, pairs: list[str], timeframes: list[str], data_path: Path, timerange: str = "") -> list[str]:
    command = [sys.executable, "-m", "freqtrade", "download-data", "--exchange", exchange, "--trading-mode", trading_mode, "--pairs", *pairs, "--timeframes", *timeframes, "--datadir", str(data_path)]
    if timerange:
        command.extend(["--prepend", "--timerange", timerange])
    return command


def default_timerange() -> str:
    """Five calendar years ending today, used when the UI leaves timerange blank."""
    end = datetime.now(timezone.utc)
    try:
        start = end.replace(year=end.year - 5)
    except ValueError:  # February 29th
        start = end.replace(year=end.year - 5, day=28)
    return f"{start:%Y%m%d}-{end:%Y%m%d}"


def walk_forward_ranges(start: datetime, end: datetime, test_count: int = 10) -> tuple[str, list[str]]:
    """Reserve the first 70% for training and divide the remaining 30% chronologically."""
    if start >= end:
        raise ValueError("Downloaded candle range is invalid.")
    duration = end - start
    train_end = start + duration * 0.7
    test_duration = (end - train_end) / test_count
    def timerange(left: datetime, right: datetime) -> str:
        return f"{left:%Y%m%dT%H%M}-{right:%Y%m%dT%H%M}"
    return timerange(start, train_end), [timerange(train_end + test_duration * index, train_end + test_duration * (index + 1)) for index in range(test_count)]


def available_candle_range(data_path: Path, pair: str, timeframe: str) -> tuple[datetime, datetime]:
    """Use the candle file actually downloaded, so unavailable exchange history is skipped."""
    import pandas as pd

    stem = pair.replace("/", "_").replace(":", "_")
    files = [path for path in data_path.rglob(f"{stem}-{timeframe}*.feather") if "funding_rate" not in path.name and "-mark" not in path.name]
    if not files:
        raise ValueError(f"Freqtrade did not download {pair} {timeframe} candles.")
    frame = pd.read_feather(files[0], columns=["date"])
    if frame.empty or "date" not in frame:
        raise ValueError(f"Downloaded {pair} {timeframe} candles have no usable dates.")
    dates = pd.to_datetime(frame["date"], utc=True)
    return dates.min().to_pydatetime(), dates.max().to_pydatetime()


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


def userdir_command(user_data_path: Path) -> list[str]:
    return [sys.executable, "-m", "freqtrade", "create-userdir", "--userdir", str(user_data_path)]


def ensure_userdir(workspace: Path) -> Path:
    """Create Freqtrade's required standard workspace directory once."""
    user_data_path = workspace / "user_data"
    if not user_data_path.is_dir():
        run(userdir_command(user_data_path), workspace)
    return user_data_path


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
        "entry_pricing": {"price_side": "same", "use_order_book": True, "order_book_top": 1},
        "exit_pricing": {"price_side": "same", "use_order_book": True, "order_book_top": 1},
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
    candidates.extend(sorted((item for item in directory.glob("backtest-result*") if item.suffix in {".json", ".gz", ".zip"}), key=lambda item: item.stat().st_mtime, reverse=True))
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
    if path.suffix == ".zip":
        with ZipFile(path) as archive:
            result_name = next((name for name in archive.namelist() if name.endswith(".json") and not name.endswith("_config.json")), "")
            if not result_name:
                raise ValueError("Freqtrade ZIP result has no statistics JSON file.")
            value = json.loads(archive.read(result_name).decode("utf-8"))
        if isinstance(value, dict):
            return value
        raise ValueError("Freqtrade result must be a JSON object.")
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
