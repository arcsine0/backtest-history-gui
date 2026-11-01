from ..contracts import NodeDefinition, series_input, series_output

NODE = NodeDefinition(
    "indicator.obv",
    "indicators",
    "OBV",
    "On-balance volume.",
    inputs=(
        series_input("close", "Candle close."),
        series_input("volume", "Candle volume."),
    ),
    outputs=(series_output("value", "OBV"),),
)


def compile_node(context):
    context.require_import("import talib.abstract as ta")
    context.bind_output(
        "value", f"ta.OBV({context.input('close')}, {context.input('volume')})"
    )
    return context.finalize()
