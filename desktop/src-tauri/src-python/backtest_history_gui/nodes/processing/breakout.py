from ..contracts import NodeDefinition, bool_output, decimal_param, series_input

NODE = NodeDefinition(
    "pattern.breakout",
    "patterns",
    "Breakout",
    "Detects a close through a supplied range boundary.",
    inputs=(
        series_input("close", "Candle close.", semantic="price"),
        series_input("upper", "Resistance boundary.", semantic="price"),
        series_input("lower", "Support boundary.", semantic="price"),
    ),
    outputs=(
        bool_output("bullish", "Upside breakout"),
        bool_output("bearish", "Downside breakdown"),
    ),
    parameters=(
        decimal_param("buffer_pct", 0.001, "Required close-through buffer.", 0.0, 0.02),
    ),
)


def compile_node(context):
    close, upper, lower, buffer = (
        context.input("close"),
        context.input("upper"),
        context.input("lower"),
        context.parameter("buffer_pct"),
    )
    context.bind_output("bullish", f"{close} >= {upper} * (1 + {buffer})")
    context.bind_output("bearish", f"{close} <= {lower} * (1 - {buffer})")
    return context.finalize()
