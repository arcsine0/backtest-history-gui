"""Safe local bridge to a user-installed Vibe-Trading CLI."""

import ast
import csv
import json
import re
import shutil
import hashlib
import subprocess
from pathlib import Path

from .models import StrategyParameter, StrategySetup


def snapshot_payload(run_dir: Path) -> dict[str, object]:
    """Portable source material for the local Backtesting.py adapter."""
    config = _load_json(run_dir / "config.json")
    try:
        code = (run_dir / "code" / "signal_engine.py").read_text(encoding="utf-8")
    except OSError:
        return {}
    return {"format": "vibe-signal-engine-v1", "config": config, "signal_engine": code, "sha256": hashlib.sha256(code.encode()).hexdigest()}


def run_prompt(prompt: str) -> str:
    executable = shutil.which("vibe-trading")
    if executable is None:
        raise RuntimeError("Vibe-Trading is not installed or is not on PATH. Install vibe-trading-ai and run vibe-trading init first.")
    result = subprocess.run([executable, "run", "-p", prompt, "--json"], text=True, capture_output=True, timeout=600)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Vibe-Trading failed.")
    return result.stdout.strip()


def backtest_prompt(setup: StrategySetup, run_type: str, metrics: dict[str, object] | None = None, goal: str = "") -> str:
    if not setup.source.strip():
        raise ValueError("Add a strategy prompt before running a backtest.")
    unlocked = [parameter for parameter in setup.parameters if parameter.enabled and not parameter.locked]
    parameter_shape = ", ".join(
        f"{parameter.name}={parameter.value} [{'LOCKED' if parameter.locked else 'OPTIMIZE' if parameter.enabled else 'FIXED'}]"
        for parameter in setup.parameters
    ) or "No existing parameters; identify tunable constants from the strategy."
    if run_type == "optimized" and not unlocked:
        raise ValueError("Select at least one unlocked parameter.")
    entry_requirement = "Treat the Strategy prompt as the source of truth: do not substitute its requested entry model or add an unrelated entry filter unless it is explicitly requested. Define every tunable indicator, entry, exit, stop, and risk value that this strategy actually uses as a UPPER_CASE module-level constant in code/signal_engine.py."
    if run_type == "raw":
        optimisation = f"Use the supplied parameters as-is when they remain relevant. {entry_requirement} Do not add an unsupported generic parameters field to config.json."
    elif run_type == "auto":
        if not metrics:
            raise ValueError("Run a backtest before data-driven optimization.")
        parameters = f"changing only these unlocked parameters: {', '.join(f'{parameter.name}={parameter.value}' for parameter in unlocked)}. Keep all locked and unspecified settings fixed" if unlocked else "first identifying the strategy's tunable constants, then changing only the most relevant ones"
        if goal.strip():
            optimisation = f"Prioritize this goal: {goal.strip()}. Use these displayed prior-backtest metrics as the second priority: {json.dumps(metrics)}. Improve the strategy by {parameters}, run the improved backtest. {entry_requirement}"
        else:
            optimisation = f"Prioritize these displayed prior-backtest metrics: {json.dumps(metrics)}. Improve the strategy by {parameters}, run the improved backtest. {entry_requirement}"
    else:
        context = f"Use these displayed prior-backtest metrics as the second priority: {json.dumps(metrics)}. " if metrics else ""
        optimisation = f"Prioritize optimizing only these unlocked parameters: {', '.join(f'{parameter.name}={parameter.value}' for parameter in unlocked)}. {context}Keep all other settings fixed. {entry_requirement}"
    preservation = "For this new raw strategy run, retain listed parameters only when they are relevant to the Strategy prompt; replace stale entry-model constants with constants for the requested entry." if run_type == "raw" else "Preserve every listed parameter name and value unless it is explicitly marked OPTIMIZE. LOCKED and FIXED parameters must remain present and unchanged in the next code/configuration."
    return f"""Backtest the strategy below. {optimisation}

Current parameter configuration: {parameter_shape}. {preservation}

Complete a real Vibe-Trading backtest before ending the run. The desktop app imports metrics.csv, trades.csv, and equity.csv from the Vibe run directory; do not finish until those artifacts exist. Resolve a bare BTC request as BTC-USDT on Binance, rather than a Yahoo Finance symbol. Return only one JSON object after the backtest completes. It must have this exact top-level shape:
{{
  "parameters": [{{"name":"...","value":"...","notes":"..."}}],
  "metrics": {{"P/L":0,"P/L [%]":0,"Return [%]":0,"Win Rate [%]":0,"Avg. Drawdown [%]":0,"Max. Drawdown [%]":0,"Total Trades":0,"Profit Factor":0,"Sharpe Ratio":0,"Sortino Ratio":0,"SQN":0,"Exposure Time [%]":0}},
  "trades": [{{"EntryTime":"...","ExitTime":"...","EntryPrice":0,"ExitPrice":0,"Size":0,"PnL":0,"ReturnPct":0}}],
  "equity_curve": [0]
}}

Use a numeric equity_curve and avoid lookahead bias. Strategy name: {setup.name}. Workspace: {setup.workspace_path}.

Strategy prompt:
{setup.source}"""


def vibe_run_directory(output: str) -> Path | None:
    try:
        envelope = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(envelope, dict) or envelope.get("status") != "success" or not isinstance(envelope.get("run_dir"), str):
        return None
    return Path(envelope["run_dir"])


def parse_vibe_artifacts(run_dir: Path) -> tuple[dict[str, object], list[StrategyParameter]]:
    artifacts = run_dir / "artifacts"
    metrics_rows = _csv_rows(artifacts / "metrics.csv")
    equity_rows = _csv_rows(artifacts / "equity.csv")
    trades = _csv_rows(artifacts / "trades.csv")
    if not metrics_rows or not equity_rows:
        evidence = _load_json(artifacts / "grounding_evidence.json")
        if evidence.get("identity", {}).get("status") == "ambiguous":
            raise ValueError("Vibe-Trading did not execute a backtest because the market symbol is ambiguous. Specify an exchange and pair, for example BTC-USDT on Binance.")
        raise ValueError("Vibe-Trading completed without metrics.csv and equity.csv artifacts.")

    raw_metrics = metrics_rows[0]
    equity_points = [(float(row["equity"]), row.get("timestamp", "")) for row in equity_rows if row.get("equity")]
    equity = [point[0] for point in equity_points]
    drawdowns = [float(row["drawdown"]) for row in equity_rows if row.get("drawdown")]
    if len(equity) < 2:
        raise ValueError("Vibe-Trading's equity.csv does not contain enough points.")

    def metric(name: str) -> float:
        try:
            return float(raw_metrics.get(name, 0))
        except (TypeError, ValueError):
            return 0

    supplied = {
        "pnl": ("P/L", 1),
        "net_pnl": ("P/L", 1),
        "total_pnl": ("P/L", 1),
        "total_return": ("Return [%]", 100),
        "win_rate": ("Win Rate [%]", 100),
        "avg_drawdown": ("Avg. Drawdown [%]", 100),
        "max_drawdown": ("Max. Drawdown [%]", 100),
        "trade_count": ("Total Trades", 1),
        "profit_factor": ("Profit Factor", 1),
        "sharpe": ("Sharpe Ratio", 1),
        "sortino": ("Sortino Ratio", 1),
    }
    metrics: dict[str, object] = {}
    for raw_name, value in raw_metrics.items():
        mapped = supplied.get(raw_name)
        if mapped is None:
            metrics[raw_name.replace("_", " ").title()] = value
            continue
        try:
            metrics[mapped[0]] = float(value) * mapped[1]
        except (TypeError, ValueError):
            metrics[mapped[0]] = value
    if "P/L" not in metrics:
        metrics["P/L"] = equity[-1] - equity[0]
    if "Avg. Drawdown [%]" not in metrics and drawdowns:
        metrics["Avg. Drawdown [%]"] = sum(drawdowns) / len(drawdowns) * 100
    parameters = _parameters_from_config(run_dir / "config.json")
    sampled_indexes = _sample_indexes(len(equity))
    return {"metrics": metrics, "trades": trades, "equity_curve": [equity[index] for index in sampled_indexes], "equity_timestamps": [equity_points[index][1] for index in sampled_indexes]}, parameters


def _csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _parameters_from_config(path: Path) -> list[StrategyParameter]:
    config = _load_json(path)
    parameters = config.get("parameters", {}) if isinstance(config, dict) else {}
    if isinstance(parameters, dict) and parameters:
        return [StrategyParameter(name=name, value=str(value), notes="Vibe-Trading config parameter") for name, value in parameters.items()]
    return _parameters_from_strategy_code(path.parent / "code" / "signal_engine.py")


def _parameters_from_strategy_code(path: Path) -> list[StrategyParameter]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    parameters: list[StrategyParameter] = []
    keywords = ("atr", "period", "lookback", "multiplier", "threshold", "stop", "risk", "window", "length", "ratio", "fraction", "fvg", "gap", "imbalance", "age")
    for node in tree.body:
        target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else node.target if isinstance(node, ast.AnnAssign) else None
        value = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
        if not isinstance(target, ast.Name) or not any(keyword in target.id.lower() for keyword in keywords):
            continue
        if isinstance(value, ast.Constant) and isinstance(value.value, (str, int, float, bool)):
            parameters.append(StrategyParameter(name=target.id, value=str(value.value), notes="Extracted from Vibe-Trading strategy code"))
    return parameters


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sample_indexes(length: int, limit: int = 2000) -> list[int]:
    if length <= limit:
        return list(range(length))
    # shortcut: retains chart-friendly points only; store full equity data when detailed chart inspection is needed.
    return [round(index * (length - 1) / (limit - 1)) for index in range(limit)]


def parse_backtest_output(output: str) -> tuple[dict[str, object], list[StrategyParameter]]:
    candidates: list[object] = [output]
    seen: set[str] = set()
    while candidates:
        candidate = candidates.pop()
        if isinstance(candidate, str):
            text = candidate.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            if text in seen:
                continue
            seen.add(text)
            try:
                candidates.append(json.loads(text))
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", text, flags=re.DOTALL)
                if match:
                    candidates.append(match.group(0))
            continue
        if isinstance(candidate, dict):
            if isinstance(candidate.get("metrics"), dict) and isinstance(candidate.get("trades"), list):
                parameters = [StrategyParameter.model_validate(item) for item in candidate.get("parameters", [])]
                return candidate, parameters
            candidates.extend(candidate.values())
        elif isinstance(candidate, list):
            candidates.extend(candidate)
    raise ValueError("Vibe-Trading did not return the required backtest JSON.")
