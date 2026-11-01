from ..contracts import NodeDefinition, Port, decimal_param, series_input

NODE = NodeDefinition(
    "risk.atr_trailing",
    "risk",
    "ATR trailing stop",
    "Activates after an ATR profit move and trails below the trade high.",
    inputs=(
        Port("trade", "trade", True, "Open trade."),
        series_input("atr", "ATR series."),
    ),
    outputs=(Port("stoploss", "scalar.number", True, "Dynamic stop loss ratio"),),
    parameters=(
        decimal_param(
            "activation_atr",
            1.5,
            "Profit move in ATR units required to arm the trail.",
            0.1,
            10.0,
            2,
        ),
        decimal_param("trail_atr", 2.5, "ATR distance below trade high.", 0.1, 10.0, 2),
    ),
)


def compile_node(context):
    context.require_import("from freqtrade.strategy import stoploss_from_absolute")
    trade, atr = context.input("trade"), context.input("atr")
    activation, trail = (
        context.parameter("activation_atr"),
        context.parameter("trail_atr"),
    )
    context.bind_output(
        "stoploss",
        f"stoploss_from_absolute({trade}.max_rate - ({atr} * {trail}), current_rate, is_short={trade}.is_short) if {trade}.max_rate >= {trade}.open_rate + ({atr} * {activation}) else None",
    )
    return context.finalize()
