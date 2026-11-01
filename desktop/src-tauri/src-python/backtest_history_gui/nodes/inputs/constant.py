from ..contracts import NodeDefinition, decimal_param, series_output

NODE = NodeDefinition(
    "input.constant",
    "inputs",
    "Constant",
    "A scalar value broadcast across every candle.",
    outputs=(series_output("value", "Constant series"),),
    parameters=(
        decimal_param("value", 0.0, "Constant numeric value.", -1_000_000, 1_000_000),
    ),
)


def compile_node(context):
    context.bind_output("value", context.parameter("value"))
    return context.finalize()
