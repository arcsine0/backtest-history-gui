from ..contracts import NodeDefinition, Parameter, series_output, variadic_series_input

NODE = NodeDefinition(
    "arithmetic.operations",
    "arithmetic",
    "Arithmetic operations",
    "Applies a left-to-right numeric operation across all connected series.",
    inputs=(variadic_series_input("inputs", "Numeric series to combine."),),
    outputs=(series_output("value", "Calculated series."),),
    parameters=(
        Parameter(
            "operation",
            "choice",
            "add",
            "Operation applied to the connected inputs.",
            choices=("add", "subtract", "multiply", "divide"),
            optimizable=False,
        ),
    ),
)


def compile_node(context):
    values = context.input_values("inputs")
    operation = context.parameter_value("operation")
    symbols = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}
    expression = values[0]
    for value in values[1:]:
        right = f"({value}).replace(0, float('nan'))" if operation == "divide" else value
        expression = f"({expression}) {symbols[operation]} ({right})"
    context.bind_output("value", expression)
    return context.finalize()
