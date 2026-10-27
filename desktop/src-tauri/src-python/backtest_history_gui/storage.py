"""SQLite storage for strategy setups and imported backtests."""

import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import DEFAULT_WORKSPACE, PROJECT_ROOT, StoredBacktest, StrategySetup

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_setups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    workspace_path TEXT NOT NULL DEFAULT '',
    optimization_goal TEXT NOT NULL DEFAULT '',
    vibe_payload_json TEXT NOT NULL DEFAULT '{}',
    parameters_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS imported_backtests (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(strategy_setups)")}
    changed = False
    if "workspace_path" not in columns:
        connection.execute("ALTER TABLE strategy_setups ADD COLUMN workspace_path TEXT NOT NULL DEFAULT ''")
        changed = True
    if "optimization_goal" not in columns:
        connection.execute("ALTER TABLE strategy_setups ADD COLUMN optimization_goal TEXT NOT NULL DEFAULT ''")
        changed = True
    if "vibe_payload_json" not in columns:
        connection.execute("ALTER TABLE strategy_setups ADD COLUMN vibe_payload_json TEXT NOT NULL DEFAULT '{}'")
        changed = True
    if changed:
        connection.commit()
    return connection


def save_strategy(connection: sqlite3.Connection, setup: StrategySetup) -> StrategySetup:
    workspace = Path(setup.workspace_path.strip() or DEFAULT_WORKSPACE).expanduser()
    if not workspace.is_absolute():
        workspace = Path(PROJECT_ROOT) / workspace
    setup.workspace_path = str(workspace.resolve())
    encoded = json.dumps([parameter.model_dump() for parameter in setup.parameters])
    vibe_payload = json.dumps(setup.vibe_payload)
    if setup.id is None:
        cursor = connection.execute(
            "INSERT INTO strategy_setups (name, source, workspace_path, optimization_goal, parameters_json, vibe_payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (setup.name, setup.source, setup.workspace_path, setup.optimization_goal, encoded, vibe_payload),
        )
        setup.id = int(cursor.lastrowid)
    else:
        connection.execute(
            "UPDATE strategy_setups SET name = ?, source = ?, workspace_path = ?, optimization_goal = ?, parameters_json = ?, vibe_payload_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (setup.name, setup.source, setup.workspace_path, setup.optimization_goal, encoded, vibe_payload, setup.id),
        )
    connection.commit()
    return setup


def _strategy_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-") or "strategy"


def next_snapshot(connection: sqlite3.Connection, setup: StrategySetup, run_type: str, redo_source: str = "") -> tuple[str, Path]:
    stem = _strategy_stem(setup.name)
    names = [row["name"] for row in connection.execute("SELECT name FROM imported_backtests WHERE name LIKE ?", (f"{stem}-{run_type}-%",))]
    iterations = _snapshot_iterations(stem, run_type, names)
    redo_match = re.match(rf"^{re.escape(stem)}-{re.escape(run_type)}-(\d+)(?:\.\d+)?-\d{{8}}\.sqlite3$", Path(redo_source).name)
    if redo_match:
        major = redo_match.group(1)
        revisions = [int(iteration.split(".", 1)[1]) for iteration in iterations if iteration.startswith(f"{major}.")]
        iteration = f"{major}.{max(revisions, default=0) + 1}"
    else:
        majors = [int(iteration.split(".", 1)[0]) for iteration in iterations]
        iteration = str(max(majors, default=0) + 1)
    workspace = Path(setup.workspace_path)
    workspace.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%m%d%Y")
    path = workspace / f"{stem}-{run_type}-{iteration}-{date}.sqlite3"
    while path.exists():
        if "." in iteration:
            major, revision = iteration.split(".", 1)
            iteration = f"{major}.{int(revision) + 1}"
        else:
            iteration = str(int(iteration) + 1)
        path = workspace / f"{stem}-{run_type}-{iteration}-{date}.sqlite3"
    return iteration, path


def _snapshot_iterations(stem: str, run_type: str, names: list[str]) -> list[str]:
    pattern = re.compile(rf"^{re.escape(stem)}-{re.escape(run_type)}-(\d+(?:\.\d+)?)-\d{{8}}\.sqlite3$")
    return [match.group(1) for name in names if (match := pattern.match(name))]


def save_strategy_file(setup: StrategySetup, payload: dict[str, Any], path: Path) -> StrategySetup:
    """Write a portable SQLite snapshot containing the setup and its result."""
    snapshot = open_database(path)
    try:
        save_strategy(snapshot, setup.model_copy(update={"id": None}))
        import_backtest(snapshot, path.name, payload)
    finally:
        snapshot.close()
    setup.strategy_file = str(path)
    return setup


def load_strategy_file(path: Path) -> tuple[StrategySetup, StoredBacktest]:
    if not path.is_file():
        raise ValueError("Strategy save file was not found.")
    snapshot = open_database(path)
    try:
        setups = list_strategies(snapshot)
        if not setups:
            raise ValueError("Strategy save file does not contain a strategy setup.")
        row = snapshot.execute("SELECT id FROM imported_backtests ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            raise ValueError("Strategy save file does not contain backtest results.")
        setup = setups[0]
        setup.strategy_file = str(path)
        return setup, load_backtest(snapshot, int(row["id"]))
    finally:
        snapshot.close()


def copy_strategy_save_to_good(path: Path, good_root: Path) -> Path:
    source = _snapshot_path(path)
    destination = _unique_path(good_root, source.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def recycle_strategy_save_file(path: Path, recycle_root: Path) -> tuple[Path, Path | None]:
    source = _snapshot_path(path)
    previous = _previous_snapshot(source)
    destination = _unique_path(recycle_root, source.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return destination, previous


def restore_strategy_save_file(original_path: Path, recycle_path: Path, recycle_root: Path) -> Path:
    source = recycle_path.resolve()
    if recycle_root.resolve() not in source.parents or not source.is_file():
        raise ValueError("Recycled strategy save file was not found.")
    destination = original_path.resolve()
    if destination.exists():
        raise ValueError("Cannot restore because a strategy save file already exists at that path.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return destination


def delete_backtest(connection: sqlite3.Connection, backtest_id: int) -> None:
    connection.execute("DELETE FROM imported_backtests WHERE id = ?", (backtest_id,))
    connection.commit()


def clear_backtests(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM imported_backtests")
    connection.commit()


def _snapshot_path(path: Path) -> Path:
    source = path.resolve()
    if source.suffix not in {".sqlite", ".sqlite3"} or not source.is_file():
        raise ValueError("Strategy save file was not found.")
    return source


def _unique_path(directory: Path, name: str) -> Path:
    candidate = directory / name
    suffix = candidate.suffix
    stem = candidate.stem
    count = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{count}{suffix}"
        count += 1
    return candidate


def _previous_snapshot(source: Path) -> Path | None:
    snapshots = [
        candidate for candidate in source.parent.glob("*.sqlite*")
        if candidate.resolve() != source and candidate.name != "backtest_history.sqlite3"
    ]
    return max(snapshots, key=lambda candidate: candidate.stat().st_mtime, default=None)


def list_strategies(connection: sqlite3.Connection) -> list[StrategySetup]:
    return [
        StrategySetup(id=row["id"], name=row["name"], source=row["source"], workspace_path=row["workspace_path"] or DEFAULT_WORKSPACE, optimization_goal=row["optimization_goal"], parameters=json.loads(row["parameters_json"]), vibe_payload=json.loads(row["vibe_payload_json"] or "{}"))
        for row in connection.execute("SELECT * FROM strategy_setups ORDER BY updated_at DESC, id DESC")
    ]


def _normalise(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[float], list[str]]:
    metrics = payload.get("metrics", payload.get("statistics", payload.get("summary", {})))
    trades = payload.get("trades", payload.get("_trades", []))
    equity = payload.get("equity_curve", payload.get("equity", payload.get("_equity_curve", [])))
    timestamps = payload.get("equity_timestamps", [])
    if not isinstance(metrics, dict) or not isinstance(trades, list) or not isinstance(equity, list):
        raise ValueError("Expected an object with metrics/statistics, trades, and optional equity_curve.")
    return metrics, [trade for trade in trades if isinstance(trade, dict)], [float(point) for point in equity if isinstance(point, (int, float))], [str(timestamp) for timestamp in timestamps if isinstance(timestamp, str)]


def import_backtest(connection: sqlite3.Connection, name: str, payload: dict[str, Any]) -> StoredBacktest:
    metrics, trades, equity, timestamps = _normalise(payload)
    cursor = connection.execute("INSERT INTO imported_backtests (name, payload_json) VALUES (?, ?)", (name, json.dumps(payload)))
    connection.commit()
    return StoredBacktest(id=int(cursor.lastrowid), name=name, imported_at="just now", metrics=metrics, trades=trades, equity_curve=equity, equity_timestamps=timestamps)


def list_backtests(connection: sqlite3.Connection) -> list[StoredBacktest]:
    rows = connection.execute("SELECT id, name, payload_json, imported_at FROM imported_backtests ORDER BY id DESC").fetchall()
    return [StoredBacktest(id=row["id"], name=row["name"], imported_at=row["imported_at"], metrics=_normalise(json.loads(row["payload_json"]))[0], trades=[], equity_curve=[]) for row in rows]


def load_backtest(connection: sqlite3.Connection, backtest_id: int) -> StoredBacktest:
    row = connection.execute("SELECT id, name, payload_json, imported_at FROM imported_backtests WHERE id = ?", (backtest_id,)).fetchone()
    if row is None:
        raise ValueError("Backtest not found.")
    metrics, trades, equity, timestamps = _normalise(json.loads(row["payload_json"]))
    return StoredBacktest(id=row["id"], name=row["name"], imported_at=row["imported_at"], metrics=metrics, trades=trades, equity_curve=equity, equity_timestamps=timestamps)
