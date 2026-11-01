from ..contracts import NodeDefinition, Port

NODE = NodeDefinition(
    "input.trade_state",
    "inputs",
    "Trade state",
    "Per-trade values available only to exit and risk graphs.",
    outputs=(
        Port("trade", "trade", True, "Open trade object"),
        Port("current_profit", "scalar.number", True, "Current profit ratio"),
        Port("open_rate", "scalar.number", True, "Trade entry price"),
        Port("max_rate", "scalar.number", True, "Highest rate since entry"),
        Port("age_candles", "scalar.number", True, "Candles held"),
    ),
)


def compile_node(context):
    context.bind_output("trade", "trade")
    context.bind_output("current_profit", "current_profit")
    context.bind_output("open_rate", "trade.open_rate")
    context.bind_output("max_rate", "trade.max_rate")
    context.bind_output("age_candles", "trade_age_candles")
    return context.finalize()
