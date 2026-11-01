from ..contracts import NodeDefinition, Parameter, bool_input, bool_output

NODE = NodeDefinition(
    "process.boolean",
    "processing",
    "Boolean logic",
    "Combines two boolean conditions.",
    inputs=(
        bool_input("left", "Left condition."),
        bool_input("right", "Right condition.", False),
    ),
    outputs=(bool_output("result", "Combined condition"),),
    parameters=(
        Parameter(
            "operation",
            "choice",
            "and",
            "Boolean operation.",
            choices=("and", "or", "xor", "not"),
            optimizable=False,
        ),
    ),
)


def compile_node(context):
    left = context.input("left")
    right = context.inputs.get("right", left)
    operation = context.parameter_value("operation")
    expressions = {
        "and": f"{left} & {right}",
        "or": f"{left} | {right}",
        "xor": f"{left} ^ {right}",
        "not": f"~{left}",
    }
    context.bind_output("result", expressions[operation])
    return context.finalize()
