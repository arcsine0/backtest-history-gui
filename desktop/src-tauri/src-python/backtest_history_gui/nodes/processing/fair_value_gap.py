from ..contracts import (
    NodeDefinition,
    bool_output,
    decimal_param,
    series_input,
    series_output,
)


def compile_node(context):
    high, low = context.input("high"), context.input("low")
    gap = f"({low} / {high}.shift(2)) - 1"
    valid = f"({gap} >= {context.parameter('minimum_gap_pct')}) & ({gap} <= {context.parameter('maximum_gap_pct')})"
    context.bind_output("bullish", valid)
    context.bind_output(
        "bearish",
        f"((-{gap}) >= {context.parameter('minimum_gap_pct')}) & ((-{gap}) <= {context.parameter('maximum_gap_pct')})",
    )
    context.bind_output("bullish_lower", f"{high}.shift(2).where({valid})")
    context.bind_output("bullish_upper", f"{low}.where({valid})")
    context.bind_output("bearish_lower", f"{high}.where(~({valid}))")
    context.bind_output("bearish_upper", f"{low}.shift(2).where(~({valid}))")
    return context.finalize()


NODE = NodeDefinition(
    "pattern.fair_value_gap",
    "patterns",
    "Fair Value Gap",
    "Three-candle imbalance zone.",
    inputs=(series_input("high", "Candle high."), series_input("low", "Candle low.")),
    outputs=(
        bool_output("bullish", "Bullish gap detected"),
        bool_output("bearish", "Bearish gap detected"),
        series_output("bullish_lower", "Bullish gap lower boundary"),
        series_output("bullish_upper", "Bullish gap upper boundary"),
        series_output("bearish_lower", "Bearish gap lower boundary"),
        series_output("bearish_upper", "Bearish gap upper boundary"),
    ),
    parameters=(
        decimal_param(
            "minimum_gap_pct",
            0.002,
            "Minimum gap relative to the older candle.",
            0.0005,
            0.0095,
        ),
        decimal_param("maximum_gap_pct", 0.03, "Maximum accepted gap.", 0.01, 0.05),
    ),
)
