from ..contracts import NodeDefinition, Port, int_param

NODE = NodeDefinition(
    "risk.time_stop",
    "risk",
    "Time stop",
    "Forces an exit after a maximum number of held candles.",
    inputs=(Port("trade", "trade", True, "Open trade."),),
    outputs=(Port("exit", "signal.exit", True, "Exit signal when expired"),),
    parameters=(int_param("max_hold_candles", 288, "Maximum held candles.", 1, 10000),),
)


def compile_node(context):
    context.bind_output(
        "exit", f"trade_age_candles >= {context.parameter('max_hold_candles')}"
    )
    return context.finalize()
