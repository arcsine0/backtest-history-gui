"""Portable graph contracts for deterministic strategy generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


GRAPH_VERSION = 1


@dataclass(frozen=True)
class GraphNode:
    id: str
    type: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source_node: str
    source_port: str
    target_node: str
    target_port: str


@dataclass(frozen=True)
class StrategyGraph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    version: int = GRAPH_VERSION

    def as_dict(self) -> dict:
        return asdict(self)
