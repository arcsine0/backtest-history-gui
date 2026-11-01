from ..context import NodeCompileContext
from ..contracts import NodeDefinition, int_param, series_input, series_output

NODE = NodeDefinition(
    "indicator.ema",
    "indicators",
    "EMA",
    "Exponential moving average.",
    inputs=(series_input("source", "Price or numeric series."),),
    outputs=(series_output("value", "EMA"),),
    parameters=(int_param("period", 100, "EMA lookback period.", 2, 500),),
)


def compile_node(context: NodeCompileContext):
    """Emit the EMA series used by downstream graph nodes."""
    context.require_import("import talib.abstract as ta")
    context.bind_output(
        "value",
        f"ta.EMA({context.input('source')}, timeperiod={context.parameter('period')})",
    )
    return context.finalize()
