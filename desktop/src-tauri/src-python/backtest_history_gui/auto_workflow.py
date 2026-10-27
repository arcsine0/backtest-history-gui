"""Persistent, bounded AI experiment workflows for strategy snapshots."""

import json
import math
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import AutoTrial, AutoWorkflow, AutoWorkflowRequest, StoredBacktest, StrategyRun, StrategySetup
from .storage import load_backtest, open_database

_stops: dict[str, threading.Event] = {}
_stops_lock = threading.Lock()
ACCEPTABLE_DECLINE = 0.05


def workflow_root(history_root: Path, name: str) -> Path:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-") or "strategy"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return history_root / f"{slug}-{stamp}"


def workflow_for_snapshot(history_root: Path, snapshot_path: Path) -> Path | None:
    """Return the owning auto-run only for a snapshot safely inside history_root."""
    try:
        history = history_root.resolve()
        snapshot = snapshot_path.resolve()
        root = snapshot.parent.parent
    except OSError:
        return None
    if snapshot.parent.name not in {"snapshots", "winning-snapshots"} or root.parent != history or not (root / "backtest_history.sqlite3").is_file():
        return None
    return root


def create_workflow(history_root: Path, request: AutoWorkflowRequest) -> AutoWorkflow:
    root = workflow_root(history_root, request.strategy.name)
    root.mkdir(parents=True, exist_ok=False)
    (root / "snapshots").mkdir()
    connection = open_database(root / "backtest_history.sqlite3")
    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS auto_workflow (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
                prompt_limit INTEGER NOT NULL, target_metrics_json TEXT NOT NULL,
                setup_json TEXT NOT NULL, baseline_json TEXT NOT NULL,
                stop_requested INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS auto_trials (
                number INTEGER PRIMARY KEY, status TEXT NOT NULL, score REAL,
                parameters_json TEXT NOT NULL, metrics_json TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '', snapshot_path TEXT NOT NULL DEFAULT '', backtest_id INTEGER
            );
        """)
        identifier = root.name
        baseline = request.baseline.model_dump() if request.baseline else {}
        connection.execute(
            "INSERT INTO auto_workflow (id, name, status, prompt_limit, target_metrics_json, setup_json, baseline_json) VALUES (?, ?, 'queued', ?, ?, ?, ?)",
            (identifier, request.strategy.name, request.prompt_limit, json.dumps(request.target_metrics), json.dumps(request.strategy.model_dump()), json.dumps(baseline)),
        )
        connection.commit()
    finally:
        connection.close()
    return load_workflow(root)


def resume_workflow(root: Path, request: AutoWorkflowRequest) -> AutoWorkflow:
    """Append a new optimization budget to an existing workflow history."""
    connection = open_database(root / "backtest_history.sqlite3")
    try:
        completed = connection.execute("SELECT COUNT(*) FROM auto_trials").fetchone()[0]
        prompt_limit = completed + request.prompt_limit
        baseline = request.baseline.model_dump() if request.baseline else {}
        connection.execute(
            "UPDATE auto_workflow SET status = 'queued', prompt_limit = ?, target_metrics_json = ?, setup_json = ?, baseline_json = ?, stop_requested = 0",
            (prompt_limit, json.dumps(request.target_metrics), json.dumps(request.strategy.model_dump()), json.dumps(baseline)),
        )
        connection.commit()
    finally:
        connection.close()
    return load_workflow(root)


def _row_to_trial(row: sqlite3.Row) -> AutoTrial:
    return AutoTrial(number=row["number"], status=row["status"], score=row["score"], parameters=json.loads(row["parameters_json"]), metrics=json.loads(row["metrics_json"]), error=row["error"], snapshot_path=row["snapshot_path"], backtest_id=row["backtest_id"])


def load_workflow(root: Path) -> AutoWorkflow:
    connection = open_database(root / "backtest_history.sqlite3")
    try:
        row = connection.execute("SELECT * FROM auto_workflow LIMIT 1").fetchone()
        if row is None:
            raise ValueError("Auto workflow was not found.")
        trials = [_row_to_trial(trial) for trial in connection.execute("SELECT * FROM auto_trials ORDER BY number")]
        best = max((trial for trial in trials if trial.score is not None), key=lambda trial: float(trial.score), default=None)
        best_backtest = load_backtest(connection, best.backtest_id) if best and best.backtest_id else None
        return AutoWorkflow(id=row["id"], name=row["name"], path=str(root), status=row["status"], prompt_limit=row["prompt_limit"], target_metrics=json.loads(row["target_metrics_json"]), completed_trials=len(trials), stop_requested=bool(row["stop_requested"]), best_trial=best, best_backtest=best_backtest, trials=trials)
    finally:
        connection.close()


def list_workflows(history_root: Path) -> list[AutoWorkflow]:
    if not history_root.is_dir():
        return []
    workflows: list[AutoWorkflow] = []
    for database in history_root.glob("*/backtest_history.sqlite3"):
        try:
            workflows.append(load_workflow(database.parent))
        except (sqlite3.Error, ValueError, json.JSONDecodeError):
            continue
    return sorted(workflows, key=lambda workflow: workflow.path, reverse=True)


def request_stop(root: Path) -> AutoWorkflow:
    connection = open_database(root / "backtest_history.sqlite3")
    try:
        connection.execute("UPDATE auto_workflow SET stop_requested = 1")
        connection.commit()
    finally:
        connection.close()
    with _stops_lock:
        _stops.setdefault(str(root), threading.Event()).set()
    return load_workflow(root)


def start_workflow(root: Path, request: AutoWorkflowRequest, run_backtest: Callable[..., StrategyRun]) -> None:
    stop = threading.Event()
    with _stops_lock:
        _stops[str(root)] = stop
    threading.Thread(target=_run_workflow, args=(root, request, run_backtest, stop), daemon=True).start()


def run_backtesting_workflow(root: Path, request: AutoWorkflowRequest, optimize: Callable[..., StrategyRun]) -> AutoWorkflow:
    """Persist every Backtesting.py candidate in the shared workflow history."""
    setup = request.strategy.model_copy(deep=True, update={"id": None})
    baseline = request.baseline.metrics if request.baseline else {}
    _set_status(root, "running")
    try:
        run = optimize(setup, request.prompt_limit, baseline, request.target_metrics, root / "backtest_history.sqlite3", root / "snapshots", request.ohlcv_path)
        if run.error or run.backtest is None:
            _save_trial(root, 1, "failed", None, setup, {}, run.error or "No Backtesting.py result returned.", "")
            _set_status(root, "failed")
            return load_workflow(root)
        candidates = run.optimization_history or [{"parameters": {}, "score": _score(run.backtest.metrics, baseline, request.target_metrics)}]
        first_number = _next_trial_number(root)
        _set_prompt_limit(root, first_number - 1 + len(candidates))
        scores = [_candidate_score(candidate.get("score")) for candidate in candidates]
        best_offset = max((offset for offset, score in enumerate(scores) if score is not None), key=lambda offset: scores[offset], default=len(candidates) - 1)
        for offset, (candidate, score) in enumerate(zip(candidates, scores)):
            number = first_number + offset
            candidate_setup = _candidate_setup(setup, candidate.get("parameters", {}))
            is_best = offset == best_offset
            snapshot_path = run.strategy.strategy_file or "" if is_best else ""
            _save_trial(root, number, "complete", score, run.strategy if is_best else candidate_setup, run.backtest.metrics if is_best else {}, "", snapshot_path, run.backtest.id if is_best else None)
        if request.target_metrics and _goal_met(run.backtest.metrics, baseline, request.target_metrics):
            _copy_winner(root, Path(run.strategy.strategy_file or ""))
            _set_status(root, "goal_met")
        else:
            _set_status(root, "complete")
    except Exception as error:
        _save_trial(root, 1, "failed", None, setup, {}, str(error), "")
        _set_status(root, "failed")
    return load_workflow(root)


def _run_workflow(root: Path, request: AutoWorkflowRequest, run_backtest: Callable[..., StrategyRun], stop: threading.Event) -> None:
    setup = request.strategy.model_copy(deep=True, update={"id": None})
    baseline = request.baseline.metrics if request.baseline else {}
    current_metrics = baseline
    _set_status(root, "running")
    try:
        for number in range(_next_trial_number(root), request.prompt_limit + 1):
            if stop.is_set() or _stop_requested(root):
                _set_status(root, "stopped")
                return
            run = run_backtest(setup, "auto", current_metrics, _workflow_goal(request.target_metrics), "", root / "backtest_history.sqlite3", root / "snapshots")
            if run.error or run.backtest is None:
                _save_trial(root, number, "failed", None, setup, {}, run.error or "No backtest returned.", "")
                continue
            setup = run.strategy
            current_metrics = run.backtest.metrics
            score = _score(current_metrics, baseline, request.target_metrics)
            _save_trial(root, number, "complete", score, setup, current_metrics, "", setup.strategy_file or "", run.backtest.id)
            if request.target_metrics and _goal_met(current_metrics, baseline, request.target_metrics):
                _copy_winner(root, Path(setup.strategy_file or ""))
                _set_status(root, "goal_met")
                return
        _set_status(root, "stopped" if stop.is_set() or _stop_requested(root) else "complete")
    except Exception as error:  # Preserve the persisted trials and make the failure inspectable.
        _set_status(root, "failed", str(error))


def _set_status(root: Path, status: str, error: str = "") -> None:
    connection = open_database(root / "backtest_history.sqlite3")
    try:
        connection.execute("UPDATE auto_workflow SET status = ?", (status,))
        connection.commit()
    finally:
        connection.close()


def _set_prompt_limit(root: Path, prompt_limit: int) -> None:
    connection = open_database(root / "backtest_history.sqlite3")
    try:
        connection.execute("UPDATE auto_workflow SET prompt_limit = ?", (prompt_limit,))
        connection.commit()
    finally:
        connection.close()


def _next_trial_number(root: Path) -> int:
    connection = open_database(root / "backtest_history.sqlite3")
    try:
        return int(connection.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM auto_trials").fetchone()[0])
    finally:
        connection.close()


def _candidate_score(value: object) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return score if math.isfinite(score) else None


def _candidate_setup(setup: StrategySetup, values: dict) -> StrategySetup:
    candidate = setup.model_copy(deep=True)
    candidate.parameters = [parameter.model_copy(update={"value": str(values.get(parameter.name, parameter.value))}) for parameter in candidate.parameters]
    return candidate


def _stop_requested(root: Path) -> bool:
    connection = open_database(root / "backtest_history.sqlite3")
    try:
        return bool(connection.execute("SELECT stop_requested FROM auto_workflow LIMIT 1").fetchone()[0])
    finally:
        connection.close()


def _save_trial(root: Path, number: int, status: str, score: float | None, setup: StrategySetup, metrics: dict, error: str, snapshot_path: str, backtest_id: int | None = None) -> None:
    connection = open_database(root / "backtest_history.sqlite3")
    try:
        connection.execute("INSERT OR REPLACE INTO auto_trials (number, status, score, parameters_json, metrics_json, error, snapshot_path, backtest_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (number, status, score, json.dumps([parameter.model_dump() for parameter in setup.parameters]), json.dumps(metrics), error, snapshot_path, backtest_id))
        connection.commit()
    finally:
        connection.close()


def _metric_value(metrics: dict, name: str) -> float | None:
    value = metrics.get(name)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _improvement(current: float, baseline: float, name: str) -> float:
    if "drawdown" in name.lower():
        delta = abs(baseline) - abs(current)
    else:
        delta = current - baseline
    return delta / max(abs(baseline), 1.0)


def _score(metrics: dict, baseline: dict, targets: list[str]) -> float:
    quality = _quality_metric_names(metrics, baseline)
    target_values = _improvements(metrics, baseline, targets or quality)
    quality_values = _improvements(metrics, baseline, quality)
    regressions = [value for value in quality_values if value < -ACCEPTABLE_DECLINE]
    target_score = sum(target_values) / len(target_values) if target_values else 0.0
    quality_score = sum(quality_values) / len(quality_values) if quality_values else 0.0
    return (target_score * 0.6) + (quality_score * 0.4) + sum(regressions) * 4


def _goal_met(metrics: dict, baseline: dict, targets: list[str]) -> bool:
    target_values = _improvements(metrics, baseline, targets)
    quality_values = _improvements(metrics, baseline, _quality_metric_names(metrics, baseline))
    return bool(target_values) and len(target_values) == len(targets) and all(value > 0 for value in target_values) and all(value >= -ACCEPTABLE_DECLINE for value in quality_values)


def _quality_metric_names(metrics: dict, baseline: dict) -> list[str]:
    ignored = ("trade count", "total trades", "exposure", "holding", "turnover", "fee", "commission")
    return [name for name in baseline if name in metrics and not any(word in name.lower() for word in ignored) and _metric_value(metrics, name) is not None and _metric_value(baseline, name) is not None]


def _improvements(metrics: dict, baseline: dict, names: list[str]) -> list[float]:
    return [_improvement(current, previous, name) for name in names if (current := _metric_value(metrics, name)) is not None and (previous := _metric_value(baseline, name)) is not None]


def _workflow_goal(targets: list[str]) -> str:
    target_text = ", ".join(targets) if targets else "overall risk-adjusted performance"
    return f"Primary improvement targets: {target_text}. Treat all other quality metrics as guardrails: do not let return, P/L, win rate, profit factor, Sharpe, Sortino, or drawdown worsen by more than {ACCEPTABLE_DECLINE:.0%} from the baseline. Reject candidates that improve one target by collapsing equity or overall strategy quality."


def _copy_winner(root: Path, source: Path) -> None:
    if not source.is_file():
        return
    winner_root = root / "winning-snapshots"
    winner_root.mkdir(exist_ok=True)
    target = winner_root / source.name
    target.write_bytes(source.read_bytes())
