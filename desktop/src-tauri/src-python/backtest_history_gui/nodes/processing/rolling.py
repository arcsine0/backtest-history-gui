from ..contracts import (
    NodeDefinition,
    Parameter,
    int_param,
    series_input,
    series_output,
)


def compile_node(context):
    source = context.input("source")
    expression = f"{source}.rolling({context.parameter('period')}).{context.parameter_value('operation')}()"
    context.bind_output("value", expression)
    return context.finalize()


NODE = NodeDefinition(
    "process.rolling",
    "processing",
    "Rolling statistic",
    "Rolling numeric aggregation.",
    inputs=(series_input("source", "Numeric series."),),
    outputs=(series_output("value", "Rolling result"),),
    parameters=(
        int_param("period", 20, "Lookback period.", 2, 1000),
        Parameter(
            "operation",
            "choice",
            "mean",
            "Aggregation operation.",
            choices=("mean", "min", "max", "sum", "stddev"),
            optimizable=False,
        ),
    ),
)
