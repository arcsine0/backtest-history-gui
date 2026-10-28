"""PyTauri commands for the local Freqtrade strategy studio."""

import asyncio
from pathlib import Path

from anyio.from_thread import start_blocking_portal
from pytauri import Commands, builder_factory, context_factory

from .freqtrade_runner import backtest_command, data_is_available, download_data_command, ensure_config, hyperopt_command, parse_backtest_directory, read_parameter_file, run as run_freqtrade
from .freqtrade_snapshot import export_strategy
from .freqtrade_templates import list_entries, list_exits, list_templates, make_template_strategy
from .models import DEFAULT_WORKSPACE, PROJECT_ROOT, FreqtradeBacktestRequest, FreqtradeExportRequest, FreqtradeTemplateRequest, StoredBacktest, StrategyFileRequest, StrategyRun, StrategySetup
from .storage import import_backtest, list_backtests, list_strategies, load_backtest, load_strategy_file, next_snapshot, open_database, save_strategy, save_strategy_file

commands: Commands = Commands()
DATABASE = Path(PROJECT_ROOT) / "data" / "freqtrade_history.sqlite3"


def _database():
    return open_database(DATABASE)


def _with_database(action):
    connection = _database()
    try:
        return action(connection)
    finally:
        connection.close()


def _run_freqtrade_backtest(request: FreqtradeBacktestRequest) -> StrategyRun:
    setup = request.strategy.model_copy(deep=True)
    payload = setup.freqtrade_payload
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
    config_path = ensure_config(request.config_path, workspace, request.exchange.strip(), request.trading_mode, pairs, timeframes)
    strategy_path, result_path, data_path = workspace / "freqtrade" / "strategies", workspace / "freqtrade" / "backtest_results", workspace / "freqtrade" / "data"
    data_output = _download_freqtrade_data(config_path, workspace, data_path, request.exchange, request.trading_mode, request.pairs, request.timeframes, request.timerange)
    strategy_path.mkdir(parents=True, exist_ok=True)
    result_path.mkdir(parents=True, exist_ok=True)
    (strategy_path / f"{class_name}.py").write_text(source, encoding="utf-8")
    if request.hyperopt_epochs:
        output = run_freqtrade(hyperopt_command(config_path, class_name, strategy_path, data_path, request.hyperopt_epochs, request.timerange), workspace)
        payload["parameter_file"] = read_parameter_file(strategy_path, class_name)
        output += "\n\n" + run_freqtrade(backtest_command(config_path, class_name, strategy_path, result_path, data_path, request.timerange), workspace)
        run_type = "hyperopt"
    else:
        output = run_freqtrade(backtest_command(config_path, class_name, strategy_path, result_path, data_path, request.timerange), workspace)
        run_type = "backtest"
    result_payload = parse_backtest_directory(result_path)
    connection = _database()
    try:
        saved = save_strategy(connection, setup)
        snapshot = save_strategy_file(saved, result_payload, next_snapshot(connection, saved, run_type))
        result = import_backtest(connection, Path(snapshot.strategy_file).name, result_payload)
    finally:
        connection.close()
    return StrategyRun(strategy=snapshot, backtest=result, output=f"Market data update:\n{data_output}\n\nExecution:\n{output}")


def _download_freqtrade_data(config_path: Path, workspace: Path, data_path: Path, exchange: str, trading_mode: str, pair_text: str, timeframe_text: str, timerange: str) -> str:
    pairs = [item.strip() for item in pair_text.split(",") if item.strip()]
    timeframes = [item.strip() for item in timeframe_text.split(",") if item.strip()]
    if not exchange.strip() or not pairs or not timeframes:
        raise ValueError("Exchange, at least one pair, and at least one timeframe are required.")
    data_path.mkdir(parents=True, exist_ok=True)
    if trading_mode not in {"spot", "margin", "futures"}:
        raise ValueError("Trading mode must be spot, margin, or futures.")
    output = run_freqtrade(download_data_command(exchange.strip(), trading_mode, pairs, timeframes, data_path, timerange), workspace)
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
