from ..contracts import (
    NodeDefinition,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    context.require_import("import talib.abstract as ta")
    context.bind_output(
        "value",
        f"ta.ATR({context.input('high')}, {context.input('low')}, {context.input('close')}, timeperiod={context.parameter('period')})",
    )
    return context.finalize()


NODE = NodeDefinition(
    "indicator.atr",
    "indicators",
    "ATR",
    "Average True Range.",
    inputs=(
        series_input("high", "Candle high."),
        series_input("low", "Candle low."),
        series_input("close", "Candle close."),
    ),
    outputs=(series_output("value", "ATR"),),
    parameters=(int_param("period", 14, "ATR lookback period.", 5, 50),),
)
