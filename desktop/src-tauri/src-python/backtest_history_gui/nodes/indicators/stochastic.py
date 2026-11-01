from ..contracts import (
    NodeDefinition,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    context.require_import("import talib.abstract as ta")
    args = f"{context.input('high')}, {context.input('low')}, {context.input('close')}, fastk_period={context.parameter('k_period')}, slowk_period={context.parameter('slowing')}, slowd_period={context.parameter('d_period')}"
    context.bind_output("k", f"ta.STOCH({args})['slowk']")
    context.bind_output("d", f"ta.STOCH({args})['slowd']")
    return context.finalize()


NODE = NodeDefinition(
    "indicator.stochastic",
    "indicators",
    "Stochastic",
    "Stochastic oscillator with K and D lines.",
    inputs=(
        series_input("high", "Candle high."),
        series_input("low", "Candle low."),
        series_input("close", "Candle close."),
    ),
    outputs=(series_output("k", "Stochastic K"), series_output("d", "Stochastic D")),
    parameters=(
        int_param("k_period", 14, "K lookback.", 2, 100),
        int_param("d_period", 3, "D smoothing.", 1, 50),
        int_param("slowing", 3, "K slowing.", 1, 50),
    ),
)
