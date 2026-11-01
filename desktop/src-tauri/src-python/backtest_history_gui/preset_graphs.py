"""Canonical node-graph topologies for Builder presets.

These definitions are intentionally separate from source compilation so every
preset can be reviewed and validated before the legacy adapter is removed.
"""

from __future__ import annotations

from .graph_schema import GraphEdge, GraphNode, StrategyGraph


def ema_chandelier_graph() -> StrategyGraph:
    """EMA-crossover entry topology used by the EMA + Chandelier preset."""
    return StrategyGraph(
        nodes=(
            GraphNode("candles", "input.ohlcv"),
            GraphNode("ema_fast", "indicator.ema", {"period": 12}),
            GraphNode("ema_slow", "indicator.ema", {"period": 48}),
            GraphNode("ema_trend", "indicator.ema", {"period": 150}),
            GraphNode("cross", "pattern.crossover"),
            GraphNode("trend", "process.comparison", {"operator": "greater_than"}),
            GraphNode("entry_condition", "process.boolean", {"operation": "and"}),
            GraphNode("enter", "signal.enter_long"),
        ),
        edges=(
            GraphEdge("candles", "close", "ema_fast", "source"),
            GraphEdge("candles", "close", "ema_slow", "source"),
            GraphEdge("candles", "close", "ema_trend", "source"),
            GraphEdge("ema_fast", "value", "cross", "left"),
            GraphEdge("ema_slow", "value", "cross", "right"),
            GraphEdge("candles", "close", "trend", "left"),
            GraphEdge("ema_trend", "value", "trend", "right"),
            GraphEdge("cross", "crossed_above", "entry_condition", "left"),
            GraphEdge("trend", "result", "entry_condition", "right"),
            GraphEdge("entry_condition", "result", "enter", "condition"),
        ),
    )


def rsi_profit_graph() -> StrategyGraph:
    """RSI mean-reversion entry topology used by the RSI + Profit preset."""
    return StrategyGraph(
        nodes=(
            GraphNode("candles", "input.ohlcv"),
            GraphNode("rsi", "indicator.rsi", {"period": 14}),
            GraphNode("ema", "indicator.ema", {"period": 100}),
            GraphNode("rsi_min", "input.constant", {"value": 15}),
            GraphNode("rsi_max", "input.constant", {"value": 32}),
            GraphNode(
                "above_min", "process.comparison", {"operator": "greater_or_equal"}
            ),
            GraphNode("below_max", "process.comparison", {"operator": "less_or_equal"}),
            GraphNode("above_ema", "process.comparison", {"operator": "greater_than"}),
            GraphNode("rsi_zone", "process.boolean", {"operation": "and"}),
            GraphNode("entry_condition", "process.boolean", {"operation": "and"}),
            GraphNode("enter", "signal.enter_long"),
        ),
        edges=(
            GraphEdge("candles", "close", "rsi", "source"),
            GraphEdge("candles", "close", "ema", "source"),
            GraphEdge("rsi", "value", "above_min", "left"),
            GraphEdge("rsi_min", "value", "above_min", "right"),
            GraphEdge("rsi", "value", "below_max", "left"),
            GraphEdge("rsi_max", "value", "below_max", "right"),
            GraphEdge("candles", "close", "above_ema", "left"),
            GraphEdge("ema", "value", "above_ema", "right"),
            GraphEdge("above_min", "result", "rsi_zone", "left"),
            GraphEdge("below_max", "result", "rsi_zone", "right"),
            GraphEdge("rsi_zone", "result", "entry_condition", "left"),
            GraphEdge("above_ema", "result", "entry_condition", "right"),
            GraphEdge("entry_condition", "result", "enter", "condition"),
        ),
    )


def macd_atr_graph() -> StrategyGraph:
    """MACD crossover + EMA trend entry topology used by the MACD + ATR preset."""
    return StrategyGraph(
        nodes=(
            GraphNode("candles", "input.ohlcv"),
            GraphNode(
                "macd",
                "indicator.macd",
                {"fast_period": 12, "slow_period": 26, "signal_period": 9},
            ),
            GraphNode("ema", "indicator.ema", {"period": 100}),
            GraphNode("cross", "pattern.crossover"),
            GraphNode("trend", "process.comparison", {"operator": "greater_than"}),
            GraphNode("entry_condition", "process.boolean", {"operation": "and"}),
            GraphNode("enter", "signal.enter_long"),
        ),
        edges=(
            GraphEdge("candles", "close", "macd", "source"),
            GraphEdge("candles", "close", "ema", "source"),
            GraphEdge("macd", "line", "cross", "left"),
            GraphEdge("macd", "signal", "cross", "right"),
            GraphEdge("candles", "close", "trend", "left"),
            GraphEdge("ema", "value", "trend", "right"),
            GraphEdge("cross", "crossed_above", "entry_condition", "left"),
            GraphEdge("trend", "result", "entry_condition", "right"),
            GraphEdge("entry_condition", "result", "enter", "condition"),
        ),
    )


def donchian_chandelier_graph() -> StrategyGraph:
    """Donchian breakout + EMA trend entry topology."""
    return StrategyGraph(
        nodes=(
            GraphNode("candles", "input.ohlcv"),
            GraphNode("channel", "indicator.donchian", {"period": 20}),
            GraphNode("ema", "indicator.ema", {"period": 100}),
            GraphNode("breakout", "pattern.breakout", {"buffer_pct": 0.003}),
            GraphNode("trend", "process.comparison", {"operator": "greater_than"}),
            GraphNode("entry_condition", "process.boolean", {"operation": "and"}),
            GraphNode("enter", "signal.enter_long"),
        ),
        edges=(
            GraphEdge("candles", "high", "channel", "high"),
            GraphEdge("candles", "low", "channel", "low"),
            GraphEdge("candles", "close", "ema", "source"),
            GraphEdge("candles", "close", "breakout", "close"),
            GraphEdge("channel", "upper", "breakout", "upper"),
            GraphEdge("channel", "lower", "breakout", "lower"),
            GraphEdge("candles", "close", "trend", "left"),
            GraphEdge("ema", "value", "trend", "right"),
            GraphEdge("breakout", "bullish", "entry_condition", "left"),
            GraphEdge("trend", "result", "entry_condition", "right"),
            GraphEdge("entry_condition", "result", "enter", "condition"),
        ),
    )


def stochastic_profit_graph() -> StrategyGraph:
    """Stochastic K/D bullish crossover in an oversold zone."""
    return StrategyGraph(
        nodes=(
            GraphNode("candles", "input.ohlcv"),
            GraphNode(
                "stoch",
                "indicator.stochastic",
                {"k_period": 14, "d_period": 3, "slowing": 3},
            ),
            GraphNode("cross", "pattern.crossover"),
            GraphNode("minimum", "input.constant", {"value": 5}),
            GraphNode("maximum", "input.constant", {"value": 25}),
            GraphNode("zone", "process.threshold_zone"),
            GraphNode("entry_condition", "process.boolean", {"operation": "and"}),
            GraphNode("enter", "signal.enter_long"),
        ),
        edges=(
            GraphEdge("candles", "high", "stoch", "high"),
            GraphEdge("candles", "low", "stoch", "low"),
            GraphEdge("candles", "close", "stoch", "close"),
            GraphEdge("stoch", "k", "cross", "left"),
            GraphEdge("stoch", "d", "cross", "right"),
            GraphEdge("stoch", "k", "zone", "source"),
            GraphEdge("minimum", "value", "zone", "minimum"),
            GraphEdge("maximum", "value", "zone", "maximum"),
            GraphEdge("cross", "crossed_above", "entry_condition", "left"),
            GraphEdge("zone", "result", "entry_condition", "right"),
            GraphEdge("entry_condition", "result", "enter", "condition"),
        ),
    )


def fvg_retest_atr_graph() -> StrategyGraph:
    """Bullish FVG-zone retest with bounded zone validity and confirmations."""
    return StrategyGraph(
        nodes=(
            GraphNode("candles", "input.ohlcv"),
            GraphNode(
                "fvg",
                "pattern.fair_value_gap",
                {"minimum_gap_pct": 0.002, "maximum_gap_pct": 0.03},
            ),
            GraphNode("lower_offset", "process.offset", {"candles": 1}),
            GraphNode("upper_offset", "process.offset", {"candles": 1}),
            GraphNode("lower", "process.forward_fill", {"limit": 48}),
            GraphNode("upper", "process.forward_fill", {"limit": 48}),
            GraphNode("tolerance", "input.constant", {"value": 1.003}),
            GraphNode(
                "upper_tolerance", "process.arithmetic", {"operation": "multiply"}
            ),
            GraphNode(
                "touches_zone", "process.comparison", {"operator": "less_or_equal"}
            ),
            GraphNode(
                "reclaims_lower", "process.comparison", {"operator": "greater_or_equal"}
            ),
            GraphNode("retest", "process.boolean", {"operation": "and"}),
            GraphNode("ema", "indicator.ema", {"period": 100}),
            GraphNode("rsi", "indicator.rsi", {"period": 14}),
            GraphNode("rsi_max", "input.constant", {"value": 70}),
            GraphNode("trend", "process.comparison", {"operator": "greater_than"}),
            GraphNode(
                "rsi_allowed", "process.comparison", {"operator": "less_or_equal"}
            ),
            GraphNode("retest_trend", "process.boolean", {"operation": "and"}),
            GraphNode("entry_condition", "process.boolean", {"operation": "and"}),
            GraphNode("enter", "signal.enter_long"),
        ),
        edges=(
            GraphEdge("candles", "high", "fvg", "high"),
            GraphEdge("candles", "low", "fvg", "low"),
            GraphEdge("fvg", "bullish_lower", "lower_offset", "source"),
            GraphEdge("fvg", "bullish_upper", "upper_offset", "source"),
            GraphEdge("lower_offset", "value", "lower", "source"),
            GraphEdge("upper_offset", "value", "upper", "source"),
            GraphEdge("upper", "value", "upper_tolerance", "left"),
            GraphEdge("tolerance", "value", "upper_tolerance", "right"),
            GraphEdge("candles", "low", "touches_zone", "left"),
            GraphEdge("upper_tolerance", "value", "touches_zone", "right"),
            GraphEdge("candles", "close", "reclaims_lower", "left"),
            GraphEdge("lower", "value", "reclaims_lower", "right"),
            GraphEdge("touches_zone", "result", "retest", "left"),
            GraphEdge("reclaims_lower", "result", "retest", "right"),
            GraphEdge("candles", "close", "ema", "source"),
            GraphEdge("candles", "close", "rsi", "source"),
            GraphEdge("candles", "close", "trend", "left"),
            GraphEdge("ema", "value", "trend", "right"),
            GraphEdge("rsi", "value", "rsi_allowed", "left"),
            GraphEdge("rsi_max", "value", "rsi_allowed", "right"),
            GraphEdge("retest", "result", "retest_trend", "left"),
            GraphEdge("trend", "result", "retest_trend", "right"),
            GraphEdge("retest_trend", "result", "entry_condition", "left"),
            GraphEdge("rsi_allowed", "result", "entry_condition", "right"),
            GraphEdge("entry_condition", "result", "enter", "condition"),
        ),
    )


def fvg_atr_graph() -> StrategyGraph:
    """Bullish FVG with an EMA trend filter and bounded RSI."""
    return StrategyGraph(
        nodes=(
            GraphNode("candles", "input.ohlcv"),
            GraphNode(
                "fvg",
                "pattern.fair_value_gap",
                {"minimum_gap_pct": 0.002, "maximum_gap_pct": 0.03},
            ),
            GraphNode("ema", "indicator.ema", {"period": 100}),
            GraphNode("rsi", "indicator.rsi", {"period": 14}),
            GraphNode("rsi_max", "input.constant", {"value": 70}),
            GraphNode("trend", "process.comparison", {"operator": "greater_than"}),
            GraphNode(
                "rsi_allowed", "process.comparison", {"operator": "less_or_equal"}
            ),
            GraphNode("trend_fvg", "process.boolean", {"operation": "and"}),
            GraphNode("entry_condition", "process.boolean", {"operation": "and"}),
            GraphNode("enter", "signal.enter_long"),
        ),
        edges=(
            GraphEdge("candles", "high", "fvg", "high"),
            GraphEdge("candles", "low", "fvg", "low"),
            GraphEdge("candles", "close", "ema", "source"),
            GraphEdge("candles", "close", "rsi", "source"),
            GraphEdge("candles", "close", "trend", "left"),
            GraphEdge("ema", "value", "trend", "right"),
            GraphEdge("rsi", "value", "rsi_allowed", "left"),
            GraphEdge("rsi_max", "value", "rsi_allowed", "right"),
            GraphEdge("fvg", "bullish", "trend_fvg", "left"),
            GraphEdge("trend", "result", "trend_fvg", "right"),
            GraphEdge("trend_fvg", "result", "entry_condition", "left"),
            GraphEdge("rsi_allowed", "result", "entry_condition", "right"),
            GraphEdge("entry_condition", "result", "enter", "condition"),
        ),
    )


def vwap_atr_graph() -> StrategyGraph:
    """VWAP reclaim with EMA trend and bounded RSI confirmation."""
    return StrategyGraph(
        nodes=(
            GraphNode("candles", "input.ohlcv"),
            GraphNode("vwap", "indicator.vwap", {"period": 96}),
            GraphNode("ema", "indicator.ema", {"period": 100}),
            GraphNode("rsi", "indicator.rsi", {"period": 14}),
            GraphNode("rsi_min", "input.constant", {"value": 35}),
            GraphNode("rsi_max", "input.constant", {"value": 60}),
            GraphNode("reclaim", "pattern.crossover"),
            GraphNode("trend", "process.comparison", {"operator": "greater_than"}),
            GraphNode("rsi_zone", "process.threshold_zone"),
            GraphNode("reclaim_trend", "process.boolean", {"operation": "and"}),
            GraphNode("entry_condition", "process.boolean", {"operation": "and"}),
            GraphNode("enter", "signal.enter_long"),
        ),
        edges=(
            GraphEdge("candles", "high", "vwap", "high"),
            GraphEdge("candles", "low", "vwap", "low"),
            GraphEdge("candles", "close", "vwap", "close"),
            GraphEdge("candles", "volume", "vwap", "volume"),
            GraphEdge("candles", "close", "ema", "source"),
            GraphEdge("candles", "close", "rsi", "source"),
            GraphEdge("candles", "close", "reclaim", "left"),
            GraphEdge("vwap", "value", "reclaim", "right"),
            GraphEdge("candles", "close", "trend", "left"),
            GraphEdge("ema", "value", "trend", "right"),
            GraphEdge("rsi", "value", "rsi_zone", "source"),
            GraphEdge("rsi_min", "value", "rsi_zone", "minimum"),
            GraphEdge("rsi_max", "value", "rsi_zone", "maximum"),
            GraphEdge("reclaim", "crossed_above", "reclaim_trend", "left"),
            GraphEdge("trend", "result", "reclaim_trend", "right"),
            GraphEdge("reclaim_trend", "result", "entry_condition", "left"),
            GraphEdge("rsi_zone", "result", "entry_condition", "right"),
            GraphEdge("entry_condition", "result", "enter", "condition"),
        ),
    )


def bollinger_rsi_graph() -> StrategyGraph:
    """Lower Bollinger-band reversion with a bounded RSI filter."""
    return StrategyGraph(
        nodes=(
            GraphNode("candles", "input.ohlcv"),
            GraphNode("bands", "indicator.bollinger", {"period": 20, "stddev": 2.0}),
            GraphNode("rsi", "indicator.rsi", {"period": 14}),
            GraphNode("rsi_min", "input.constant", {"value": 15}),
            GraphNode("rsi_max", "input.constant", {"value": 35}),
            GraphNode("reentry_pct", "input.constant", {"value": 1.01}),
            GraphNode(
                "reentry_ceiling", "process.arithmetic", {"operation": "multiply"}
            ),
            GraphNode(
                "near_lower", "process.comparison", {"operator": "less_or_equal"}
            ),
            GraphNode("rsi_zone", "process.threshold_zone"),
            GraphNode("entry_condition", "process.boolean", {"operation": "and"}),
            GraphNode("enter", "signal.enter_long"),
        ),
        edges=(
            GraphEdge("candles", "close", "bands", "source"),
            GraphEdge("candles", "close", "rsi", "source"),
            GraphEdge("bands", "lower", "reentry_ceiling", "left"),
            GraphEdge("reentry_pct", "value", "reentry_ceiling", "right"),
            GraphEdge("candles", "close", "near_lower", "left"),
            GraphEdge("reentry_ceiling", "value", "near_lower", "right"),
            GraphEdge("rsi", "value", "rsi_zone", "source"),
            GraphEdge("rsi_min", "value", "rsi_zone", "minimum"),
            GraphEdge("rsi_max", "value", "rsi_zone", "maximum"),
            GraphEdge("near_lower", "result", "entry_condition", "left"),
            GraphEdge("rsi_zone", "result", "entry_condition", "right"),
            GraphEdge("entry_condition", "result", "enter", "condition"),
        ),
    )


ENTRY_GRAPHS = {
    "fvg": fvg_atr_graph,
    "fvg_retest": fvg_retest_atr_graph,
    "vwap_pullback": vwap_atr_graph,
    "ema_cross": ema_chandelier_graph,
    "rsi_reversion": rsi_profit_graph,
    "macd_trend": macd_atr_graph,
    "bollinger_reversion": bollinger_rsi_graph,
    "donchian_breakout": donchian_chandelier_graph,
    "stochastic_reversal": stochastic_profit_graph,
}


def strategy_graph(entry_id: str, exit_id: str) -> StrategyGraph:
    """Compose the selected entry and exit node graphs into one strategy graph."""
    try:
        graph = ENTRY_GRAPHS[entry_id]()
    except KeyError as error:
        raise ValueError(f"Unknown entry graph: {entry_id}") from error
    return _with_exit_graph(_with_volume_filter(graph), exit_id)


def _with_volume_filter(graph: StrategyGraph) -> StrategyGraph:
    enter = next(node for node in graph.nodes if node.type == "signal.enter_long")
    condition = next(
        edge
        for edge in graph.edges
        if edge.target_node == enter.id and edge.target_port == "condition"
    )
    return StrategyGraph(
        nodes=tuple(node for node in graph.nodes if node.id != enter.id)
        + (
            GraphNode("entry_volume", "filter.volume"),
            GraphNode("entry_gate", "process.boolean", {"operation": "and"}),
            GraphNode(enter.id, enter.type),
        ),
        edges=tuple(edge for edge in graph.edges if edge != condition)
        + (
            GraphEdge(
                condition.source_node, condition.source_port, "entry_gate", "left"
            ),
            GraphEdge("candles", "volume", "entry_volume", "volume"),
            GraphEdge("entry_volume", "above_baseline", "entry_gate", "right"),
            GraphEdge("entry_gate", "result", enter.id, "condition"),
        ),
    )


def _with_exit_graph(graph: StrategyGraph, exit_id: str) -> StrategyGraph:
    nodes = [
        GraphNode("trade_state", "input.trade_state"),
        GraphNode("initial_stop", "risk.initial_stop", {"loss_pct": 0.08}),
        GraphNode("time_stop", "risk.time_stop", {"max_hold_candles": 288}),
    ]
    edges = [
        GraphEdge("trade_state", "trade", "initial_stop", "trade"),
        GraphEdge("trade_state", "trade", "time_stop", "trade"),
    ]
    if exit_id in {"atr_trailing", "chandelier"}:
        period, activation, trail = (
            (14, 1.5, 2.5) if exit_id == "atr_trailing" else (22, 1.0, 3.0)
        )
        nodes.extend(
            (
                GraphNode("exit_atr", "indicator.atr", {"period": period}),
                GraphNode(
                    "exit_trailing",
                    "risk.atr_trailing",
                    {"activation_atr": activation, "trail_atr": trail},
                ),
            )
        )
        edges.extend(
            (
                GraphEdge("candles", "high", "exit_atr", "high"),
                GraphEdge("candles", "low", "exit_atr", "low"),
                GraphEdge("candles", "close", "exit_atr", "close"),
                GraphEdge("trade_state", "trade", "exit_trailing", "trade"),
                GraphEdge("exit_atr", "value", "exit_trailing", "atr"),
            )
        )
    elif exit_id == "profit_trailing":
        nodes.append(GraphNode("exit_trailing", "risk.profit_trailing"))
        edges.append(GraphEdge("trade_state", "trade", "exit_trailing", "trade"))
    elif exit_id == "rsi_trailing":
        nodes.extend(
            (
                GraphNode("exit_rsi", "indicator.rsi", {"period": 14}),
                GraphNode("exit_trailing", "risk.rsi_trailing"),
            )
        )
        edges.extend(
            (
                GraphEdge("candles", "close", "exit_rsi", "source"),
                GraphEdge("trade_state", "trade", "exit_trailing", "trade"),
                GraphEdge("exit_rsi", "value", "exit_trailing", "rsi"),
            )
        )
    else:
        raise ValueError(f"Unknown exit graph: {exit_id}")
    return StrategyGraph(
        nodes=graph.nodes + tuple(nodes), edges=graph.edges + tuple(edges)
    )


PRESET_GRAPHS = {
    "fvg_atr": lambda: strategy_graph("fvg", "atr_trailing"),
    "fvg_retest_atr": lambda: strategy_graph("fvg_retest", "atr_trailing"),
    "vwap_atr": lambda: strategy_graph("vwap_pullback", "atr_trailing"),
    "ema_chandelier": lambda: strategy_graph("ema_cross", "chandelier"),
    "rsi_profit": lambda: strategy_graph("rsi_reversion", "profit_trailing"),
    "macd_atr": lambda: strategy_graph("macd_trend", "atr_trailing"),
    "bollinger_rsi": lambda: strategy_graph("bollinger_reversion", "rsi_trailing"),
    "donchian_chandelier": lambda: strategy_graph("donchian_breakout", "chandelier"),
    "stochastic_profit": lambda: strategy_graph(
        "stochastic_reversal", "profit_trailing"
    ),
}
