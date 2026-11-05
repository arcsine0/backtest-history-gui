from ..contracts import NodeDefinition, Port, decimal_param

NODE = NodeDefinition(
    "risk.max_exposure",
    "risk",
    "Maximum position exposure",
    "Caps the initial position at a fraction of Freqtrade's proposed stake.",
    outputs=(Port("exposure_cap", "scalar.number", True, "Maximum stake fraction"),),
    parameters=(
        decimal_param(
            "maximum_fraction",
            0.50,
            "Largest allowed fraction of the proposed stake.",
            0.05,
            1.00,
            3,
        ),
    ),
)


def compile_node(context):
    context.bind_output("exposure_cap", context.parameter("maximum_fraction"))
    return context.finalize()
