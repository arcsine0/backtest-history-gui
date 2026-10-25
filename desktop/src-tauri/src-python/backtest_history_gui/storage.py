"""SQLite storage for strategy setups and imported backtests."""

import json
import re
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
    if "workspace_path" not in columns:
        connection.execute("ALTER TABLE strategy_setups ADD COLUMN workspace_path TEXT NOT NULL DEFAULT ''")
        connection.commit()
    return connection


def save_strategy(connection: sqlite3.Connection, setup: StrategySetup) -> StrategySetup:
    workspace = Path(setup.workspace_path.strip() or DEFAULT_WORKSPACE).expanduser()
    if not workspace.is_absolute():
        workspace = Path(PROJECT_ROOT) / workspace
    setup.workspace_path = str(workspace.resolve())
    encoded = json.dumps([parameter.model_dump() for parameter in setup.parameters])
    if setup.id is None:
        cursor = connection.execute(
            "INSERT INTO strategy_setups (name, source, workspace_path, parameters_json) VALUES (?, ?, ?, ?)",
            (setup.name, setup.source, setup.workspace_path, encoded),
        )
        setup.id = int(cursor.lastrowid)
    else:
        connection.execute(
            "UPDATE strategy_setups SET name = ?, source = ?, workspace_path = ?, parameters_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (setup.name, setup.source, setup.workspace_path, encoded, setup.id),
        )
    connection.commit()
    return setup


def _strategy_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-") or "strategy"


def next_snapshot(connection: sqlite3.Connection, setup: StrategySetup, run_type: str) -> tuple[int, Path]:
    stem = _strategy_stem(setup.name)
    count = connection.execute("SELECT COUNT(*) FROM imported_backtests WHERE name LIKE ?", (f"{stem}-{run_type}-%",)).fetchone()[0]
    workspace = Path(setup.workspace_path)
    workspace.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%m%d%Y")
    iteration = int(count) + 1
    path = workspace / f"{stem}-{run_type}-{iteration}-{date}.sqlite3"
    while path.exists():
        iteration += 1
        path = workspace / f"{stem}-{run_type}-{iteration}-{date}.sqlite3"
    return iteration, path


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


def list_strategies(connection: sqlite3.Connection) -> list[StrategySetup]:
    return [
        StrategySetup(id=row["id"], name=row["name"], source=row["source"], workspace_path=row["workspace_path"] or DEFAULT_WORKSPACE, parameters=json.loads(row["parameters_json"]))
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
