from ..contracts import NodeDefinition, Parameter, series_input, series_output

NODE = NodeDefinition(
    "arithmetic.round",
    "arithmetic",
    "Round",
    "Rounds every value in a numeric series to the selected precision.",
    inputs=(series_input("source", "Numeric series to round."),),
    outputs=(series_output("value", "Rounded series."),),
    parameters=(
        Parameter(
            "decimals",
            "integer",
            2,
            "Decimal places to retain.",
            minimum=0,
            maximum=8,
            optimizable=False,
        ),
    ),
)


def compile_node(context):
    context.bind_output(
        "value", f"{context.input('source')}.round({context.parameter_value('decimals')})"
    )
    return context.finalize()
