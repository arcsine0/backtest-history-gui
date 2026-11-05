from ..contracts import NodeDefinition, Parameter, series_output, variadic_series_input

NODE = NodeDefinition(
    "statistic.aggregate",
    "statistics",
    "Aggregate statistics",
    "Calculates an element-wise average, median, or mode across all connected series.",
    inputs=(variadic_series_input("inputs", "Numeric series to aggregate."),),
    outputs=(series_output("value", "Aggregate series."),),
    parameters=(
        Parameter(
            "operation",
            "choice",
            "average",
            "Statistic applied across the connected inputs.",
            choices=("average", "median", "mode"),
            optimizable=False,
        ),
    ),
)


def compile_node(context):
    context.require_import("import pandas as pd")
    values = ", ".join(context.input_values("inputs"))
    frame = f"pd.concat([{values}], axis=1)"
    expressions = {
        "average": f"{frame}.mean(axis=1)",
        "median": f"{frame}.median(axis=1)",
        "mode": f"{frame}.mode(axis=1).iloc[:, 0]",
    }
    context.bind_output("value", expressions[context.parameter_value("operation")])
    return context.finalize()
