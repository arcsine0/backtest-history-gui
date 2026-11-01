from ..contracts import NodeDefinition, Port, bool_input

NODE = NodeDefinition(
    "signal.exit_long",
    "signals",
    "Exit long",
    "Terminal exit node for a validated long exit condition.",
    inputs=(bool_input("condition", "Exit condition."),),
    outputs=(Port("signal", "signal.exit", True, "Long exit signal"),),
)


def compile_node(context):
    context.bind_output("signal", context.input("condition"))
    return context.finalize()
