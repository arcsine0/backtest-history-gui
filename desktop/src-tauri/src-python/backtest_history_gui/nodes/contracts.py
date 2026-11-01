"""Shared, declarative contracts for every supported strategy-graph node."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

PortType = Literal[
    "series.number",
    "series.boolean",
    "scalar.number",
    "scalar.boolean",
    "trade",
    "signal.entry",
    "signal.exit",
]
ParameterType = Literal["integer", "decimal", "boolean", "choice"]


@dataclass(frozen=True)
class Port:
    key: str
    value_type: PortType
    required: bool = True
    description: str = ""


@dataclass(frozen=True)
class Parameter:
    key: str
    value_type: ParameterType
    default: int | float | bool | str
    description: str
    minimum: int | float | None = None
    maximum: int | float | None = None
    decimals: int | None = None
    choices: tuple[str, ...] = ()
    optimizable: bool = True


@dataclass(frozen=True)
class NodeDefinition:
    id: str
    group: str
    label: str
    description: str
    inputs: tuple[Port, ...] = ()
    outputs: tuple[Port, ...] = ()
    parameters: tuple[Parameter, ...] = ()

    def as_dict(self) -> dict:
        return asdict(self)


def series_input(key: str, description: str, required: bool = True) -> Port:
    return Port(key, "series.number", required, description)


def bool_input(key: str, description: str, required: bool = True) -> Port:
    return Port(key, "series.boolean", required, description)


def scalar_input(key: str, description: str, required: bool = True) -> Port:
    return Port(key, "scalar.number", required, description)


def series_output(key: str, description: str) -> Port:
    return Port(key, "series.number", True, description)


def bool_output(key: str, description: str) -> Port:
    return Port(key, "series.boolean", True, description)


def int_param(
    key: str, default: int, description: str, minimum: int = 1, maximum: int = 500
) -> Parameter:
    return Parameter(key, "integer", default, description, minimum, maximum)


def decimal_param(
    key: str,
    default: float,
    description: str,
    minimum: float,
    maximum: float,
    decimals: int = 4,
) -> Parameter:
    return Parameter(key, "decimal", default, description, minimum, maximum, decimals)
