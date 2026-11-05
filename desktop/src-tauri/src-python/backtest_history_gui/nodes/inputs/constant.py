from ..contracts import NodeDefinition, Parameter, series_output

NODE = NodeDefinition(
    "input.constant",
    "inputs",
    "Constant",
    "A scalar value broadcast across every candle.",
    outputs=(series_output("value", "Constant series"),),
    parameters=(
        Parameter(
            "value",
            "decimal",
            0.0,
            "Fixed numeric value. Use an Optimizable parameter node to expose a range.",
            -1_000_000,
            1_000_000,
            optimizable=False,
        ),
    ),
)


def compile_node(context):
    context.bind_output("value", context.parameter("value"))
    return context.finalize()
