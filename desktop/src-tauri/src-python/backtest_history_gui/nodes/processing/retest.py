from ..contracts import (
    NodeDefinition,
    bool_output,
    decimal_param,
    int_param,
    series_input,
)


def compile_node(context):
    low, high, close, level, tolerance, validity = (
        context.input("low"),
        context.input("high"),
        context.input("close"),
        context.input("level"),
        context.parameter("tolerance_pct"),
        context.parameter("validity_candles"),
    )
    bullish_touch = f"({low} <= {level} * (1 + {tolerance}))"
    bearish_touch = f"({high} >= {level} * (1 - {tolerance}))"
    context.bind_output(
        "bullish",
        f"{bullish_touch}.rolling({validity}).max().fillna(0).astype(bool) & ({close} >= {level})",
    )
    context.bind_output(
        "bearish",
        f"{bearish_touch}.rolling({validity}).max().fillna(0).astype(bool) & ({close} <= {level})",
    )
    return context.finalize()


NODE = NodeDefinition(
    "pattern.retest",
    "patterns",
    "Level retest",
    "Detects a return to a level followed by a close back through it.",
    inputs=(
        series_input("low", "Candle low.", semantic="price"),
        series_input("high", "Candle high.", semantic="price"),
        series_input("close", "Candle close.", semantic="price"),
        series_input("level", "Level or zone boundary.", semantic="price"),
    ),
    outputs=(
        bool_output("bullish", "Bullish level reclaim"),
        bool_output("bearish", "Bearish level rejection"),
    ),
    parameters=(
        decimal_param(
            "tolerance_pct", 0.003, "Allowed distance from the level.", 0.0005, 0.02
        ),
        int_param(
            "validity_candles",
            12,
            "Candles during which the level can be retested.",
            1,
            50,
        ),
    ),
)
