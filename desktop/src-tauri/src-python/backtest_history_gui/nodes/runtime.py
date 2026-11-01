"""Runtime contracts used by executable node implementations only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .context import CompiledNode, NodeCompileContext


@dataclass(frozen=True)
class NodeImplementation:
    """One node's executable compiler function and its Freqtrade destination."""

    phase: str
    compile: Callable[[NodeCompileContext], CompiledNode]


def compile_node(
    implementation: NodeImplementation, context: NodeCompileContext
) -> CompiledNode:
    """Run a node-owned implementation through the shared safe context."""
    compiled = implementation.compile(context)
    if compiled.phase != implementation.phase:
        raise ValueError(
            f"Node implementation emitted `{compiled.phase}`, expected `{implementation.phase}`."
        )
    return compiled
