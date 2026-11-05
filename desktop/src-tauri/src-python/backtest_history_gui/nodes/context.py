"""Shared deterministic context used by future node compiler handlers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .contracts import NodeDefinition, Parameter, Port


class NodeCompileError(ValueError):
    """Raised when a graph node cannot be safely prepared for compilation."""


@dataclass(frozen=True)
class CompiledNode:
    """The source fragments produced by one validated graph node."""

    instance_id: str
    node_id: str
    phase: str
    imports: tuple[str, ...]
    statements: tuple[str, ...]
    outputs: dict[str, str]


@dataclass
class NodeCompileContext:
    """Stable accessors and source collection shared by every node handler.

    The graph compiler owns edge/type validation. A node handler only reads its
    validated inputs and parameters, emits source fragments, and names outputs.
    """

    definition: NodeDefinition
    instance_id: str
    inputs: Mapping[str, str] = field(default_factory=dict)
    parameter_values: Mapping[str, Any] = field(default_factory=dict)
    parameter_references: Mapping[str, str] = field(default_factory=dict)
    _imports: set[str] = field(default_factory=set, init=False, repr=False)
    _statements: list[str] = field(default_factory=list, init=False, repr=False)
    _outputs: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.instance_id):
            raise NodeCompileError(
                "Node instance IDs must use letters, numbers, and underscores."
            )
        _validate_keys("input", self.inputs, self.definition.inputs)
        _validate_keys("parameter", self.parameter_values, self.definition.parameters)
        _validate_keys(
            "parameter reference", self.parameter_references, self.definition.parameters
        )
        for parameter in self.definition.parameters:
            _validate_parameter(parameter, self.parameter_value(parameter.key))
        for port in self.definition.inputs:
            connected = self.input_values(port.key)
            if port.required and len(connected) < port.minimum_connections:
                raise NodeCompileError(
                    f"{self.definition.id} requires at least {port.minimum_connections} connection(s) for input `{port.key}`."
                )

    def input(self, key: str) -> str:
        """Return the validated expression connected to an input port."""
        if key not in {port.key for port in self.definition.inputs}:
            raise NodeCompileError(f"{self.definition.id} has no input `{key}`.")
        try:
            return self.inputs[key]
        except KeyError as error:
            raise NodeCompileError(
                f"{self.definition.id} has no connection for optional input `{key}`."
            ) from error

    def input_values(self, key: str) -> tuple[str, ...]:
        """Return all values connected to a fixed or variadic input port."""
        port = _port_for_key(key, self.definition.inputs)
        if port is None:
            raise NodeCompileError(f"{self.definition.id} has no input `{key}`.")
        if not port.variadic:
            return (self.input(key),) if key in self.inputs else ()
        values = [
            (input_key, value)
            for input_key, value in self.inputs.items()
            if _port_matches(port, input_key)
        ]
        return tuple(
            value
            for _, value in sorted(values, key=lambda item: _port_sort_key(item[0]))
        )

    def parameter_value(self, key: str) -> Any:
        """Return a validated literal parameter value, falling back to its default."""
        parameter = self._parameter(key)
        return self.parameter_values.get(key, parameter.default)

    def parameter(self, key: str) -> str:
        """Return a source expression for a parameter, using Hyperopt refs when supplied."""
        parameter = self._parameter(key)
        if key in self.parameter_references:
            return self.parameter_references[key]
        if parameter.optimizable:
            return f"self.{self.instance_id}_{key}.value"
        return repr(self.parameter_value(key))

    def output(self, key: str) -> str:
        """Return the stable local symbol allocated for an output port."""
        if key not in {port.key for port in self.definition.outputs}:
            raise NodeCompileError(f"{self.definition.id} has no output `{key}`.")
        port = next(port for port in self.definition.outputs if port.key == key)
        if (
            self.definition.group != "risk"
            and self.definition.id != "input.trade_state"
            and port.value_type not in {"scalar.number", "scalar.boolean", "trade"}
        ):
            return self._outputs.setdefault(
                key, f"dataframe['node_{self.instance_id}_{key}']"
            )
        return self._outputs.setdefault(key, f"node_{self.instance_id}_{key}")

    def bind_output(self, key: str, expression: str) -> str:
        """Emit an assignment for an output and return its stable symbol."""
        symbol = self.output(key)
        self.emit(f"{symbol} = {expression}")
        return symbol

    def require_import(self, statement: str) -> None:
        """Register one deterministic import statement needed by this node."""
        self._imports.add(statement)

    def emit(self, statement: str) -> None:
        """Append one already-safe source statement in the node's compiler phase."""
        if not statement.strip():
            raise NodeCompileError("Compiler statements cannot be empty.")
        self._statements.append(statement)

    def finalize(self) -> CompiledNode:
        """Return the accumulated fragments for the graph compiler to place by phase."""
        return CompiledNode(
            instance_id=self.instance_id,
            node_id=self.definition.id,
            phase=_phase_for(self.definition),
            imports=tuple(sorted(self._imports)),
            statements=tuple(self._statements),
            outputs=dict(self._outputs),
        )

    def _parameter(self, key: str) -> Parameter:
        try:
            return next(
                parameter
                for parameter in self.definition.parameters
                if parameter.key == key
            )
        except StopIteration as error:
            raise NodeCompileError(
                f"{self.definition.id} has no parameter `{key}`."
            ) from error


def node_compile_context(
    node_id: str,
    instance_id: str,
    *,
    inputs: Mapping[str, str] | None = None,
    parameter_values: Mapping[str, Any] | None = None,
    parameter_references: Mapping[str, str] | None = None,
) -> NodeCompileContext:
    """Create the common compiler context for any catalog node by stable ID."""
    from .catalog import node_by_id

    try:
        definition = node_by_id(node_id)
    except StopIteration as error:
        raise NodeCompileError(f"Unknown node `{node_id}`.") from error
    return NodeCompileContext(
        definition=definition,
        instance_id=instance_id,
        inputs=inputs or {},
        parameter_values=parameter_values or {},
        parameter_references=parameter_references or {},
    )


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _validate_keys(
    kind: str, supplied: Mapping[str, Any], definitions: tuple[Any, ...]
) -> None:
    unknown = sorted(key for key in supplied if _port_for_key(key, definitions) is None)
    if unknown:
        raise NodeCompileError(
            f"{kind.capitalize()} `{unknown[0]}` is not defined for this node."
        )


def _port_matches(port: Port, key: str) -> bool:
    return key == port.key or (
        getattr(port, "variadic", False)
        and re.fullmatch(rf"{re.escape(port.key)}_[1-9][0-9]*", key) is not None
    )


def _port_for_key(key: str, ports: tuple[Any, ...]) -> Any | None:
    return next((port for port in ports if _port_matches(port, key)), None)


def _port_sort_key(key: str) -> tuple[int, int]:
    match = re.fullmatch(r".+_([1-9][0-9]*)", key)
    return (0, 1) if match is None else (1, int(match.group(1)))


def _validate_parameter(parameter: Parameter, value: Any) -> None:
    if parameter.value_type == "integer" and (
        not isinstance(value, int) or isinstance(value, bool)
    ):
        raise NodeCompileError(f"Parameter `{parameter.key}` must be an integer.")
    if parameter.value_type == "decimal" and (
        not isinstance(value, (int, float)) or isinstance(value, bool)
    ):
        raise NodeCompileError(f"Parameter `{parameter.key}` must be numeric.")
    if parameter.value_type == "boolean" and not isinstance(value, bool):
        raise NodeCompileError(f"Parameter `{parameter.key}` must be boolean.")
    if parameter.value_type == "choice" and value not in parameter.choices:
        raise NodeCompileError(
            f"Parameter `{parameter.key}` must be one of the declared choices."
        )
    if parameter.minimum is not None and value < parameter.minimum:
        raise NodeCompileError(f"Parameter `{parameter.key}` is below its minimum.")
    if parameter.maximum is not None and value > parameter.maximum:
        raise NodeCompileError(f"Parameter `{parameter.key}` is above its maximum.")


def _phase_for(definition: NodeDefinition) -> str:
    if definition.group == "risk" or definition.id == "input.trade_state":
        return "risk"
    if definition.group == "signals":
        return "signals"
    return (
        "indicators"
        if any(port.value_type == "series.number" for port in definition.outputs)
        else "conditions"
    )
