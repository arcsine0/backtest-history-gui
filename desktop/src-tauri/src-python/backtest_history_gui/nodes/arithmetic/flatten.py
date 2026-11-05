from ..contracts import NodeDefinition, series_input, series_output

NODE = NodeDefinition(
    "arithmetic.flatten",
    "arithmetic",
    "Flatten series",
    "Normalizes a numeric source to a one-dimensional, index-aligned pandas series.",
    inputs=(series_input("source", "Numeric series to normalize."),),
    outputs=(series_output("value", "Flattened numeric series."),),
)


def compile_node(context):
    context.require_import("import pandas as pd")
    context.bind_output(
        "value", f"pd.Series({context.input('source')}.to_numpy().ravel(), index=dataframe.index)"
    )
    return context.finalize()
