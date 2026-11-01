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
        f"ta.SMA({context.input('source')}, timeperiod={context.parameter('period')})",
    )
    return context.finalize()


NODE = NodeDefinition(
    "indicator.sma",
    "indicators",
    "SMA",
    "Simple moving average.",
    inputs=(series_input("source", "Price or numeric series."),),
    outputs=(series_output("value", "SMA"),),
    parameters=(int_param("period", 100, "SMA lookback period.", 2, 500),),
)
