from ..contracts import NodeDefinition, bool_output, series_input

NODE = NodeDefinition(
    "process.threshold_zone",
    "processing",
    "Threshold zone",
    "True when a series is between inclusive lower and upper bounds.",
    inputs=(
        series_input("source", "Numeric series."),
        series_input("minimum", "Lower threshold."),
        series_input("maximum", "Upper threshold."),
    ),
    outputs=(bool_output("result", "Inside zone"),),
)


def compile_node(context):
    context.bind_output(
        "result",
        f"({context.input('source')} >= {context.input('minimum')}) & ({context.input('source')} <= {context.input('maximum')})",
    )
    return context.finalize()
