from ..contracts import (
    NodeDefinition,
    bool_output,
    decimal_param,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    high, low, close, period = (
        context.input("high"),
        context.input("low"),
        context.input("close"),
        context.parameter("period"),
    )
    upper, lower = f"{high}.rolling({period}).max()", f"{low}.rolling({period}).min()"
    context.bind_output("upper", upper)
    context.bind_output("lower", lower)
    context.bind_output(
        "is_tight",
        f"(({upper} - {lower}) / {close}.replace(0, float('nan'))) <= {context.parameter('max_width_pct')}",
    )
    return context.finalize()


NODE = NodeDefinition(
    "pattern.range",
    "patterns",
    "Trading range",
    "Rolling high-low range with a width filter.",
    inputs=(
        series_input("high", "Candle high.", semantic="price"),
        series_input("low", "Candle low.", semantic="price"),
        series_input("close", "Candle close.", semantic="price"),
    ),
    outputs=(
        series_output("upper", "Range high", "price"),
        series_output("lower", "Range low", "price"),
        bool_output("is_tight", "Range width is below threshold"),
    ),
    parameters=(
        int_param("period", 20, "Range lookback period.", 5, 100),
        decimal_param(
            "max_width_pct",
            0.03,
            "Maximum high-low width relative to close.",
            0.0001,
            0.10,
        ),
    ),
)
