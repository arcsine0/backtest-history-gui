from ..contracts import NodeDefinition, bool_input, bool_output, int_param

NODE = NodeDefinition(
    "filter.lookback",
    "processing",
    "Recent condition",
    "Keeps a condition true for a bounded number of completed candles.",
    inputs=(bool_input("condition", "Condition to retain."),),
    outputs=(bool_output("result", "Condition occurred recently"),),
    parameters=(int_param("candles", 3, "Completed candles after the event.", 1, 50),),
)


def compile_node(context):
    context.bind_output(
        "result",
        f"{context.input('condition')}.rolling({context.parameter('candles')}).max().fillna(0).astype(bool)",
    )
    return context.finalize()
