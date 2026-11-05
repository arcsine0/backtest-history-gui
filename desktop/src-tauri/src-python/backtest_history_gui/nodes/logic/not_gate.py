from ..contracts import NodeDefinition, bool_input, bool_output

NODE = NodeDefinition(
    "logic.not",
    "logic",
    "NOT",
    "Inverts one boolean condition.",
    inputs=(bool_input("condition", "Condition to invert."),),
    outputs=(bool_output("result", "Inverted condition."),),
)


def compile_node(context):
    context.bind_output("result", f"~({context.input('condition')})")
    return context.finalize()
