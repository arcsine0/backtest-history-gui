"""SQLite backup for completed backtest results."""

import json
import sqlite3
from pathlib import Path

from .models import BacktestResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    exchange_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    request_json TEXT NOT NULL,
    statistics_json TEXT NOT NULL,
    trades_json TEXT NOT NULL
);
"""


def open_database(path: Path) -> sqlite3.Connection:
    """Open the local backup database and create the initial schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(SCHEMA)
    return connection


def save_result(connection: sqlite3.Connection, result: BacktestResult) -> int:
    """Save one completed run. TODO: Add migrations when this schema changes."""
    request = result.request
    cursor = connection.execute(
        """INSERT INTO backtest_runs (
            exchange_id, symbol, timeframe, strategy_name, request_json,
            statistics_json, trades_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            request.market_data.exchange_id,
            request.market_data.symbol,
            request.market_data.timeframe,
            request.strategy_name,
            json.dumps(request, default=lambda value: value.__dict__),
            json.dumps(result.statistics),
            json.dumps(result.trades),
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


# TODO: Add typed list_runs() and load_run() queries for the history screen.
