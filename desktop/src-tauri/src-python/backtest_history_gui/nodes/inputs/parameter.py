from ..contracts import NodeDefinition, Parameter, series_output

NODE = NodeDefinition(
    "input.parameter",
    "inputs",
    "Optimizable parameter",
    "A named scalar that becomes a Freqtrade Hyperopt parameter.",
    outputs=(series_output("value", "Parameter series"),),
    parameters=(
        Parameter(
            "name",
            "choice",
            "PARAMETER",
            "Stable parameter identifier supplied by the graph.",
            choices=("PARAMETER",),
            optimizable=False,
        ),
        Parameter(
            "default", "decimal", 1.0, "Default value.", -1_000_000, 1_000_000, 4
        ),
        Parameter(
            "minimum", "decimal", 0.0, "Hyperopt minimum.", -1_000_000, 1_000_000, 4
        ),
        Parameter(
            "maximum", "decimal", 2.0, "Hyperopt maximum.", -1_000_000, 1_000_000, 4
        ),
    ),
)


def compile_node(context):
    """Expose a declared Hyperopt parameter reference to downstream nodes."""
    context.bind_output("value", context.parameter("default"))
    return context.finalize()
