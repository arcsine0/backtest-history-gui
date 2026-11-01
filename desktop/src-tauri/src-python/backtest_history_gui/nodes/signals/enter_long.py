from ..contracts import NodeDefinition, Port, bool_input

NODE = NodeDefinition(
    "signal.enter_long",
    "signals",
    "Enter long",
    "Terminal entry node for a validated long condition.",
    inputs=(bool_input("condition", "Entry condition."),),
    outputs=(Port("signal", "signal.entry", True, "Long entry signal"),),
)


def compile_node(context):
    context.bind_output("signal", context.input("condition"))
    return context.finalize()
