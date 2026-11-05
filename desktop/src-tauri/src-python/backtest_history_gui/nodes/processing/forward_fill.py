from ..contracts import NodeDefinition, int_param, series_input, series_output


def compile_node(context):
    context.bind_output(
        "value",
        f"{context.input('source')}.ffill(limit={context.parameter('limit')})",
    )
    return context.finalize()


NODE = NodeDefinition(
    "process.forward_fill",
    "processing",
    "Forward fill",
    "Carries the last valid value forward for a bounded number of candles.",
    inputs=(series_input("source", "Series with intermittent valid values."),),
    outputs=(series_output("value", "Forward-filled series"),),
    parameters=(int_param("limit", 48, "Maximum candles to retain a value.", 1, 200),),
)
