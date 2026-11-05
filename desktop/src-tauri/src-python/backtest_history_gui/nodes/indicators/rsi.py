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
        f"ta.RSI({context.input('source')}, timeperiod={context.parameter('period')})",
    )
    return context.finalize()


NODE = NodeDefinition(
    "indicator.rsi",
    "indicators",
    "RSI",
    "Relative Strength Index.",
    inputs=(series_input("source", "Price series."),),
    outputs=(series_output("value", "RSI from 0 to 100"),),
    parameters=(int_param("period", 14, "RSI lookback period.", 5, 50),),
)
