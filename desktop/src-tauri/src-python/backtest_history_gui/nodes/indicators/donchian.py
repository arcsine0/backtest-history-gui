from ..contracts import (
    NodeDefinition,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    high, low, period = (
        context.input("high"),
        context.input("low"),
        context.parameter("period"),
    )
    upper, lower = f"{high}.rolling({period}).max()", f"{low}.rolling({period}).min()"
    context.bind_output("upper", upper)
    context.bind_output("lower", lower)
    context.bind_output("middle", f"({upper} + {lower}) / 2")
    return context.finalize()


NODE = NodeDefinition(
    "indicator.donchian",
    "indicators",
    "Donchian Channel",
    "Rolling highest high and lowest low.",
    inputs=(series_input("high", "Candle high."), series_input("low", "Candle low.")),
    outputs=(
        series_output("upper", "Channel high"),
        series_output("lower", "Channel low"),
        series_output("middle", "Channel midpoint"),
    ),
    parameters=(int_param("period", 20, "Channel lookback period.", 2, 500),),
)
