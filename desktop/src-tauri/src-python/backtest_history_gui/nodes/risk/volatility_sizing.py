from ..contracts import NodeDefinition, Port, decimal_param, series_input

NODE = NodeDefinition(
    "risk.volatility_sizing",
    "risk",
    "Volatility sizing",
    "Reduces the initial stake as ATR volatility rises relative to price.",
    inputs=(
        series_input("atr", "ATR series."),
        series_input("close", "Closing-price series."),
    ),
    outputs=(Port("stake_multiplier", "scalar.number", True, "Stake multiplier"),),
    parameters=(
        decimal_param(
            "target_atr_pct",
            0.01,
            "ATR as a price fraction that receives full size.",
            0.002,
            0.05,
            4,
        ),
        decimal_param(
            "minimum_multiplier",
            0.25,
            "Smallest stake multiplier during high volatility.",
            0.05,
            1.00,
            3,
        ),
        decimal_param(
            "maximum_multiplier",
            1.00,
            "Largest stake multiplier during low volatility.",
            0.25,
            1.00,
            3,
        ),
    ),
)


def compile_node(context):
    context.require_import("from numbers import Real")
    context.require_import("import math")
    atr, close = context.input("atr"), context.input("close")
    target = context.parameter("target_atr_pct")
    minimum = context.parameter("minimum_multiplier")
    maximum = context.parameter("maximum_multiplier")
    context.bind_output(
        "stake_multiplier",
        f"min({maximum}, max({minimum}, {target} / max(abs({atr} / {close}), 0.0001))) if (isinstance({atr}, Real) and isinstance({close}, Real) and math.isfinite({atr}) and math.isfinite({close}) and {close} != 0) else 1.0",
    )
    return context.finalize()
