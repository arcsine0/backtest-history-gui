from ..contracts import NodeDefinition, Port, decimal_param

NODE = NodeDefinition(
    "risk.profit_trailing",
    "risk",
    "Profit trailing stop",
    "Arms after a profit threshold and trails below the highest trade price.",
    inputs=(Port("trade", "trade", True, "Open trade."),),
    outputs=(Port("stoploss", "scalar.number", True, "Dynamic stop loss ratio"),),
    parameters=(
        decimal_param(
            "activation_pct", 0.03, "Profit ratio required to arm.", 0.001, 1.0
        ),
        decimal_param("trail_pct", 0.02, "Distance below trade high.", 0.001, 0.50),
    ),
)


def compile_node(context):
    context.require_import("from freqtrade.strategy import stoploss_from_absolute")
    trade, activation, trail = (
        context.input("trade"),
        context.parameter("activation_pct"),
        context.parameter("trail_pct"),
    )
    context.bind_output(
        "stoploss",
        f"stoploss_from_absolute({trade}.max_rate * (1 - {trail}), current_rate, is_short={trade}.is_short) if current_profit >= {activation} else None",
    )
    return context.finalize()
