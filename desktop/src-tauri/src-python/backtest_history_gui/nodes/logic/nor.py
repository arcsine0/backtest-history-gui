from ..contracts import NodeDefinition, bool_output, variadic_bool_input

NODE = NodeDefinition(
    "logic.nor",
    "logic",
    "NOR",
    "True only when every connected condition is false. Connect inputs, inputs_2, inputs_3, and so on.",
    inputs=(variadic_bool_input("inputs", "Conditions to combine."),),
    outputs=(bool_output("result", "Combined condition."),),
)


def compile_node(context):
    values = context.input_values("inputs")
    expression = " | ".join(f"({value})" for value in values)
    context.bind_output("result", f"~({expression})")
    return context.finalize()
