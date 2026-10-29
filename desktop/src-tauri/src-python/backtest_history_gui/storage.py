"""SQLite storage for Freqtrade strategies and normalized result history."""

import json
import os
import re
import shutil
import sqlite3
import ctypes
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .models import DEFAULT_WORKSPACE, PROJECT_ROOT, StoredBacktest, StrategySetup

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_setups (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    workspace_path TEXT NOT NULL,
    template_id TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    freqtrade_payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS imported_backtests (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS validation_runs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def save_strategy(connection: sqlite3.Connection, setup: StrategySetup) -> StrategySetup:
    workspace = Path(setup.workspace_path.strip() or DEFAULT_WORKSPACE).expanduser()
    if not workspace.is_absolute():
        workspace = Path(PROJECT_ROOT) / workspace
    setup.workspace_path = str(workspace.resolve())
    values = (setup.name, setup.source, setup.workspace_path, setup.template_id, json.dumps([item.model_dump() for item in setup.parameters]), json.dumps(setup.freqtrade_payload))
    if setup.id is None:
        cursor = connection.execute("INSERT INTO strategy_setups (name, source, workspace_path, template_id, parameters_json, freqtrade_payload_json) VALUES (?, ?, ?, ?, ?, ?)", values)
        setup.id = int(cursor.lastrowid)
    else:
        connection.execute("UPDATE strategy_setups SET name=?, source=?, workspace_path=?, template_id=?, parameters_json=?, freqtrade_payload_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*values, setup.id))
    connection.commit()
    return setup


def next_snapshot(connection: sqlite3.Connection, setup: StrategySetup, run_type: str) -> Path:
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", setup.name).strip("-") or "strategy"
    count = connection.execute("SELECT COUNT(*) FROM imported_backtests WHERE name LIKE ?", (f"{stem}-{run_type}-%",)).fetchone()[0] + 1
    path = Path(setup.workspace_path) / f"{stem}-{run_type}-{count}-{datetime.now():%m%d%Y}.sqlite3"
    while path.exists():
        count += 1
        path = Path(setup.workspace_path) / f"{stem}-{run_type}-{count}-{datetime.now():%m%d%Y}.sqlite3"
    return path


def save_strategy_file(setup: StrategySetup, payload: dict[str, Any], path: Path) -> StrategySetup:
    snapshot = open_database(path)
    try:
        save_strategy(snapshot, setup.model_copy(update={"id": None}))
        import_backtest(snapshot, path.name, payload)
    finally:
        snapshot.close()
    setup.strategy_file = str(path)
    return setup


def save_validation_file(setup: StrategySetup, payload: dict[str, Any], path: Path) -> StrategySetup:
    """Persist all train/test slices with a portable strategy snapshot."""
    snapshot = open_database(path)
    try:
        save_strategy(snapshot, setup.model_copy(update={"id": None}))
        training = payload.get("training", {}).get("backtest")
        if isinstance(training, dict):
            import_backtest(snapshot, path.name, training)
        snapshot.execute("INSERT INTO validation_runs (name, payload_json) VALUES (?, ?)", (path.name, json.dumps(payload)))
        snapshot.commit()
    finally:
        snapshot.close()
    setup.strategy_file = str(path)
    return setup


def load_strategy_file(path: Path) -> tuple[StrategySetup, StoredBacktest]:
    if not path.is_file():
        raise ValueError("Strategy save file was not found.")
    connection = open_database(path)
    try:
        setup = list_strategies(connection)[0]
        row = connection.execute("SELECT id FROM imported_backtests ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            raise ValueError("Strategy save file does not contain backtest results.")
        setup.strategy_file = str(path)
        return setup, load_backtest(connection, row["id"])
    finally:
        connection.close()


def list_strategies(connection: sqlite3.Connection) -> list[StrategySetup]:
    return [StrategySetup(id=row["id"], name=row["name"], source=row["source"], workspace_path=row["workspace_path"], template_id=row["template_id"], parameters=json.loads(row["parameters_json"]), freqtrade_payload=json.loads(row["freqtrade_payload_json"])) for row in connection.execute("SELECT * FROM strategy_setups ORDER BY updated_at DESC, id DESC")]


def import_backtest(connection: sqlite3.Connection, name: str, payload: dict[str, Any]) -> StoredBacktest:
    metrics, trades, equity, timestamps = _normalise(payload)
    cursor = connection.execute("INSERT INTO imported_backtests (name, payload_json) VALUES (?, ?)", (name, json.dumps(payload)))
    connection.commit()
    return StoredBacktest(id=cursor.lastrowid, name=name, imported_at="just now", metrics=metrics, trades=trades, equity_curve=equity, equity_timestamps=timestamps)


def list_backtests(connection: sqlite3.Connection) -> list[StoredBacktest]:
    rows = connection.execute("SELECT id, name, payload_json, imported_at FROM imported_backtests ORDER BY id DESC").fetchall()
    return [StoredBacktest(id=row["id"], name=row["name"], imported_at=row["imported_at"], metrics=_normalise(json.loads(row["payload_json"]))[0], trades=[], equity_curve=[]) for row in rows]


def load_backtest(connection: sqlite3.Connection, backtest_id: int) -> StoredBacktest:
    row = connection.execute("SELECT id, name, payload_json, imported_at FROM imported_backtests WHERE id=?", (backtest_id,)).fetchone()
    if row is None:
        raise ValueError("Backtest not found.")
    metrics, trades, equity, timestamps = _normalise(json.loads(row["payload_json"]))
    return StoredBacktest(id=row["id"], name=row["name"], imported_at=row["imported_at"], metrics=metrics, trades=trades, equity_curve=equity, equity_timestamps=timestamps)


def list_downloaded_datasets(workspace: Path) -> list[dict[str, Any]]:
    """List cached Freqtrade candles without inspecting their contents."""
    data_path = workspace.resolve() / "freqtrade" / "data"
    if not data_path.is_dir():
        return []
    datasets = [path for path in data_path.rglob("*") if path.is_file() and path.suffix.lower() in {".feather", ".json", ".gz", ".parquet"}]
    return [{"path": str(path.relative_to(data_path)), "bytes": path.stat().st_size} for path in sorted(datasets)]


def clear_freqtrade_results(connection: sqlite3.Connection, workspace: Path, kind: str, on_artifact: Callable[[str, int], None] | None = None) -> dict[str, int]:
    """Clear one result class; downloaded market candles deliberately remain untouched."""
    targets = {
        "backtests": ("-backtest-", [workspace / "freqtrade" / "backtest_results"]),
        "hyperopts": ("-hyperopt-", [workspace / "user_data" / "hyperopt_results", workspace / "user_data" / "hyperopts" / "StudioGoalHyperOptLoss.py"]),
        "validations": ("-validation-", [workspace / "freqtrade" / "validation_results"]),
    }
    if kind not in targets:
        raise ValueError("Clear kind must be backtests, hyperopts, or validations.")
    marker, artifact_paths = targets[kind]
    root = workspace.resolve()
    snapshots = [path for path in root.glob(f"*{marker}*.sqlite3") if path.is_file()]
    rows = connection.execute("SELECT name FROM imported_backtests WHERE name LIKE ?", (f"%{marker}%",)).fetchall()
    connection.execute("DELETE FROM imported_backtests WHERE name LIKE ?", (f"%{marker}%",))
    if kind == "validations":
        connection.execute("DELETE FROM validation_runs WHERE name LIKE ?", (f"%{marker}%",))
    connection.commit()
    moved = 0
    paths = [*snapshots, *artifact_paths]
    for index, path in enumerate(paths, start=1):
        if path.exists():
            if on_artifact:
                on_artifact(f"Moving {path.name} to the Recycle Bin", round(index * 100 / len(paths)))
            _move_to_recycle(path)
            moved += 1
    return {"history": len(rows), "files": moved}


def _move_to_recycle(path: Path) -> None:
    """Use the Windows Recycle Bin so clearing local artifacts is recoverable."""
    if os.name != "nt":
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_bool), ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]

    operation = SHFILEOPSTRUCTW(None, 3, f"{path}\0\0", None, 0x40 | 0x10 | 0x4 | 0x400, False, None, None)
    if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation)) or operation.fAnyOperationsAborted:
        raise OSError(f"Could not move {path} to the Recycle Bin.")


def _normalise(payload: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[float], list[str]]:
    metrics = payload.get("metrics", {})
    trades = payload.get("trades", [])
    equity = payload.get("equity_curve", [])
    timestamps = payload.get("equity_timestamps", [])
    if not isinstance(metrics, dict) or not isinstance(trades, list) or not isinstance(equity, list):
        raise ValueError("Expected Freqtrade metrics, trades, and an optional equity curve.")
    return metrics, [item for item in trades if isinstance(item, dict)], [float(item) for item in equity if isinstance(item, (int, float))], [str(item) for item in timestamps]
