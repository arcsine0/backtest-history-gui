"""Portable Freqtrade snapshot reader.  Uses only the Python standard library.

Copy this file to a VPS or another project to read a Backtest Studio SQLite
snapshot and export its generated strategy without installing the desktop app.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def load_freqtrade_snapshot(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.suffix not in {".sqlite", ".sqlite3"} or not source.is_file():
        raise ValueError("Expected an existing SQLite strategy snapshot.")
    connection = sqlite3.connect(source)
    try:
        row = connection.execute("SELECT * FROM strategy_setups ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            raise ValueError("Snapshot does not contain a strategy setup.")
        columns = [column[0] for column in connection.execute("SELECT * FROM strategy_setups LIMIT 0").description]
        setup = dict(zip(columns, row))
        try:
            validations = [json.loads(item[0]) for item in connection.execute("SELECT payload_json FROM validation_runs ORDER BY id DESC")]
        except sqlite3.OperationalError:
            validations = []
    finally:
        connection.close()
    payload = json.loads(setup.get("freqtrade_payload_json") or "{}")
    if payload.get("format") not in {"freqtrade-strategy-v1", "freqtrade-strategy-v2"} or not payload.get("strategy_source"):
        raise ValueError("Snapshot does not contain a Freqtrade strategy export.")
    return {"name": setup["name"], "template_id": setup.get("template_id", ""), "parameters": json.loads(setup["parameters_json"]), "payload": payload, "validations": validations}


def export_strategy(snapshot_path: str | Path, destination: str | Path) -> Path:
    snapshot = load_freqtrade_snapshot(snapshot_path)
    target = Path(destination)
    if target.suffix == "" or (target.exists() and target.is_dir()):
        target = target / f"{snapshot['payload']['class_name']}.py"
    if target.suffix != ".py":
        raise ValueError("Strategy export destination must be a .py file or an existing directory.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(snapshot["payload"]["strategy_source"], encoding="utf-8")
    parameter_file = snapshot["payload"].get("parameter_file")
    if isinstance(parameter_file, dict):
        target.with_suffix(".json").write_text(json.dumps(parameter_file, indent=2), encoding="utf-8")
    return target
