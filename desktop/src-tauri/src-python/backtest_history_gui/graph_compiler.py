"""Validate node graphs and compile them into deterministic Freqtrade strategies."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from importlib import import_module

from .graph_schema import GraphEdge, StrategyGraph
from .nodes import NodeCompileError, node_by_id, node_compile_context
from .nodes.contracts import Parameter, Port


class GraphCompileError(ValueError):
    """Raised when a graph cannot become a deterministic strategy."""


@dataclass(frozen=True)
class GraphParameter:
    """One Hyperopt-compatible parameter declared by a graph node."""

    name: str
    node_id: str
    key: str
    definition: Parameter
    value: int | float | bool | str
    space: str


def topological_nodes(graph: StrategyGraph) -> tuple[str, ...]:
    """Validate catalog node/port types and return a dependency-safe order."""
    nodes = {node.id: node for node in graph.nodes}
    if len(nodes) != len(graph.nodes):
        raise GraphCompileError("Graph node IDs must be unique.")
    dependencies: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        _validate_edge(nodes, edge)
        dependencies[edge.target_node].add(edge.source_node)
    ready = sorted(node_id for node_id in nodes if not dependencies[node_id])
    ordered: list[str] = []
    while ready:
        node_id = ready.pop(0)
        ordered.append(node_id)
        for target, sources in dependencies.items():
            if node_id in sources:
                sources.remove(node_id)
                if not sources and target not in ordered and target not in ready:
                    ready.append(target)
                    ready.sort()
    if len(ordered) != len(nodes):
        raise GraphCompileError("Strategy graphs cannot contain cycles.")
    return tuple(ordered)


def graph_parameters(graph: StrategyGraph) -> tuple[GraphParameter, ...]:
    """Return every optimizable graph parameter with its Freqtrade space."""
    topological_nodes(graph)
    _validate_parameter_relationships(graph)
    parameters: list[GraphParameter] = []
    for node in graph.nodes:
        definition = node_by_id(node.type)
        space = (
            "exit"
            if definition.group == "risk" or node.id.startswith("exit_")
            else "enter"
        )
        if node.type == "input.parameter":
            parameters.append(_declared_input_parameter(node, definition, space))
            continue
        for parameter in definition.parameters:
            if parameter.optimizable:
                parameters.append(
                    GraphParameter(
                        f"{node.id}_{parameter.key}",
                        node.id,
                        parameter.key,
                        parameter,
                        node.parameters.get(parameter.key, parameter.default),
                        space,
                    )
                )
    return tuple(parameters)


def _validate_parameter_relationships(graph: StrategyGraph) -> None:
    for node in graph.nodes:
        if node.type == "indicator.macd":
            fast = node.parameters.get("fast_period")
            slow = node.parameters.get("slow_period")
            if isinstance(fast, int) and isinstance(slow, int) and fast >= slow:
                raise GraphCompileError(
                    f"{node.id} fast_period must be lower than slow_period."
                )
        if node.type == "pattern.fair_value_gap":
            minimum = node.parameters.get("minimum_gap_pct")
            maximum = node.parameters.get("maximum_gap_pct")
            if (
                isinstance(minimum, (int, float))
                and isinstance(maximum, (int, float))
                and minimum >= maximum
            ):
                raise GraphCompileError(
                    f"{node.id} minimum_gap_pct must be lower than maximum_gap_pct."
                )


def _declared_input_parameter(node, definition, space: str) -> GraphParameter:
    """Use an input.parameter node's local bounds for one real Hyperopt value."""
    fields = {parameter.key: parameter for parameter in definition.parameters}
    default = float(node.parameters.get("default", fields["default"].default))
    minimum = float(node.parameters.get("minimum", fields["minimum"].default))
    maximum = float(node.parameters.get("maximum", fields["maximum"].default))
    if minimum > maximum:
        raise GraphCompileError(f"{node.id} minimum cannot exceed maximum.")
    if not minimum <= default <= maximum:
        raise GraphCompileError(f"{node.id} default must be within its Hyperopt range.")
    parameter = replace(
        fields["default"],
        default=default,
        minimum=minimum,
        maximum=maximum,
        optimizable=True,
    )
    return GraphParameter(node.id, node.id, "default", parameter, default, space)


def compile_graph_fragments(
    graph: StrategyGraph,
    parameter_references: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, object]:
    """Compile catalog logic in dependency order with validated graph wiring."""
    order = topological_nodes(graph)
    by_id = {node.id: node for node in graph.nodes}
    incoming: dict[str, dict[str, str]] = defaultdict(dict)
    compiled: dict[str, object] = {}
    imports: set[str] = set()
    statements: dict[str, list[str]] = defaultdict(list)
    for node_id in order:
        node = by_id[node_id]
        try:
            context = node_compile_context(
                node.type,
                node.id,
                inputs=incoming[node_id],
                parameter_values=node.parameters,
                parameter_references=(parameter_references or {}).get(node_id),
            )
            module = import_module(
                _module_name(node.type), package="backtest_history_gui"
            )
            fragment = module.compile_node(context)
        except NodeCompileError as error:
            raise GraphCompileError(str(error)) from error
        compiled[node_id] = fragment
        for edge in graph.edges:
            if edge.source_node == node_id:
                value = fragment.outputs[edge.source_port]
                if node_by_id(by_id[edge.target_node].type).group == "risk":
                    value = _risk_value(value)
                incoming[edge.target_node][edge.target_port] = value
        imports.update(fragment.imports)
        statements[fragment.phase].extend(fragment.statements)
    return {
        "order": order,
        "imports": tuple(sorted(imports)),
        "statements": dict(statements),
        "fragments": compiled,
    }


def compile_freqtrade_graph(
    graph: StrategyGraph,
    class_name: str,
    timeframe: str = "5m",
    entry_tag: str = "graph",
) -> str:
    """Compile one validated node graph into a standalone Freqtrade strategy."""
    parameters = graph_parameters(graph)
    result = compile_graph_fragments(graph, _parameter_references(parameters))
    fragments = result["fragments"]
    nodes = {node.id: node for node in graph.nodes}
    entry = next(
        (
            fragment.outputs["signal"]
            for node_id, fragment in fragments.items()
            if nodes[node_id].type == "signal.enter_long"
        ),
        None,
    )
    if not entry:
        raise GraphCompileError("A graph requires one Enter long signal node.")
    statements = result["statements"]
    indicator_lines = _indent(
        [
            line
            for phase in ("indicators", "conditions", "signals")
            for line in statements.get(phase, [])
        ]
    )
    risk_fragments = [
        (nodes[node_id], fragment)
        for node_id, fragment in fragments.items()
        if fragment.phase == "risk"
    ]
    stop_statements = _indent(
        [
            statement
            for node, fragment in risk_fragments
            if node.type != "risk.time_stop"
            for statement in fragment.statements
        ]
    )
    time_stop_fragment = next(
        (
            fragment
            for node, fragment in risk_fragments
            if node.type == "risk.time_stop"
        ),
        None,
    )
    time_stop = next(
        (
            fragment.outputs["exit"]
            for node, fragment in risk_fragments
            if node.type == "risk.time_stop"
        ),
        None,
    )
    initial_stop = next(
        (
            fragment.outputs["stoploss"]
            for node, fragment in risk_fragments
            if node.type == "risk.initial_stop"
        ),
        "None",
    )
    trailing_stops = [
        fragment.outputs["stoploss"]
        for node, fragment in risk_fragments
        if "stoploss" in fragment.outputs and node.type != "risk.initial_stop"
    ]
    imports = "\n".join(result["imports"])
    declarations = _class_indent([_declaration(parameter) for parameter in parameters])
    seconds = _timeframe_minutes(timeframe) * 60
    custom_exit = "        return None"
    if time_stop:
        custom_exit = (
            f"        trade_age_candles = int((current_time - trade.open_date_utc).total_seconds() // {seconds})\n"
            f"{_indent(list(time_stop_fragment.statements))}\n"
            f'        if {time_stop}:\n            return "max_hold"\n        return None'
        )
    risk_return = f"return next((stop for stop in ({', '.join(trailing_stops) or 'None'},) if stop is not None), {initial_stop})"
    return f'''"""Generated by Backtest Studio from a validated node graph."""
from pandas import DataFrame
from freqtrade.strategy import BooleanParameter, CategoricalParameter, DecimalParameter, IStrategy, IntParameter
{imports}


class {class_name}(IStrategy):
    timeframe = "{timeframe}"
    startup_candle_count = 250
    can_short = False
    stoploss = -0.25
    minimal_roi = {{"0": 0.99}}
    use_exit_signal = True
    use_custom_stoploss = True
    protections = [
        {{"method": "CooldownPeriod", "stop_duration_candles": 5}},
        {{"method": "MaxDrawdown", "lookback_period_candles": 288, "trade_limit": 20, "stop_duration_candles": 48, "max_allowed_drawdown": 0.20}},
    ]

{declarations or "    pass"}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
{indicator_lines or "        pass"}
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[{entry}, ['enter_long', 'enter_tag']] = (1, "{entry_tag}")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
{custom_exit}

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        trade_age_candles = int((current_time - trade.open_date_utc).total_seconds() // {seconds})
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        candle = dataframe.iloc[-1]
{stop_statements or "        pass"}
        {risk_return}
'''


def _module_name(node_type: str) -> str:
    group, name = node_type.split(".", 1)
    package = {
        "input": "inputs",
        "indicator": "indicators",
        "process": "processing",
        "pattern": "processing",
        "filter": "processing",
        "risk": "risk",
        "signal": "signals",
        "logic": "logic",
        "arithmetic": "arithmetic",
        "statistic": "statistics",
    }[group]
    name = {
        "boolean": "boolean_logic",
        "volume": "volume_filter",
        "and": "and_gate",
        "or": "or_gate",
        "not": "not_gate",
    }.get(name, name)
    return f".nodes.{package}.{name}"


def _parameter_references(
    parameters: tuple[GraphParameter, ...],
) -> dict[str, dict[str, str]]:
    references: dict[str, dict[str, str]] = defaultdict(dict)
    for parameter in parameters:
        references[parameter.node_id][parameter.key] = f"self.{parameter.name}.value"
    return dict(references)


def _declaration(parameter: GraphParameter) -> str:
    definition = parameter.definition
    if definition.value_type == "integer":
        return f'{parameter.name} = IntParameter({definition.minimum}, {definition.maximum}, default={parameter.value}, space="{parameter.space}", optimize=True)'
    if definition.value_type == "decimal":
        return f'{parameter.name} = DecimalParameter({definition.minimum}, {definition.maximum}, default={parameter.value}, decimals={definition.decimals}, space="{parameter.space}", optimize=True)'
    if definition.value_type == "boolean":
        return f'{parameter.name} = BooleanParameter(default={parameter.value}, space="{parameter.space}", optimize=True)'
    return f'{parameter.name} = CategoricalParameter({definition.choices!r}, default={parameter.value!r}, space="{parameter.space}", optimize=True)'


def _risk_value(value: str) -> str:
    match = re.fullmatch(r"dataframe\['([^']+)'\]", value)
    return f"candle['{match.group(1)}']" if match else value


def _indent(lines: list[str]) -> str:
    return "\n".join(f"        {line}" for line in lines)


def _class_indent(lines: list[str]) -> str:
    return "\n".join(f"    {line}" for line in lines)


def _timeframe_minutes(timeframe: str) -> int:
    match = re.fullmatch(r"(\d+)([mhd])", timeframe)
    if not match:
        raise GraphCompileError(f"Unsupported timeframe: {timeframe}")
    quantity, unit = int(match.group(1)), match.group(2)
    return quantity * {"m": 1, "h": 60, "d": 1440}[unit]


def _validate_edge(nodes: dict[str, object], edge: GraphEdge) -> None:
    if edge.source_node not in nodes or edge.target_node not in nodes:
        raise GraphCompileError("Graph edges must reference existing nodes.")
    source = node_by_id(nodes[edge.source_node].type)
    target = node_by_id(nodes[edge.target_node].type)
    source_port = next(
        (port for port in source.outputs if port.key == edge.source_port), None
    )
    target_port = _input_port_for(target.inputs, edge.target_port)
    if not source_port or not target_port:
        raise GraphCompileError("Graph edge references an unknown port.")
    if source_port.value_type != target_port.value_type:
        raise GraphCompileError(
            f"Cannot connect {source.id}.{source_port.key} to {target.id}.{target_port.key}."
        )


def _input_port_for(ports: tuple[Port, ...], key: str) -> Port | None:
    return next(
        (
            port
            for port in ports
            if key == port.key
            or (
                port.variadic
                and re.fullmatch(rf"{re.escape(port.key)}_[1-9][0-9]*", key)
            )
        ),
        None,
    )
