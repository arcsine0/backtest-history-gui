from ..contracts import (
    NodeDefinition,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    context.require_import("import talib.abstract as ta")
    source = context.input("source")
    args = f"{source}, fastperiod={context.parameter('fast_period')}, slowperiod={context.parameter('slow_period')}, signalperiod={context.parameter('signal_period')}"
    context.bind_output("line", f"ta.MACD({args})['macd']")
    context.bind_output("signal", f"ta.MACD({args})['macdsignal']")
    context.bind_output("histogram", f"ta.MACD({args})['macdhist']")
    return context.finalize()


NODE = NodeDefinition(
    "indicator.macd",
    "indicators",
    "MACD",
    "Moving Average Convergence Divergence.",
    inputs=(series_input("source", "Price series.", semantic="price"),),
    outputs=(
        series_output("line", "MACD line", "oscillator"),
        series_output("signal", "MACD signal line", "oscillator"),
        series_output("histogram", "MACD histogram", "oscillator"),
    ),
    parameters=(
        int_param("fast_period", 12, "Fast EMA period.", 4, 20),
        int_param("slow_period", 26, "Slow EMA period.", 21, 80),
        int_param("signal_period", 9, "Signal EMA period.", 3, 20),
    ),
)
