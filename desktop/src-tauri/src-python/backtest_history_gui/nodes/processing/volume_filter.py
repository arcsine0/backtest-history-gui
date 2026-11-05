from ..contracts import (
    NodeDefinition,
    bool_output,
    decimal_param,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    volume, period = context.input("volume"), context.parameter("period")
    baseline = f"{volume}.rolling({period}).mean()"
    context.bind_output("baseline", baseline)
    context.bind_output(
        "above_baseline",
        f"{volume} >= ({baseline} * {context.parameter('multiplier')})",
    )
    return context.finalize()


NODE = NodeDefinition(
    "filter.volume",
    "processing",
    "Volume filter",
    "Compares volume against its rolling baseline.",
    inputs=(series_input("volume", "Candle volume.", semantic="volume"),),
    outputs=(
        series_output("baseline", "Rolling volume baseline", "volume"),
        bool_output("above_baseline", "Volume passes threshold"),
    ),
    parameters=(
        int_param("period", 20, "Volume lookback period.", 5, 100),
        decimal_param(
            "multiplier", 1.0, "Required volume relative to baseline.", 0.5, 3.0, 2
        ),
    ),
)
