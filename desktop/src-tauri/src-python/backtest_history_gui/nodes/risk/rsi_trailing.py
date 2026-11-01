from ..contracts import NodeDefinition, Port, decimal_param, int_param, series_input

NODE = NodeDefinition(
    "risk.rsi_trailing",
    "risk",
    "RSI activated trailing stop",
    "Arms after RSI strength and trails below the highest trade price.",
    inputs=(
        Port("trade", "trade", True, "Open trade."),
        series_input("rsi", "Current RSI value."),
    ),
    outputs=(Port("stoploss", "scalar.number", True, "Dynamic stop loss ratio"),),
    parameters=(
        int_param("activation", 68, "RSI required to arm the trail.", 5, 95),
        decimal_param(
            "trail_pct", 0.025, "Distance below the trade high.", 0.001, 0.50
        ),
    ),
)


def compile_node(context):
    context.require_import("from freqtrade.strategy import stoploss_from_absolute")
    trade, rsi = context.input("trade"), context.input("rsi")
    context.bind_output(
        "stoploss",
        f"stoploss_from_absolute({trade}.max_rate * (1 - {context.parameter('trail_pct')}), current_rate, is_short={trade}.is_short) if {rsi} >= {context.parameter('activation')} else None",
    )
    return context.finalize()
