"""PyTauri commands for the local Vibe-Trading companion GUI."""

import asyncio
import os
import shutil
from pathlib import Path

from anyio.from_thread import start_blocking_portal
from pytauri import Commands, builder_factory, context_factory

from .auto_workflow import create_workflow, list_workflows, load_workflow, request_stop, start_workflow
from .models import AutoOptimizeRequest, AutoWorkflow, AutoWorkflowRequest, DEFAULT_WORKSPACE, PROJECT_ROOT, ImportedBacktest, RecycledStrategyFile, RecycleStrategyFileRequest, RedoRequest, StoredBacktest, StrategyFileRequest, StrategyRun, StrategySetup
from .storage import clear_backtests, copy_strategy_save_to_good, delete_backtest, import_backtest, list_backtests, list_strategies, load_backtest, load_strategy_file, next_snapshot, open_database, recycle_strategy_save_file, restore_strategy_save_file, save_strategy, save_strategy_file
from .vibe import backtest_prompt, parse_backtest_output, parse_vibe_artifacts, run_prompt, vibe_run_directory

commands: Commands = Commands()
DATABASE = Path(PROJECT_ROOT) / "data" / "backtest_history.sqlite3"
VIBE_STAGING = Path(PROJECT_ROOT) / "data" / "vibe-staging"
GOOD_SAVES = Path(PROJECT_ROOT) / "data" / "good"
RECYCLE_BIN = Path(PROJECT_ROOT) / "data" / "recycle-bin"
AUTO_RUNS = Path(PROJECT_ROOT) / "data" / "history" / "auto-runs"


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


def _run_backtest(setup: StrategySetup, run_type: str, metrics: dict | None = None, goal: str = "", redo_source: str = "", database_path: Path = DATABASE, snapshot_workspace: Path | None = None) -> StrategyRun:
    output = run_prompt(backtest_prompt(setup, run_type, metrics, goal))
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
        if snapshot_workspace is not None:
            setup.workspace_path = str(snapshot_workspace)
        saved = save_strategy(connection, setup)
        _, path = next_snapshot(connection, saved, run_type, redo_source)
        snapshot = save_strategy_file(saved, payload, path)
        result = import_backtest(connection, path.name, payload)
        return StrategyRun(strategy=snapshot, backtest=result, output=output)

    database_path = Path(database_path)
    connection = open_database(database_path)
    try:
        run = persist(connection)
    finally:
        connection.close()
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
async def optimize_strategy_backtest(body: AutoOptimizeRequest) -> StrategyRun:
    return await asyncio.to_thread(_run_backtest, body.strategy, "optimized", body.metrics)


@commands.command()
async def auto_optimize_strategy_backtest(body: AutoOptimizeRequest) -> StrategyRun:
    return await asyncio.to_thread(_run_backtest, body.strategy, "auto", body.metrics, body.goal)


@commands.command()
async def redo_strategy_backtest(body: RedoRequest) -> StrategyRun:
    if body.run_type not in {"raw", "optimized", "auto"}:
        raise ValueError("Unknown strategy run type.")
    return await asyncio.to_thread(_run_backtest, body.strategy, body.run_type, body.metrics, body.goal, body.redo_source)


@commands.command()
async def start_auto_workflow(body: AutoWorkflowRequest) -> AutoWorkflow:
    request = body.model_copy(deep=True)
    if request.start_path.strip():
        setup, baseline = await asyncio.to_thread(load_strategy_file, Path(request.start_path))
        request.strategy = setup
        request.baseline = baseline
    if request.baseline is None:
        raise ValueError("Load a strategy snapshot with backtest results before starting an auto workflow.")
    workflow = await asyncio.to_thread(create_workflow, AUTO_RUNS, request)
    start_workflow(Path(workflow.path), request, _run_backtest)
    return workflow


@commands.command()
async def list_auto_workflows() -> list[AutoWorkflow]:
    return await asyncio.to_thread(list_workflows, AUTO_RUNS)


@commands.command()
async def load_auto_workflow(body: str) -> AutoWorkflow:
    return await asyncio.to_thread(load_workflow, Path(body))


@commands.command()
async def stop_auto_workflow(body: str) -> AutoWorkflow:
    return await asyncio.to_thread(request_stop, Path(body))


@commands.command()
async def load_strategy_save_file(body: StrategyFileRequest) -> StrategyRun:
    setup, result = await asyncio.to_thread(load_strategy_file, Path(body.path))
    await asyncio.to_thread(_save_strategy, setup)
    return StrategyRun(strategy=setup, backtest=result, output=f"Loaded {body.path}")


@commands.command()
async def preview_strategy_save_file(body: StrategyFileRequest) -> StrategyRun:
    """Read a snapshot for the Auto workflow without adding it to Manual history."""
    setup, result = await asyncio.to_thread(load_strategy_file, Path(body.path))
    return StrategyRun(strategy=setup, backtest=result, output=f"Prepared {body.path}")


@commands.command()
async def copy_strategy_save_to_good_file(body: StrategyFileRequest) -> str:
    return str(await asyncio.to_thread(copy_strategy_save_to_good, Path(body.path), GOOD_SAVES))


@commands.command()
async def recycle_strategy_save_file_command(body: StrategyFileRequest) -> RecycledStrategyFile:
    recycle_path, previous_path = await asyncio.to_thread(recycle_strategy_save_file, Path(body.path), RECYCLE_BIN)
    return RecycledStrategyFile(original_path=body.path, recycle_path=str(recycle_path), previous_path=str(previous_path) if previous_path else None)


@commands.command()
async def restore_strategy_save_file_command(body: RecycleStrategyFileRequest) -> str:
    return str(await asyncio.to_thread(restore_strategy_save_file, Path(body.original_path), Path(body.recycle_path), RECYCLE_BIN))


@commands.command()
async def import_backtest_result(body: ImportedBacktest) -> StoredBacktest:
    return await asyncio.to_thread(_with_database, lambda connection: import_backtest(connection, body.name, body.payload))


@commands.command()
async def list_imported_backtests() -> list[StoredBacktest]:
    return await asyncio.to_thread(_with_database, list_backtests)


@commands.command()
async def load_imported_backtest(body: int) -> StoredBacktest:
    return await asyncio.to_thread(_with_database, lambda connection: load_backtest(connection, body))


@commands.command()
async def delete_imported_backtest(body: int) -> None:
    await asyncio.to_thread(_with_database, lambda connection: delete_backtest(connection, body))


@commands.command()
async def clear_imported_backtests() -> None:
    await asyncio.to_thread(_with_database, clear_backtests)


def main() -> int:
    with start_blocking_portal("asyncio") as portal:
        app = builder_factory().build(context=context_factory(), invoke_handler=commands.generate_handler(portal))
        return app.run_return()
