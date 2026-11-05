from ..contracts import (
    NodeDefinition,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    context.require_import("import talib.abstract as ta")
    args = f"{context.input('high')}, {context.input('low')}, {context.input('close')}, timeperiod={context.parameter('period')}"
    context.bind_output("adx", f"ta.ADX({args})")
    context.bind_output("plus_di", f"ta.PLUS_DI({args})")
    context.bind_output("minus_di", f"ta.MINUS_DI({args})")
    return context.finalize()


NODE = NodeDefinition(
    "indicator.adx",
    "indicators",
    "ADX",
    "Average Directional Index and directional movement.",
    inputs=(
        series_input("high", "Candle high."),
        series_input("low", "Candle low."),
        series_input("close", "Candle close."),
    ),
    outputs=(
        series_output("adx", "Trend strength"),
        series_output("plus_di", "Positive directional index"),
        series_output("minus_di", "Negative directional index"),
    ),
    parameters=(int_param("period", 14, "ADX lookback period.", 5, 50),),
)
