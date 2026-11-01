from ..contracts import NodeDefinition, int_param, series_input, series_output

NODE = NodeDefinition(
    "process.offset",
    "processing",
    "Candle offset",
    "Returns a prior value without using future candles.",
    inputs=(series_input("source", "Numeric series."),),
    outputs=(series_output("value", "Shifted series"),),
    parameters=(
        int_param("candles", 1, "Completed candles to shift backward.", 1, 500),
    ),
)


def compile_node(context):
    context.bind_output(
        "value", f"{context.input('source')}.shift({context.parameter('candles')})"
    )
    return context.finalize()
