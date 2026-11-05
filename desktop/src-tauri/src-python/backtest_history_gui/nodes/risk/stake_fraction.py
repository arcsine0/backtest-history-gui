from ..contracts import NodeDefinition, Port, decimal_param

NODE = NodeDefinition(
    "risk.stake_fraction",
    "risk",
    "Initial stake fraction",
    "Uses a bounded fraction of Freqtrade's proposed initial stake.",
    outputs=(Port("stake_multiplier", "scalar.number", True, "Stake multiplier"),),
    parameters=(
        decimal_param(
            "fraction",
            0.10,
            "Fraction of the proposed stake used for the initial entry.",
            0.01,
            0.50,
            3,
        ),
    ),
)


def compile_node(context):
    context.bind_output("stake_multiplier", context.parameter("fraction"))
    return context.finalize()
