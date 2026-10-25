"""PyTauri commands for the local Vibe-Trading companion GUI."""

import asyncio
import os
import shutil
from pathlib import Path

from anyio.from_thread import start_blocking_portal
from pytauri import Commands, builder_factory, context_factory

from .models import AutoOptimizeRequest, DEFAULT_WORKSPACE, PROJECT_ROOT, ImportedBacktest, StoredBacktest, StrategyFileRequest, StrategyRun, StrategySetup
from .storage import import_backtest, list_backtests, list_strategies, load_backtest, load_strategy_file, next_snapshot, open_database, save_strategy, save_strategy_file
from .vibe import backtest_prompt, parse_backtest_output, parse_vibe_artifacts, run_prompt, vibe_run_directory

commands: Commands = Commands()
DATABASE = Path(PROJECT_ROOT) / "data" / "backtest_history.sqlite3"
VIBE_STAGING = Path(PROJECT_ROOT) / "data" / "vibe-staging"


def _database():
    return open_database(DATABASE)


def _with_database(action):
    connection = _database()
    try:
        return action(connection)
    finally:
        connection.close()


def _save_strategy(setup: StrategySetup) -> StrategySetup:
    return _with_database(lambda connection: save_strategy(connection, setup))


def _stage_vibe_run(run_dir: Path) -> Path:
    source_root = Path(os.environ.get("VIBE_TRADING_HOME", Path.home() / ".vibe-trading")) / "runs"
    source = run_dir.resolve()
    if source.parent != source_root.resolve() or not (source / "artifacts").is_dir():
        raise ValueError("Vibe-Trading returned an unsafe or incomplete run directory.")
    VIBE_STAGING.mkdir(parents=True, exist_ok=True)
    destination = VIBE_STAGING / source.name
    if destination.exists():
        raise ValueError("A Vibe-Trading staging directory already exists for this run.")
    shutil.move(str(source), str(destination))
    return destination


def _run_backtest(setup: StrategySetup, run_type: str, metrics: dict | None = None) -> StrategyRun:
    output = run_prompt(backtest_prompt(setup, run_type, metrics))
    staged_run: Path | None = None
    try:
        run_dir = vibe_run_directory(output)
        if run_dir is None:
            payload, parameters = parse_backtest_output(output)
        else:
            staged_run = _stage_vibe_run(run_dir)
            payload, parameters = parse_vibe_artifacts(staged_run)
    except ValueError as error:
        return StrategyRun(strategy=setup, output=output, error=str(error))
    setup.parameters = parameters

    def persist(connection):
        saved = save_strategy(connection, setup)
        _, path = next_snapshot(connection, saved, run_type)
        snapshot = save_strategy_file(saved, payload, path)
        result = import_backtest(connection, path.name, payload)
        return StrategyRun(strategy=snapshot, backtest=result, output=output)

    run = _with_database(persist)
    if staged_run is not None:
        try:
            shutil.rmtree(staged_run)
        except OSError as error:
            run.output = f"{output}\n\nWarning: SQLite conversion succeeded, but staging cleanup failed: {error}"
    return run


@commands.command()
async def project_root() -> str:
    return PROJECT_ROOT


@commands.command()
async def default_workspace() -> str:
    return DEFAULT_WORKSPACE


@commands.command()
async def list_strategy_setups() -> list[StrategySetup]:
    return await asyncio.to_thread(_with_database, list_strategies)


@commands.command()
async def save_strategy_setup(body: StrategySetup) -> StrategySetup:
    return await asyncio.to_thread(_save_strategy, body)


@commands.command()
async def run_strategy_backtest(body: StrategySetup) -> StrategyRun:
    return await asyncio.to_thread(_run_backtest, body, "raw")


@commands.command()
async def optimize_strategy_backtest(body: StrategySetup) -> StrategyRun:
    return await asyncio.to_thread(_run_backtest, body, "optimized")


@commands.command()
async def auto_optimize_strategy_backtest(body: AutoOptimizeRequest) -> StrategyRun:
    return await asyncio.to_thread(_run_backtest, body.strategy, "auto", body.metrics)


@commands.command()
async def load_strategy_save_file(body: StrategyFileRequest) -> StrategyRun:
    setup, result = await asyncio.to_thread(load_strategy_file, Path(body.path))
    await asyncio.to_thread(_save_strategy, setup)
    return StrategyRun(strategy=setup, backtest=result, output=f"Loaded {body.path}")


@commands.command()
async def import_backtest_result(body: ImportedBacktest) -> StoredBacktest:
    return await asyncio.to_thread(_with_database, lambda connection: import_backtest(connection, body.name, body.payload))


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
