from ..contracts import NodeDefinition, series_output

NODE = NodeDefinition(
    "input.ohlcv",
    "inputs",
    "OHLCV candles",
    "Market candle fields supplied by Freqtrade.",
    outputs=(
        series_output("open", "Open price", "price"),
        series_output("high", "High price", "price"),
        series_output("low", "Low price", "price"),
        series_output("close", "Close price", "price"),
        series_output("volume", "Base volume", "volume"),
    ),
)


def compile_node(context):
    for field in ("open", "high", "low", "close", "volume"):
        context.bind_output(field, f"dataframe['{field}']")
    return context.finalize()
