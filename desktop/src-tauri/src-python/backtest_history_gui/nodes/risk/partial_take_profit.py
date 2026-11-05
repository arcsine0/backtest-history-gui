from ..contracts import NodeDefinition, Port, decimal_param, scalar_input

NODE = NodeDefinition(
    "risk.partial_take_profit",
    "risk",
    "Partial take profit",
    "Reduces an open position once after a bounded profit threshold is reached.",
    inputs=(
        Port("trade", "trade", True, "Open trade."),
        scalar_input("current_profit", "Current trade profit ratio."),
    ),
    outputs=(
        Port("position_adjustment", "scalar.number", True, "Partial-exit stake"),
    ),
    parameters=(
        decimal_param(
            "trigger_profit_pct",
            0.05,
            "Profit ratio required before the partial exit.",
            0.01,
            0.25,
            3,
        ),
        decimal_param(
            "exit_fraction",
            0.50,
            "Fraction of the original stake to reduce.",
            0.10,
            0.75,
            3,
        ),
    ),
)


def compile_node(context):
    context.require_import("from numbers import Real")
    trade, profit = context.input("trade"), context.input("current_profit")
    trigger = context.parameter("trigger_profit_pct")
    fraction = context.parameter("exit_fraction")
    context.bind_output(
        "position_adjustment",
        f"-({trade}.stake_amount * {fraction}) if (isinstance({profit}, Real) and {profit} >= {trigger} and {trade}.nr_of_successful_exits == 0) else None",
    )
    return context.finalize()
