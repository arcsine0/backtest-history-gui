"""Builder metadata and node-graph backed Freqtrade strategy creation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .graph_compiler import compile_freqtrade_graph, graph_parameters
from .models import StrategyParameter, StrategySetup
from .preset_graphs import strategy_graph


@dataclass(frozen=True)
class Component:
    id: str
    label: str
    file_label: str
    description: str


ENTRIES = (
    Component("fvg", "Fair Value Gap", "FVG", "Three-candle bullish imbalance."),
    Component("fvg_retest", "FVG retest", "FVGRetest", "Bullish gap-zone retest."),
    Component("vwap_pullback", "VWAP pullback", "VWAP", "VWAP reclaim after pullback."),
    Component("ema_cross", "EMA crossover", "EMACross", "EMA trend crossover."),
    Component(
        "rsi_reversion", "RSI mean reversion", "RSIRev", "Oversold RSI recovery."
    ),
    Component("macd_trend", "MACD trend continuation", "MACD", "MACD trend crossover."),
    Component(
        "bollinger_reversion", "Bollinger reversion", "BBRev", "Lower-band reversion."
    ),
    Component(
        "donchian_breakout", "Donchian breakout", "Donchian", "Channel breakout."
    ),
    Component(
        "stochastic_reversal",
        "Stochastic reversal",
        "Stoch",
        "Oversold stochastic crossover.",
    ),
)

EXITS = (
    Component(
        "atr_trailing", "ATR dynamic trail", "ATR", "ATR-activated trailing stop."
    ),
    Component(
        "chandelier", "Chandelier trail", "Chandelier", "Chandelier-style ATR trail."
    ),
    Component(
        "rsi_trailing",
        "RSI activated trail",
        "RSITrail",
        "RSI-activated trailing stop.",
    ),
    Component(
        "profit_trailing",
        "Profit-step trail",
        "ProfitTrail",
        "Profit-activated trailing stop.",
    ),
)

PRESETS = (
    ("fvg_atr", "FVG + ATR trail", "fvg", "atr_trailing"),
    ("fvg_retest_atr", "FVG retest + ATR trail", "fvg_retest", "atr_trailing"),
    ("vwap_atr", "VWAP pullback + ATR trail", "vwap_pullback", "atr_trailing"),
    ("ema_chandelier", "EMA crossover + Chandelier", "ema_cross", "chandelier"),
    (
        "rsi_profit",
        "RSI reversion + Profit-step trail",
        "rsi_reversion",
        "profit_trailing",
    ),
    ("macd_atr", "MACD trend + ATR trail", "macd_trend", "atr_trailing"),
    (
        "bollinger_rsi",
        "Bollinger reversion + RSI trail",
        "bollinger_reversion",
        "rsi_trailing",
    ),
    (
        "donchian_chandelier",
        "Donchian breakout + Chandelier",
        "donchian_breakout",
        "chandelier",
    ),
    (
        "stochastic_profit",
        "Stochastic reversal + Profit-step trail",
        "stochastic_reversal",
        "profit_trailing",
    ),
)


def list_templates() -> list[dict[str, str]]:
    return [
        {"id": preset_id, "label": label, "entry_id": entry_id, "exit_id": exit_id}
        for preset_id, label, entry_id, exit_id in PRESETS
    ]


def list_entries() -> list[dict[str, str]]:
    return [_component_dict(item) for item in ENTRIES]


def list_exits() -> list[dict[str, str]]:
    return [_component_dict(item) for item in EXITS]


def make_template_strategy(
    name: str,
    template_id: str,
    workspace_path: str,
    entry_id: str = "",
    exit_id: str = "",
    trading_mode: str = "futures",
    pairs: str = "",
    timeframes: str = "",
) -> StrategySetup:
    preset = _preset(template_id)
    entry_id, exit_id = entry_id or preset[2], exit_id or preset[3]
    entry, exit_rule = _component(ENTRIES, entry_id), _component(EXITS, exit_id)
    graph = strategy_graph(entry_id, exit_id)
    strategy_name = name.strip() or _generated_name(
        entry, exit_rule, trading_mode, pairs, timeframes
    )
    class_name = _class_name(strategy_name)
    timeframe = _timeframe(timeframes)
    template_id = _matching_preset(entry_id, exit_id) or "custom"
    return StrategySetup(
        name=strategy_name,
        source=f"{entry.description} {exit_rule.description}",
        workspace_path=workspace_path,
        template_id=template_id,
        parameters=[
            StrategyParameter(
                name=parameter.name.upper(),
                value=str(parameter.value),
                notes=parameter.definition.description,
            )
            for parameter in graph_parameters(graph)
        ],
        freqtrade_payload={
            "format": "freqtrade-graph-v1",
            "class_name": class_name,
            "template_id": template_id,
            "entry_id": entry_id,
            "exit_id": exit_id,
            "graph": graph.as_dict(),
            "anti_overfit": {
                "validation": "Use a held-out timerange before promoting a hyperopt result.",
                "protections": ["cooldown", "max_drawdown"],
                "parameter_spaces": ["enter", "exit"],
            },
            "strategy_source": compile_freqtrade_graph(
                graph, class_name, timeframe, entry_id
            ),
        },
    )


def _component_dict(component: Component) -> dict[str, str]:
    return {
        "id": component.id,
        "label": component.label,
        "file_label": component.file_label,
        "description": component.description,
    }


def _preset(template_id: str) -> tuple[str, str, str, str]:
    return next((item for item in PRESETS if item[0] == template_id), PRESETS[0])


def _matching_preset(entry_id: str, exit_id: str) -> str:
    return next((item[0] for item in PRESETS if item[2:] == (entry_id, exit_id)), "")


def _component(items: tuple[Component, ...], component_id: str) -> Component:
    return next(
        (item for item in items if item.id == component_id), None
    ) or _raise_unknown(component_id)


def _raise_unknown(component_id: str) -> Component:
    raise ValueError(f"Unknown strategy component: {component_id}")


def _class_name(name: str) -> str:
    parts = "".join(
        character if character.isalnum() else " " for character in name
    ).split()
    return "".join(part[:1].upper() + part[1:] for part in parts) or "StudioStrategy"


def _timeframe(timeframes: str) -> str:
    return next((item.strip() for item in timeframes.split(",") if item.strip()), "5m")


def _generated_name(
    entry: Component,
    exit_rule: Component,
    trading_mode: str,
    pairs: str,
    timeframes: str,
) -> str:
    pair = next((item.strip() for item in pairs.split(",") if item.strip()), "market")
    pair = pair.split(":", maxsplit=1)[0].replace("/", "-")
    market = {"futures": "Futures", "margin": "Margin", "spot": "Spot"}.get(
        trading_mode.lower(), "Market"
    )
    return f"{entry.file_label}-{exit_rule.file_label}-{market}-{pair}-{_timeframe(timeframes)}-{datetime.now():%Y%m%d-%H%M%S}"
