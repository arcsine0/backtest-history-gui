from ..contracts import NodeDefinition, bool_output, variadic_bool_input

NODE = NodeDefinition(
    "logic.xor",
    "logic",
    "XOR",
    "True when an odd number of connected conditions are true. Connect inputs, inputs_2, inputs_3, and so on.",
    inputs=(variadic_bool_input("inputs", "Conditions to combine."),),
    outputs=(bool_output("result", "Combined condition."),),
)


def compile_node(context):
    values = context.input_values("inputs")
    context.bind_output("result", " ^ ".join(f"({value})" for value in values))
    return context.finalize()
