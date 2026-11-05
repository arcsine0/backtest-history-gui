from ..contracts import NodeDefinition, Port, decimal_param, int_param, scalar_input

NODE = NodeDefinition(
    "risk.scale_in",
    "risk",
    "Scale in",
    "Adds to an open position after a bounded loss threshold is reached.",
    inputs=(
        Port("trade", "trade", True, "Open trade."),
        scalar_input("current_profit", "Current trade profit ratio."),
    ),
    outputs=(
        Port("position_adjustment", "scalar.number", True, "Additional stake"),
    ),
    parameters=(
        decimal_param(
            "trigger_loss_pct",
            0.03,
            "Loss ratio required before another entry is allowed.",
            0.01,
            0.15,
            3,
        ),
        decimal_param(
            "stake_multiplier",
            0.50,
            "Additional stake as a fraction of the original stake.",
            0.10,
            2.00,
            3,
        ),
        int_param("max_additions", 2, "Maximum additional entries.", 1, 3),
    ),
)


def compile_node(context):
    context.require_import("from numbers import Real")
    trade, profit = context.input("trade"), context.input("current_profit")
    trigger = context.parameter("trigger_loss_pct")
    multiplier = context.parameter("stake_multiplier")
    maximum = context.parameter("max_additions")
    context.bind_output(
        "position_adjustment",
        f"min(max_stake, {trade}.stake_amount * {multiplier}) if (isinstance({profit}, Real) and {profit} <= -{trigger} and {trade}.nr_of_successful_entries <= {maximum}) else None",
    )
    return context.finalize()
