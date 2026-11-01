from ..contracts import (
    NodeDefinition,
    bool_output,
    decimal_param,
    int_param,
    series_input,
)


def compile_node(context):
    low, high, close, level, tolerance = (
        context.input("low"),
        context.input("high"),
        context.input("close"),
        context.input("level"),
        context.parameter("tolerance_pct"),
    )
    context.bind_output(
        "bullish", f"({low} <= {level} * (1 + {tolerance})) & ({close} >= {level})"
    )
    context.bind_output(
        "bearish", f"({high} >= {level} * (1 - {tolerance})) & ({close} <= {level})"
    )
    return context.finalize()


NODE = NodeDefinition(
    "pattern.retest",
    "patterns",
    "Level retest",
    "Detects a return to a level followed by a close back through it.",
    inputs=(
        series_input("low", "Candle low."),
        series_input("high", "Candle high."),
        series_input("close", "Candle close."),
        series_input("level", "Level or zone boundary."),
    ),
    outputs=(
        bool_output("bullish", "Bullish level reclaim"),
        bool_output("bearish", "Bearish level rejection"),
    ),
    parameters=(
        decimal_param(
            "tolerance_pct", 0.003, "Allowed distance from the level.", 0.0001, 0.10
        ),
        int_param(
            "validity_candles",
            12,
            "Candles during which the level can be retested.",
            1,
            500,
        ),
    ),
)
