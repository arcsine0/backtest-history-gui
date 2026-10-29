"""PyTauri commands for the local Freqtrade strategy studio."""

import asyncio
import json
import re
import statistics
from pathlib import Path
from threading import Event, Lock

from anyio.from_thread import start_blocking_portal
from pytauri import Commands, builder_factory, context_factory

from .freqtrade_runner import RunCancelled, available_candle_range, backtest_command, data_covers_timerange, data_is_available, default_timerange, download_data_command, ensure_config, ensure_userdir, hyperopt_command, parse_backtest_directory, read_parameter_file, run as run_freqtrade, validation_stability_score, walk_forward_ranges, write_goal_hyperopt_loss
from .freqtrade_snapshot import export_strategy
from .freqtrade_templates import list_entries, list_exits, list_templates, make_template_strategy
from .models import DEFAULT_WORKSPACE, PROJECT_ROOT, FreqtradeBacktestRequest, FreqtradeExportRequest, FreqtradeTemplateRequest, StoredBacktest, StrategyFileRequest, StrategyRun, StrategySetup, ValidationRun, ValidationSlice
from .storage import import_backtest, list_backtests, list_strategies, load_backtest, load_strategy_file, next_snapshot, open_database, save_strategy, save_strategy_file, save_validation_file

commands: Commands = Commands()
DATABASE = Path(PROJECT_ROOT) / "data" / "freqtrade_history.sqlite3"
RUN_CANCEL = Event()
RUN_PROGRESS_LOCK = Lock()
RUN_PROGRESS = {"active": False, "label": "", "percent": 0, "sub_label": "", "sub_percent": 0, "steps": []}


def _start_progress(label: str) -> None:
    RUN_CANCEL.clear()
    with RUN_PROGRESS_LOCK:
        RUN_PROGRESS.update(active=True, label=label, percent=0, sub_label="Preparing", sub_percent=0, steps=[label])


def _set_progress(label: str, percent: int, sub_label: str = "Preparing", sub_percent: int = 0) -> None:
    with RUN_PROGRESS_LOCK:
        if not RUN_PROGRESS["steps"] or RUN_PROGRESS["steps"][-1] != label:
            RUN_PROGRESS["steps"].append(label)
        RUN_PROGRESS.update(label=label, percent=percent, sub_label=sub_label, sub_percent=sub_percent)


def _set_subprogress(label: str, percent: int) -> None:
    with RUN_PROGRESS_LOCK:
        RUN_PROGRESS.update(sub_label=label, sub_percent=max(0, min(100, percent)))


def _finish_progress() -> None:
    with RUN_PROGRESS_LOCK:
        RUN_PROGRESS["active"] = False


def _raise_if_cancelled() -> None:
    if RUN_CANCEL.is_set():
        raise RunCancelled("Freqtrade run cancelled. No snapshot was saved.")


def _run_command(command: list[str], workspace: Path, on_output=None, on_poll=None) -> str:
    return run_freqtrade(command, workspace, RUN_CANCEL, on_output, on_poll)


def _track_hyperopt_epoch(line: str, total_epochs: int) -> None:
    match = re.search(r"\b(\d+)\s*/\s*(\d+)\b", line)
    if not match:
        return
    current, total = (int(value) for value in match.groups())
    if total == total_epochs and 1 <= current <= total:
        _set_subprogress(f"Evaluating epoch {current} of {total}", round(current * 100 / total))


def _hyperopt_epoch_watcher(workspace: Path, class_name: str, total_epochs: int):
    """Read Freqtrade's append-only epoch results when Rich suppresses stdout lines."""
    directory = workspace / "user_data" / "hyperopt_results"
    initial = {path.name for path in directory.glob(f"strategy_{class_name}_*.fthypt")} if directory.is_dir() else set()
    latest_epoch = 0

    def poll() -> None:
        nonlocal latest_epoch
        try:
            candidates = [path for path in directory.glob(f"strategy_{class_name}_*.fthypt") if path.name not in initial]
            result_file = max(candidates, key=lambda path: path.stat().st_mtime)
            size = result_file.stat().st_size
            with result_file.open("rb") as handle:
                handle.seek(max(0, size - 131_072))
                lines = handle.read().decode("utf-8").splitlines()
            record = json.loads(next(line for line in reversed(lines) if line.strip()))
            epoch = record.get("current_epoch")
        except (AttributeError, OSError, StopIteration, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return
        if isinstance(epoch, int) and latest_epoch < epoch <= total_epochs:
            latest_epoch = epoch
            _set_subprogress(f"Evaluating epoch {epoch} of {total_epochs}", round(epoch * 100 / total_epochs))

    return poll


def _database():
    return open_database(DATABASE)


def _with_database(action):
    connection = _database()
    try:
        return action(connection)
    finally:
        connection.close()


def _write_strategy_files(strategy_path: Path, class_name: str, source: str, payload: dict) -> None:
    strategy_path.mkdir(parents=True, exist_ok=True)
    (strategy_path / f"{class_name}.py").write_text(source, encoding="utf-8")
    parameter_file = payload.get("parameter_file")
    if isinstance(parameter_file, dict):
        (strategy_path / f"{class_name}.json").write_text(json.dumps(parameter_file, indent=2), encoding="utf-8")


def _run_freqtrade_backtest(request: FreqtradeBacktestRequest) -> StrategyRun:
    _start_progress("Checking strategy run inputs")
    try:
        setup = request.strategy.model_copy(deep=True)
        payload = setup.freqtrade_payload
        payload["optimization_goal"] = request.optimization_goal.model_dump()
        source, class_name = payload.get("strategy_source"), payload.get("class_name")
        if not isinstance(source, str) or not isinstance(class_name, str):
            raise ValueError("Create or load a Freqtrade template strategy first.")
        workspace = Path(setup.workspace_path).expanduser().resolve()
        pairs = [item.strip() for item in request.pairs.split(",") if item.strip()]
        timeframes = [item.strip() for item in request.timeframes.split(",") if item.strip()]
        if not request.exchange.strip() or not pairs or not timeframes:
            raise ValueError("Exchange, at least one pair, and at least one timeframe are required.")
        if request.trading_mode not in {"spot", "margin", "futures"}:
            raise ValueError("Trading mode must be spot, margin, or futures.")
        _set_progress("Initializing Freqtrade workspace", 5, "Creating the local user-data directory")
        ensure_userdir(workspace)
        _raise_if_cancelled()
        timerange = request.timerange.strip() or default_timerange()
        _set_progress("Generating Freqtrade configuration", 10, "Writing exchange and pricing settings")
        config_path = ensure_config(request.config_path, workspace, request.exchange.strip(), request.trading_mode, pairs, timeframes)
        strategy_path, result_path, data_path = workspace / "freqtrade" / "strategies", workspace / "freqtrade" / "backtest_results", workspace / "freqtrade" / "data"
        _set_progress("Checking local market data", 20, "Inspecting cached candle coverage")
        data_output = _download_freqtrade_data(config_path, workspace, data_path, request.exchange, request.trading_mode, request.pairs, request.timeframes, timerange)
        _set_progress("Verifying market data", 35, "Confirming usable candle files")
        _raise_if_cancelled()
        result_path.mkdir(parents=True, exist_ok=True)
        _set_progress("Writing strategy files", 40, "Exporting strategy source and parameters")
        _write_strategy_files(strategy_path, class_name, source, payload)
        if request.hyperopt_epochs:
            _set_progress("Optimizing parameters", 45, f"Starting epoch 1 of {request.hyperopt_epochs}")
            loss_name, loss_path = write_goal_hyperopt_loss(workspace, request.optimization_goal.model_dump())
            output = _run_command(
                hyperopt_command(config_path, class_name, strategy_path, data_path, request.hyperopt_epochs, timerange, loss_name, loss_path),
                workspace,
                lambda line: _track_hyperopt_epoch(line, request.hyperopt_epochs),
                _hyperopt_epoch_watcher(workspace, class_name, request.hyperopt_epochs),
            )
            _raise_if_cancelled()
            _set_progress("Reading optimized parameters", 75, "Loading Freqtrade's parameter export")
            payload["parameter_file"] = read_parameter_file(strategy_path, class_name)
            _set_progress("Backtesting optimized parameters", 80, "Simulating optimized trades")
            output += "\n\n" + _run_command(backtest_command(config_path, class_name, strategy_path, result_path, data_path, timerange), workspace)
            run_type = "hyperopt"
        else:
            _set_progress("Running Freqtrade backtest", 55, "Simulating strategy trades")
            output = _run_command(backtest_command(config_path, class_name, strategy_path, result_path, data_path, timerange), workspace)
            run_type = "backtest"
        _raise_if_cancelled()
        _set_progress("Parsing backtest results", 90, "Reading Freqtrade result artifacts")
        result_payload = parse_backtest_directory(result_path)
        _raise_if_cancelled()
        _set_progress("Saving SQLite snapshot", 96, "Persisting strategy and backtest results")
        connection = _database()
        try:
            saved = save_strategy(connection, setup)
            _raise_if_cancelled()
            snapshot = save_strategy_file(saved, result_payload, next_snapshot(connection, saved, run_type))
            result = import_backtest(connection, Path(snapshot.strategy_file).name, result_payload)
        finally:
            connection.close()
        _set_progress("Run complete", 100, "All results saved", 100)
        return StrategyRun(strategy=snapshot, backtest=result, output=f"Market data update:\n{data_output}\n\nExecution:\n{output}")
    finally:
        _finish_progress()


def _run_freqtrade_validation(request: FreqtradeBacktestRequest) -> ValidationRun:
    _start_progress("Checking validation inputs")
    try:
        setup = request.strategy.model_copy(deep=True)
        payload = setup.freqtrade_payload
        payload["optimization_goal"] = request.optimization_goal.model_dump()
        source, class_name = payload.get("strategy_source"), payload.get("class_name")
        if not isinstance(source, str) or not isinstance(class_name, str):
            raise ValueError("Create or load a Freqtrade template strategy first.")
        workspace = Path(setup.workspace_path).expanduser().resolve()
        pairs = [item.strip() for item in request.pairs.split(",") if item.strip()]
        timeframes = [item.strip() for item in request.timeframes.split(",") if item.strip()]
        if not request.exchange.strip() or not pairs or not timeframes or request.trading_mode not in {"spot", "margin", "futures"}:
            raise ValueError("A valid exchange, trading mode, pair, and timeframe are required.")
        _set_progress("Initializing Freqtrade workspace", 5, "Creating the local user-data directory")
        ensure_userdir(workspace)
        _raise_if_cancelled()
        timerange = request.timerange.strip() or default_timerange(5)
        _set_progress("Generating Freqtrade configuration", 10, "Writing exchange and pricing settings")
        config_path = ensure_config(request.config_path, workspace, request.exchange.strip(), request.trading_mode, pairs, timeframes)
        strategy_path, validation_path, data_path = workspace / "freqtrade" / "strategies", workspace / "freqtrade" / "validation_results", workspace / "freqtrade" / "data"
        _set_progress("Checking local market data", 15, "Inspecting cached candle coverage")
        data_output = _download_freqtrade_data(config_path, workspace, data_path, request.exchange, request.trading_mode, request.pairs, request.timeframes, timerange)
        _set_progress("Verifying market data", 25, "Confirming validation candle coverage")
        _raise_if_cancelled()
        _write_strategy_files(strategy_path, class_name, source, payload)
        start, end = available_candle_range(data_path, pairs[0], timeframes[0])
        training_range, test_ranges = walk_forward_ranges(start, end, request.validation_test_count)
        ranges = [("Train", training_range), *[(f"Test {index + 1}", value) for index, value in enumerate(test_ranges)]]
        slices: list[ValidationSlice] = []
        output = [f"Market data update:\n{data_output}", f"Available candle coverage: {start:%Y-%m-%d} to {end:%Y-%m-%d}"]
        for index, (label, split_range) in enumerate(ranges):
            result_path = validation_path / f"{index:02d}"
            result_path.mkdir(parents=True, exist_ok=True)
            _set_progress(f"Running {label.lower()} backtest", 30 + round((index / len(ranges)) * 60), f"Simulating split {index + 1} of {len(ranges)}")
            execution = _run_command(backtest_command(config_path, class_name, strategy_path, result_path, data_path, split_range), workspace)
            _raise_if_cancelled()
            _set_progress(f"Parsing {label.lower()} result", 30 + round(((index + 1) / len(ranges)) * 60), f"Loading split {index + 1} of {len(ranges)}")
            result = parse_backtest_directory(result_path)
            slices.append(ValidationSlice(label=label, timerange=split_range, backtest=StoredBacktest(id=index, name=label, imported_at="just now", metrics=result["metrics"], trades=result["trades"], equity_curve=result["equity_curve"], equity_timestamps=result.get("equity_timestamps", []))))
            output.append(f"{label}:\n{execution}")
        returns = [float(item.backtest.metrics.get("Return [%]", 0)) for item in slices[1:]]
        trade_counts = [int(item.backtest.metrics.get("Total Trades", 0)) for item in slices[1:]]
        mean_return = statistics.fmean(returns)
        return_stddev = statistics.pstdev(returns)
        stability_score, _ = validation_stability_score(returns, trade_counts, request.optimization_goal.min_trades_per_test)
        _set_progress("Calculating validation score", 95, "Measuring out-of-sample return stability")
        _raise_if_cancelled()
        result = ValidationRun(training=slices[0], tests=slices[1:], stability_score=stability_score, mean_return=round(mean_return, 4), return_stddev=round(return_stddev, 4), total_test_trades=sum(trade_counts), minimum_test_trades=request.optimization_goal.min_trades_per_test, coverage=f"{start:%Y-%m-%d} to {end:%Y-%m-%d}", output="\n\n".join(output))
        connection = _database()
        try:
            saved = save_strategy(connection, setup)
            validation_path = next_snapshot(connection, saved, "validation")
        finally:
            connection.close()
        result.snapshot_path = str(validation_path)
        save_validation_file(saved, result.model_dump(), validation_path)
        _set_progress("Validation complete", 100, "All validation splits processed", 100)
        return result
    finally:
        _finish_progress()


def _download_freqtrade_data(config_path: Path, workspace: Path, data_path: Path, exchange: str, trading_mode: str, pair_text: str, timeframe_text: str, timerange: str) -> str:
    pairs = [item.strip() for item in pair_text.split(",") if item.strip()]
    timeframes = [item.strip() for item in timeframe_text.split(",") if item.strip()]
    if not exchange.strip() or not pairs or not timeframes:
        raise ValueError("Exchange, at least one pair, and at least one timeframe are required.")
    data_path.mkdir(parents=True, exist_ok=True)
    if trading_mode not in {"spot", "margin", "futures"}:
        raise ValueError("Trading mode must be spot, margin, or futures.")
    if data_covers_timerange(data_path, pairs, timeframes, timerange):
        _set_subprogress("Local cache covers all selected pairs and timeframes", 100)
        return "Using local candle cache for the requested timerange."
    _set_progress("Downloading market data", 25, "Fetching required candle history")
    output = _run_command(download_data_command(exchange.strip(), trading_mode, pairs, timeframes, data_path, timerange), workspace)
    _set_subprogress("Market candle download complete", 100)
    if not data_is_available(data_path):
        raise ValueError("Freqtrade finished without writing usable candle data.")
    return output


@commands.command()
async def project_root() -> str:
    return PROJECT_ROOT


@commands.command()
async def default_workspace() -> str:
    return DEFAULT_WORKSPACE


@commands.command()
async def list_freqtrade_templates() -> list[dict]:
    return list_templates()


@commands.command()
async def list_freqtrade_entries() -> list[dict]:
    return list_entries()


@commands.command()
async def list_freqtrade_exits() -> list[dict]:
    return list_exits()


@commands.command()
async def create_freqtrade_template(body: FreqtradeTemplateRequest) -> StrategySetup:
    setup = await asyncio.to_thread(make_template_strategy, body.name, body.template_id, body.workspace_path, body.entry_id, body.exit_id)
    return await asyncio.to_thread(_with_database, lambda connection: save_strategy(connection, setup))


@commands.command()
async def run_freqtrade_backtest(body: FreqtradeBacktestRequest) -> StrategyRun:
    return await asyncio.to_thread(_run_freqtrade_backtest, body)


@commands.command()
async def run_freqtrade_validation(body: FreqtradeBacktestRequest) -> ValidationRun:
    return await asyncio.to_thread(_run_freqtrade_validation, body)


@commands.command()
async def get_freqtrade_progress() -> dict:
    with RUN_PROGRESS_LOCK:
        return {**RUN_PROGRESS, "steps": list(RUN_PROGRESS["steps"])}


@commands.command()
async def cancel_freqtrade_run() -> bool:
    with RUN_PROGRESS_LOCK:
        if not RUN_PROGRESS["active"]:
            return False
        RUN_CANCEL.set()
        if not RUN_PROGRESS["steps"] or RUN_PROGRESS["steps"][-1] != "Stopping Freqtrade process":
            RUN_PROGRESS["steps"].append("Stopping Freqtrade process")
        RUN_PROGRESS.update(label="Stopping Freqtrade process", sub_label="Terminating the active Freqtrade process tree")
    return True


@commands.command()
async def export_freqtrade_strategy(body: FreqtradeExportRequest) -> str:
    return str(await asyncio.to_thread(export_strategy, body.path, body.destination))


@commands.command()
async def list_strategy_setups() -> list[StrategySetup]:
    return await asyncio.to_thread(_with_database, list_strategies)


@commands.command()
async def load_strategy_save_file(body: StrategyFileRequest) -> StrategyRun:
    setup, result = await asyncio.to_thread(load_strategy_file, Path(body.path))
    return StrategyRun(strategy=setup, backtest=result, output=f"Loaded {body.path}")


@commands.command()
async def list_imported_backtests() -> list[StoredBacktest]:
    return await asyncio.to_thread(_with_database, list_backtests)


@commands.command()
async def load_imported_backtest(body: int) -> StoredBacktest:
    return await asyncio.to_thread(_with_database, lambda connection: load_backtest(connection, body))


def main() -> int:
    with start_blocking_portal("asyncio") as portal:
        app = builder_factory().build(context=context_factory(), invoke_handler=commands.generate_handler(portal))
        return app.run_return()
