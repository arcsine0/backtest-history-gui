"""Supported Freqtrade CLI boundary and result normalizer.

Freqtrade exposes Python classes, but its CLI/result format is the supported,
version-pinned contract for a desktop integration.
"""

from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
from queue import Empty, Queue
from threading import Event, Thread
from datetime import datetime, timezone
from zipfile import ZipFile
from pathlib import Path
from typing import Any, Callable


def download_data_command(exchange: str, trading_mode: str, pairs: list[str], timeframes: list[str], data_path: Path, timerange: str = "") -> list[str]:
    command = [sys.executable, "-m", "freqtrade", "download-data", "--exchange", exchange, "--trading-mode", trading_mode, "--pairs", *pairs, "--timeframes", *timeframes, "--datadir", str(data_path)]
    if timerange:
        command.extend(["--prepend", "--timerange", timerange])
    return command


def default_timerange(years: int = 1) -> str:
    """Calendar-year range ending today, used when the UI leaves timerange blank."""
    end = datetime.now(timezone.utc)
    try:
        start = end.replace(year=end.year - years)
    except ValueError:  # February 29th
        start = end.replace(year=end.year - years, day=28)
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


def data_covers_timerange(data_path: Path, pairs: list[str], timeframes: list[str], timerange: str) -> bool:
    """Avoid a network refresh when every requested local candle file covers the range."""
    try:
        start_text, end_text = timerange.split("-", maxsplit=1)
        start = datetime.strptime(start_text[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(end_text[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    try:
        for pair in pairs:
            for timeframe in timeframes:
                available_start, available_end = available_candle_range(data_path, pair, timeframe)
                if start < available_start or end > available_end:
                    return False
        return True
    except ValueError:
        return False


def backtest_command(config_path: Path, strategy_name: str, strategy_path: Path, output_path: Path, data_path: Path, timerange: str = "") -> list[str]:
    command = [sys.executable, "-m", "freqtrade", "backtesting", "--config", str(config_path), "--strategy", strategy_name, "--strategy-path", str(strategy_path), "--datadir", str(data_path), "--export", "trades", "--backtest-directory", str(output_path)]
    if timerange:
        command.extend(["--timerange", timerange])
    return command


def hyperopt_command(config_path: Path, strategy_name: str, strategy_path: Path, data_path: Path, epochs: int, timerange: str = "", loss_name: str = "SharpeHyperOptLossDaily", hyperopt_path: Path | None = None) -> list[str]:
    command = [sys.executable, "-m", "freqtrade", "hyperopt", "--config", str(config_path), "--strategy", strategy_name, "--strategy-path", str(strategy_path), "--datadir", str(data_path), "--epochs", str(epochs), "--spaces", "enter", "exit", "--hyperopt-loss", loss_name]
    if hyperopt_path:
        command.extend(["--hyperopt-path", str(hyperopt_path)])
    if timerange:
        command.extend(["--timerange", timerange])
    return command


def write_goal_hyperopt_loss(workspace: Path, goal: dict[str, Any]) -> tuple[str, Path]:
    """Generate the Freqtrade loss objective from the UI's bounded goal values."""
    profile = str(goal.get("profile", "balanced"))
    frequency_weight, return_weight, drawdown_weight = {
        "higher_frequency": (2.0, 1.0, 1.0),
        "return_focused": (0.5, 2.0, 1.0),
        "capital_preservation": (0.5, 1.0, 2.0),
    }.get(profile, (1.0, 1.0, 1.0))
    target = int(goal.get("target_trades_per_year", 100))
    max_drawdown = float(goal.get("max_drawdown_pct", 25)) / 100
    minimum_profit_factor = float(goal.get("min_profit_factor", 1.1))
    directory = workspace / "user_data" / "hyperopts"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "StudioGoalHyperOptLoss.py"
    path.write_text(f'''from datetime import datetime
from math import inf
from typing import Any

from freqtrade.optimize.hyperopt import IHyperOptLoss


class StudioGoalHyperOptLoss(IHyperOptLoss):
    @staticmethod
    def hyperopt_loss_function(*, results, trade_count: int, min_date: datetime, max_date: datetime, backtest_stats: dict[str, Any], **kwargs) -> float:
        years = max((max_date - min_date).total_seconds() / 31_557_600, 1 / 365)
        annualized_trades = trade_count / years
        profits = results["profit_ratio"]
        gross_profit = float(profits[profits > 0].sum())
        gross_loss = abs(float(profits[profits < 0].sum()))
        profit_factor = gross_profit / gross_loss if gross_loss else (inf if gross_profit else 0.0)
        total_profit = float(profits.sum())
        drawdown = float(backtest_stats.get("max_drawdown_account", 0.0) or 0.0)
        frequency_shortfall = max(0.0, ({target} - annualized_trades) / {target})
        drawdown_excess = max(0.0, (drawdown - {max_drawdown}) / {max_drawdown})
        profit_factor_shortfall = max(0.0, {minimum_profit_factor} - profit_factor) if profit_factor != inf else 0.0
        return ({frequency_weight} * frequency_shortfall ** 2) + ({drawdown_weight} * drawdown_excess * 2) + (profit_factor_shortfall * 2) + max(0.0, -total_profit) * 10 - ({return_weight} * total_profit)
''', encoding="utf-8")
    return "StudioGoalHyperOptLoss", directory


def validation_stability_score(test_returns: list[float], trade_counts: list[int], minimum_trades_per_test: int) -> tuple[float, float]:
    """Discount stable returns that are based on too few out-of-sample trades."""
    if not test_returns or len(test_returns) != len(trade_counts):
        return 0.0, 0.0
    mean_return = sum(test_returns) / len(test_returns)
    if mean_return <= 0:
        return 0.0, mean_return
    variance = sum((value - mean_return) ** 2 for value in test_returns) / len(test_returns)
    base_score = 100 / (1 + variance ** 0.5)
    required_total = minimum_trades_per_test * len(trade_counts)
    total_coverage = min(1.0, sum(trade_counts) / required_total)
    weakest_coverage = min(1.0, min(trade_counts) / minimum_trades_per_test)
    return round(base_score * total_coverage ** 0.5 * weakest_coverage ** 0.5, 2), mean_return


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


class RunCancelled(Exception):
    pass


def run(command: list[str], working_directory: Path, cancel_event: Event | None = None, on_output: Callable[[str], None] | None = None, on_poll: Callable[[], None] | None = None) -> str:
    process = subprocess.Popen(command, cwd=working_directory, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines: Queue[str | None] = Queue()

    def read_output() -> None:
        assert process.stdout
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    Thread(target=read_output, daemon=True).start()
    output: list[str] = []
    while True:
        if on_poll:
            on_poll()
        if cancel_event and cancel_event.is_set():
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()
            raise RunCancelled("Freqtrade run cancelled. No snapshot was saved.")
        try:
            line = lines.get(timeout=0.25)
            if line is None:
                break
            output.append(line)
            if on_output:
                on_output(line)
        except Empty:
            continue
    process.wait()
    if on_poll:
        on_poll()
    if process.stdout:
        process.stdout.close()
    stdout = "".join(output)
    if process.returncode:
        raise RuntimeError(f"Freqtrade exited with code {process.returncode}.\n{stdout[-4000:]}")
    if cancel_event and cancel_event.is_set():
        raise RunCancelled("Freqtrade run cancelled. No snapshot was saved.")
    return stdout


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
