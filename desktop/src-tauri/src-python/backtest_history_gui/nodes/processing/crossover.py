from ..contracts import NodeDefinition, bool_output, series_input

NODE = NodeDefinition(
    "pattern.crossover",
    "patterns",
    "Crossover",
    "True only when the left series crosses above the right series on this candle.",
    inputs=(
        series_input("left", "Series crossing upward."),
        series_input("right", "Series crossed through."),
    ),
    outputs=(
        bool_output("crossed_above", "Bullish crossover"),
        bool_output("crossed_below", "Bearish crossover"),
    ),
)


def compile_node(context):
    left, right = context.input("left"), context.input("right")
    context.bind_output(
        "crossed_above", f"({left} > {right}) & ({left}.shift(1) <= {right}.shift(1))"
    )
    context.bind_output(
        "crossed_below", f"({left} < {right}) & ({left}.shift(1) >= {right}.shift(1))"
    )
    return context.finalize()
