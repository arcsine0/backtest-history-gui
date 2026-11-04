"""Structured OpenAI generation for validated Freqtrade node graphs."""

from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .graph_compiler import GraphCompileError, compile_freqtrade_graph, graph_parameters
from .graph_schema import GRAPH_VERSION, GraphEdge, GraphNode, StrategyGraph
from .models import (
    PROJECT_ROOT,
    AiStrategyGraphRequest,
    StrategyParameter,
    StrategySetup,
)
from .nodes import node_by_id, node_catalog
from .storage import cached_openai_api_key

MODEL = "gpt-6-luna"
REASONING_EFFORT = "low"

_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["filename", "graph"],
    "properties": {
        "filename": {
            "type": "string",
            "description": "A short, descriptive strategy label without an extension.",
        },
        "graph": {
            "type": "object",
            "additionalProperties": False,
            "required": ["version", "nodes", "edges"],
            "properties": {
                "version": {"type": "integer"},
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "type", "parameters"],
                        "properties": {
                            "id": {
                                "type": "string",
                                "pattern": "^[a-z][a-z0-9_]*$",
                                "description": "Unique lowercase snake_case node identifier.",
                            },
                            "type": {"type": "string"},
                            "parameters": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["key", "value"],
                                    "properties": {
                                        "key": {"type": "string"},
                                        "value": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                },
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "source_node",
                            "source_port",
                            "target_node",
                            "target_port",
                        ],
                        "properties": {
                            "source_node": {"type": "string"},
                            "source_port": {"type": "string"},
                            "target_node": {"type": "string"},
                            "target_port": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
}


def generate_strategy(request: AiStrategyGraphRequest) -> StrategySetup:
    """Ask OpenAI for a graph envelope, then validate and compile it locally."""
    api_key = _openai_api_key()
    if not api_key:
        raise ValueError(
            "Configure an OpenAI API key in Settings or set OPENAI_API_KEY."
        )
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError("OpenAI SDK is not installed. Reinstall the desktop Python environment.") from error

    response = OpenAI(api_key=api_key).responses.create(
        model=MODEL,
        reasoning={"effort": REASONING_EFFORT},
        store=False,
        input=[
            {"role": "developer", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(request)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "freqtrade_strategy_graph",
                "strict": True,
                "schema": _OUTPUT_SCHEMA,
            }
        },
    )
    if response.status != "completed" or not response.output_text:
        raise RuntimeError("OpenAI did not return a completed strategy graph response.")
    try:
        envelope = json.loads(response.output_text)
    except json.JSONDecodeError as error:
        raise RuntimeError("OpenAI returned unreadable structured strategy data.") from error
    return strategy_from_envelope(envelope, request)


def _load_environment() -> None:
    """Load the ignored project .env without overwriting a real process environment."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path(PROJECT_ROOT) / ".env", override=False)


def _openai_api_key() -> str:
    _load_environment()
    return os.environ.get("OPENAI_API_KEY", "").strip() or cached_openai_api_key().strip()


def openai_api_key_status() -> dict[str, str | bool]:
    """Report configuration only; never expose the local secret to the UI."""
    _load_environment()
    environment_configured = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    cache_configured = bool(cached_openai_api_key().strip())
    return {
        "configured": environment_configured or cache_configured,
        "source": "environment" if environment_configured else "local cache" if cache_configured else "",
        "cache_configured": cache_configured,
        "environment_configured": environment_configured,
    }


def strategy_from_envelope(
    envelope: dict[str, Any], request: AiStrategyGraphRequest
) -> StrategySetup:
    """Normalize a structured response and compile it into a portable setup."""
    filename = envelope.get("filename")
    graph_payload = envelope.get("graph")
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("AI strategy response requires a filename.")
    graph = graph_from_payload(graph_payload)
    name = _strategy_name(filename, request)
    class_name = _class_name(name)
    timeframe = _timeframe(request.timeframes)
    try:
        source = compile_freqtrade_graph(graph, class_name, timeframe, "ai_graph")
    except GraphCompileError as error:
        raise ValueError(f"AI generated an invalid node graph: {error}") from error
    return StrategySetup(
        name=name,
        source=request.prompt.strip(),
        workspace_path=request.workspace_path,
        template_id="ai_graph",
        parameters=[
            StrategyParameter(
                name=parameter.name.upper(),
                value=str(parameter.value),
                notes=parameter.definition.description,
            )
            for parameter in graph_parameters(graph)
        ],
        freqtrade_payload={
            "format": "freqtrade-graph-v1",
            "class_name": class_name,
            "template_id": "ai_graph",
            "entry_id": "ai_graph",
            "exit_id": "ai_graph",
            "graph": graph.as_dict(),
            "strategy_source": source,
            "ai": {
                "model": MODEL,
                "reasoning_effort": REASONING_EFFORT,
                "filename": _file_label(filename),
                "market_context": _market_context(request),
            },
            "anti_overfit": {
                "validation": "Use a held-out timerange before promoting a hyperopt result.",
                "protections": ["cooldown", "max_drawdown"],
                "parameter_spaces": ["enter", "exit"],
            },
        },
    )


def _system_prompt() -> str:
    return "\n".join(
        [
            "You design a long-only Freqtrade strategy as a node graph.",
            "Return only the structured response requested by the API.",
            "Use only node types, ports, and parameter keys in the supplied catalog.",
            "Every node id must be unique lowercase snake_case (for example, ema_fast or entry_signal); never use spaces, hyphens, or uppercase letters.",
            "Every required input must have one compatible incoming edge.",
            "Use input.ohlcv for candle fields, include signal.enter_long, risk.initial_stop, and a dynamic risk exit when suitable.",
            "Do not invent nodes, ports, parameter keys, indicators, or arbitrary Python.",
            "The filename must be a short strategy label only; the application adds market, pair, timeframe, and timestamp.",
            "Node catalog JSON:",
            json.dumps(node_catalog(), separators=(",", ":")),
        ]
    )


def _user_prompt(request: AiStrategyGraphRequest) -> str:
    return "\n".join(
        [
            "Create one strategy graph for this request:",
            request.prompt.strip(),
            "Market context (already chosen by the user; do not ask for it again):",
            json.dumps(_market_context(request), separators=(",", ":")),
        ]
    )


def _market_context(request: AiStrategyGraphRequest) -> dict[str, str]:
    return {
        "exchange": request.exchange.strip(),
        "market_type": request.trading_mode.strip(),
        "pairs": request.pairs.strip(),
        "timeframes": request.timeframes.strip(),
        "timerange": request.timerange.strip(),
    }


def graph_from_payload(payload: Any) -> StrategyGraph:
    if not isinstance(payload, dict) or payload.get("version") != GRAPH_VERSION:
        raise ValueError(f"AI strategy graph must use version {GRAPH_VERSION}.")
    raw_nodes = payload.get("nodes")
    raw_edges = payload.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise ValueError("AI strategy graph requires node and edge lists.")
    nodes = tuple(_graph_node(item) for item in raw_nodes)
    edges = tuple(_graph_edge(item) for item in raw_edges)
    graph = StrategyGraph(nodes=nodes, edges=edges)
    from .graph_compiler import topological_nodes

    topological_nodes(graph)
    return graph


def _graph_node(payload: Any) -> GraphNode:
    if not isinstance(payload, dict):
        raise ValueError("AI graph nodes must be objects.")
    node_id, node_type = payload.get("id"), payload.get("type")
    if not isinstance(node_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", node_id):
        raise ValueError("AI graph node IDs must be lowercase snake case.")
    if not isinstance(node_type, str):
        raise ValueError("AI graph nodes require a type.")
    try:
        definition = node_by_id(node_type)
    except StopIteration as error:
        raise ValueError(f"AI graph uses unknown node type: {node_type}.") from error
    supplied: dict[str, str] = {}
    raw_parameters = payload.get("parameters")
    if isinstance(raw_parameters, dict):
        for key, value in raw_parameters.items():
            if not isinstance(key, str):
                raise ValueError(f"AI graph node {node_id} has an invalid parameter.")
            supplied[key] = _parameter_text(value, node_id)
    elif isinstance(raw_parameters, list):
        for item in raw_parameters:
            if not isinstance(item, dict) or not isinstance(item.get("key"), str) or not isinstance(item.get("value"), str):
                raise ValueError(f"AI graph node {node_id} has an invalid parameter.")
            if item["key"] in supplied:
                raise ValueError(f"AI graph node {node_id} repeats parameter {item['key']}.")
            supplied[item["key"]] = item["value"]
    else:
        raise ValueError(f"AI graph node {node_id} parameters must be a list or object.")
    allowed = {parameter.key for parameter in definition.parameters}
    unknown = set(supplied) - allowed
    if unknown:
        raise ValueError(f"AI graph node {node_id} has unknown parameters: {', '.join(sorted(unknown))}.")
    parameters = {
        parameter.key: _coerce_parameter(supplied.get(parameter.key), parameter)
        for parameter in definition.parameters
    }
    return GraphNode(node_id, node_type, parameters)


def _parameter_text(value: Any, node_id: str) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (str, int, float)):
        return str(value)
    raise ValueError(f"AI graph node {node_id} has an invalid parameter.")


def _graph_edge(payload: Any) -> GraphEdge:
    if not isinstance(payload, dict) or not all(isinstance(payload.get(key), str) for key in ("source_node", "source_port", "target_node", "target_port")):
        raise ValueError("AI graph edges must identify source and target nodes and ports.")
    return GraphEdge(
        payload["source_node"],
        payload["source_port"],
        payload["target_node"],
        payload["target_port"],
    )


def _coerce_parameter(value: str | None, definition) -> int | float | bool | str:
    if value is None:
        return definition.default
    try:
        if definition.value_type == "integer":
            parsed: int | float | bool | str = int(value)
        elif definition.value_type == "decimal":
            parsed = float(value)
        elif definition.value_type == "boolean":
            if value.lower() not in {"true", "false"}:
                raise ValueError
            parsed = value.lower() == "true"
        else:
            parsed = value
    except ValueError as error:
        raise ValueError(f"Parameter {definition.key} has an invalid value.") from error
    if isinstance(parsed, float) and not math.isfinite(parsed):
        raise ValueError(f"Parameter {definition.key} must be finite.")
    if definition.minimum is not None and parsed < definition.minimum:
        raise ValueError(f"Parameter {definition.key} is below its minimum.")
    if definition.maximum is not None and parsed > definition.maximum:
        raise ValueError(f"Parameter {definition.key} exceeds its maximum.")
    if definition.choices and parsed not in definition.choices:
        raise ValueError(f"Parameter {definition.key} is not an allowed choice.")
    return parsed


def _strategy_name(filename: str, request: AiStrategyGraphRequest) -> str:
    market = {"futures": "Futures", "margin": "Margin", "spot": "Spot"}.get(
        request.trading_mode.strip().lower(), "Market"
    )
    pair = next((item.strip() for item in request.pairs.split(",") if item.strip()), "market")
    pair = pair.split(":", maxsplit=1)[0].replace("/", "-")
    return f"{_file_label(filename)}-{market}-{pair}-{_timeframe(request.timeframes)}-{datetime.now():%Y%m%d-%H%M%S}"


def _file_label(value: str) -> str:
    label = re.sub(r"\.[A-Za-z0-9]+$", "", value.strip())
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-")
    return (label or "AIStrategy")[:48]


def _class_name(value: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in re.sub(r"[^A-Za-z0-9]+", " ", value).split()) or "AiStrategy"


def _timeframe(value: str) -> str:
    return next((item.strip() for item in value.split(",") if item.strip()), "5m")
