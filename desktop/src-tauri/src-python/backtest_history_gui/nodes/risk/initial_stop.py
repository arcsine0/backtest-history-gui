from ..contracts import NodeDefinition, Port, decimal_param

NODE = NodeDefinition(
    "risk.initial_stop",
    "risk",
    "Initial hard stop",
    "Hard loss limit used before other exit logic takes control.",
    inputs=(Port("trade", "trade", True, "Open trade."),),
    outputs=(Port("stoploss", "scalar.number", True, "Stop loss ratio"),),
    parameters=(
        decimal_param(
            "loss_pct",
            0.08,
            "Maximum loss ratio before trailing logic activates.",
            0.005,
            0.25,
        ),
    ),
)


def compile_node(context):
    context.bind_output("stoploss", f"-{context.parameter('loss_pct')}")
    return context.finalize()
