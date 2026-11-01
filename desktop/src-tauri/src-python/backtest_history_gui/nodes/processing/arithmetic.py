from ..contracts import (
    NodeDefinition,
    Parameter,
    series_input,
    series_output,
)


def compile_node(context):
    left, right = context.input("left"), context.input("right")
    operations = {
        "add": f"{left} + {right}",
        "subtract": f"{left} - {right}",
        "multiply": f"{left} * {right}",
        "divide": f"{left} / {right}.replace(0, float('nan'))",
        "percent_change": f"({left} / {right}.replace(0, float('nan'))) - 1",
    }
    context.bind_output("value", operations[context.parameter_value("operation")])
    return context.finalize()


NODE = NodeDefinition(
    "process.arithmetic",
    "processing",
    "Arithmetic",
    "Element-wise arithmetic between two numeric series.",
    inputs=(
        series_input("left", "Left operand."),
        series_input("right", "Right operand."),
    ),
    outputs=(series_output("value", "Calculated series"),),
    parameters=(
        Parameter(
            "operation",
            "choice",
            "add",
            "Arithmetic operation.",
            choices=("add", "subtract", "multiply", "divide", "percent_change"),
            optimizable=False,
        ),
    ),
)
