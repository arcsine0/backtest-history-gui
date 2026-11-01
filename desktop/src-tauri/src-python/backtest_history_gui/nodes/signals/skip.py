from ..contracts import NodeDefinition, Port, bool_input

NODE = NodeDefinition(
    "signal.skip",
    "signals",
    "Skip / hold",
    "Blocks a candidate entry or exit signal when its condition is true.",
    inputs=(bool_input("condition", "Blocking condition."),),
    outputs=(Port("block", "series.boolean", True, "Signal block condition"),),
)


def compile_node(context):
    context.bind_output("block", context.input("condition"))
    return context.finalize()
