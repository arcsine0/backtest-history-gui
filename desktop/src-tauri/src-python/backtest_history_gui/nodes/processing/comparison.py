from ..contracts import NodeDefinition, Parameter, bool_output, series_input

NODE = NodeDefinition(
    "process.comparison",
    "processing",
    "Comparison",
    "Element-wise comparison that produces a boolean condition.",
    inputs=(
        series_input("left", "Left operand."),
        series_input("right", "Right operand."),
    ),
    outputs=(bool_output("result", "Comparison result"),),
    parameters=(
        Parameter(
            "operator",
            "choice",
            "greater_than",
            "Comparison operator.",
            choices=(
                "greater_than",
                "greater_or_equal",
                "less_than",
                "less_or_equal",
                "equal",
                "not_equal",
            ),
            optimizable=False,
        ),
    ),
)


def compile_node(context):
    left, right = context.input("left"), context.input("right")
    operators = {
        "greater_than": ">",
        "greater_or_equal": ">=",
        "less_than": "<",
        "less_or_equal": "<=",
        "equal": "==",
        "not_equal": "!=",
    }
    context.bind_output(
        "result", f"{left} {operators[context.parameter_value('operator')]} {right}"
    )
    return context.finalize()
