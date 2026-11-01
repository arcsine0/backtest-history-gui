from ..contracts import (
    NodeDefinition,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    close, volume, period = (
        context.input("close"),
        context.input("volume"),
        context.parameter("period"),
    )
    context.bind_output(
        "value",
        f"({close} * {volume}).rolling({period}).sum() / {volume}.rolling({period}).sum().replace(0, float('nan'))",
    )
    return context.finalize()


NODE = NodeDefinition(
    "indicator.vwap",
    "indicators",
    "VWAP",
    "Rolling volume-weighted average price.",
    inputs=(
        series_input("high", "Candle high."),
        series_input("low", "Candle low."),
        series_input("close", "Candle close."),
        series_input("volume", "Candle volume."),
    ),
    outputs=(series_output("value", "VWAP"),),
    parameters=(
        int_param(
            "period", 96, "Rolling VWAP lookback; use one session in candles.", 2, 1000
        ),
    ),
)
