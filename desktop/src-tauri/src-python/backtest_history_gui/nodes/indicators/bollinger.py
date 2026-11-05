from ..contracts import (
    NodeDefinition,
    decimal_param,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    context.require_import("import talib.abstract as ta")
    args = f"{context.input('source')}, timeperiod={context.parameter('period')}, nbdevup={context.parameter('stddev')}, nbdevdn={context.parameter('stddev')}"
    for key, field in (
        ("lower", "lowerband"),
        ("middle", "middleband"),
        ("upper", "upperband"),
    ):
        context.bind_output(key, f"ta.BBANDS({args})['{field}']")
    return context.finalize()


NODE = NodeDefinition(
    "indicator.bollinger",
    "indicators",
    "Bollinger Bands",
    "Rolling mean with configurable standard-deviation bands.",
    inputs=(series_input("source", "Price series.", semantic="price"),),
    outputs=(
        series_output("lower", "Lower band", "price"),
        series_output("middle", "Moving-average band", "price"),
        series_output("upper", "Upper band", "price"),
    ),
    parameters=(
        int_param("period", 20, "Band lookback period.", 5, 100),
        decimal_param("stddev", 2.0, "Band standard deviations.", 0.5, 4.0, 2),
    ),
)
