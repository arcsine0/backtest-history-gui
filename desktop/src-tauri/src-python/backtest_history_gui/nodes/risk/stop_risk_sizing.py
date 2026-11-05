from ..contracts import NodeDefinition, Port, decimal_param, scalar_input

NODE = NodeDefinition(
    "risk.stop_risk_sizing",
    "risk",
    "Stop-risk sizing",
    "Sizes the initial stake from a fixed loss budget and an initial hard stop.",
    inputs=(scalar_input("stoploss", "Initial hard-stop ratio."),),
    outputs=(Port("stake_multiplier", "scalar.number", True, "Stake multiplier"),),
    parameters=(
        decimal_param(
            "risk_pct",
            0.01,
            "Maximum proposed-stake loss budget at the initial stop.",
            0.0025,
            0.03,
            4,
        ),
        decimal_param(
            "max_stake_fraction",
            0.50,
            "Maximum fraction of the proposed stake allowed by this rule.",
            0.05,
            1.00,
            3,
        ),
    ),
)


def compile_node(context):
    stoploss = context.input("stoploss")
    risk_pct = context.parameter("risk_pct")
    maximum = context.parameter("max_stake_fraction")
    context.bind_output(
        "stake_multiplier",
        f"min({maximum}, {risk_pct} / max(abs({stoploss}), 0.001))",
    )
    return context.finalize()
