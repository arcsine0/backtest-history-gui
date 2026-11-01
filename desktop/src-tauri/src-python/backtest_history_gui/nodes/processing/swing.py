from ..contracts import (
    NodeDefinition,
    bool_output,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    high, low, strength = (
        context.input("high"),
        context.input("low"),
        context.parameter("strength"),
    )
    window = f"({strength} * 2 + 1)"
    swing_high = (
        f"{high}.eq({high}.rolling({window}, center=True).max()).shift({strength})"
    )
    swing_low = (
        f"{low}.eq({low}.rolling({window}, center=True).min()).shift({strength})"
    )
    context.bind_output("swing_high", swing_high)
    context.bind_output("swing_low", swing_low)
    context.bind_output("last_swing_high", f"{high}.where({swing_high}).ffill()")
    context.bind_output("last_swing_low", f"{low}.where({swing_low}).ffill()")
    return context.finalize()


NODE = NodeDefinition(
    "pattern.swing",
    "patterns",
    "Swing high / low",
    "Confirmed local swing points using completed candles on both sides.",
    inputs=(series_input("high", "Candle high."), series_input("low", "Candle low.")),
    outputs=(
        bool_output("swing_high", "Confirmed swing high"),
        bool_output("swing_low", "Confirmed swing low"),
        series_output("last_swing_high", "Most recent confirmed swing high"),
        series_output("last_swing_low", "Most recent confirmed swing low"),
    ),
    parameters=(
        int_param("strength", 3, "Completed candles required on each side.", 1, 50),
    ),
)
