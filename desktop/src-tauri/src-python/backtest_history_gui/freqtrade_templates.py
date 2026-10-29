"""Deterministic Freqtrade entry/exit building blocks.

The UI may compose components, but this module owns every emitted parameter and
strategy line.  This keeps the future AI layer limited to choosing supported
logic rather than inventing an untestable parameter shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import StrategyParameter, StrategySetup


@dataclass(frozen=True)
class Component:
    id: str
    label: str
    description: str
    parameters: tuple[tuple[str, str, str], ...]


ENTRIES = (
    Component("fvg", "Fair Value Gap", "Three-candle bullish imbalance with an EMA regime filter.", (("ENTER_FVG_MIN_GAP_PCT", "0.002", "Minimum three-candle gap percentage."), ("ENTER_FVG_MAX_GAP_PCT", "0.03", "Maximum accepted gap percentage."), ("ENTER_EMA_PERIOD", "100", "Trend EMA period."), ("ENTER_RSI_MAX", "70", "Maximum RSI allowed for a new gap entry."))),
    Component("vwap_pullback", "VWAP pullback", "VWAP reclaim after a pullback, filtered by trend.", (("ENTER_EMA_PERIOD", "100", "Trend EMA period."), ("ENTER_RSI_MIN", "35", "Minimum RSI at entry."), ("ENTER_RSI_MAX", "60", "Maximum RSI at entry."), ("ENTER_VWAP_DISTANCE_PCT", "0.003", "Maximum distance below VWAP accepted for a reclaim."))),
    Component("ema_cross", "EMA crossover", "Fast EMA crossing above slow EMA within a trend regime.", (("ENTER_EMA_FAST", "12", "Fast EMA period."), ("ENTER_EMA_SLOW", "48", "Slow EMA period."), ("ENTER_EMA_TREND", "150", "Long-term trend EMA period."), ("ENTER_CROSS_LOOKBACK", "3", "Candles after a crossover that remain eligible for entry."))),
    Component("rsi_reversion", "RSI mean reversion", "Oversold RSI recovery while price remains above the trend EMA.", (("ENTER_RSI_PERIOD", "14", "RSI calculation period."), ("ENTER_RSI_MIN", "15", "Minimum RSI allowed for entry."), ("ENTER_RSI_MAX", "32", "Maximum RSI allowed for entry."), ("ENTER_EMA_PERIOD", "100", "Trend EMA period."))),
    Component("macd_trend", "MACD trend continuation", "MACD signal crossover aligned with a trend EMA.", (("ENTER_EMA_PERIOD", "100", "Trend EMA period."), ("ENTER_MACD_FAST", "12", "MACD fast period."), ("ENTER_MACD_SLOW", "26", "MACD slow period."), ("ENTER_MACD_SIGNAL", "9", "MACD signal period."), ("ENTER_CROSS_LOOKBACK", "3", "Candles after a MACD crossover that remain eligible for entry."))),
    Component("bollinger_reversion", "Bollinger reversion", "Lower-band mean reversion with RSI confirmation.", (("ENTER_BB_PERIOD", "20", "Bollinger Bands period."), ("ENTER_BB_STDDEV", "2.0", "Bollinger Bands standard deviations."), ("ENTER_RSI_MIN", "15", "Minimum RSI allowed for entry."), ("ENTER_RSI_MAX", "35", "Maximum RSI allowed for entry."), ("ENTER_BB_REENTRY_PCT", "0.01", "Allowed percentage above the lower band."))),
    Component("donchian_breakout", "Donchian breakout", "Breakout above a previous Donchian channel high.", (("ENTER_DONCHIAN_PERIOD", "20", "Donchian lookback period."), ("ENTER_EMA_PERIOD", "100", "Trend EMA period."), ("ENTER_DONCHIAN_BUFFER_PCT", "0.003", "Allowed percentage below the channel high."))),
    Component("stochastic_reversal", "Stochastic reversal", "Stochastic K/D bullish crossover in an oversold zone.", (("ENTER_STOCH_K", "14", "Stochastic lookback."), ("ENTER_STOCH_D", "3", "Stochastic signal smoothing."), ("ENTER_STOCH_MIN", "5", "Minimum stochastic K allowed for entry."), ("ENTER_STOCH_MAX", "25", "Maximum stochastic K allowed for entry."), ("ENTER_CROSS_LOOKBACK", "3", "Candles after a stochastic crossover that remain eligible for entry."))),
)

EXITS = (
    Component("atr_trailing", "ATR dynamic trail", "Activates after an ATR profit move and trails from the high by ATR.", (("EXIT_ATR_PERIOD", "14", "ATR calculation period."), ("EXIT_ATR_ACTIVATION", "1.5", "ATR profit move required to activate."), ("EXIT_ATR_TRAIL", "2.5", "ATR distance behind the high after activation."), ("EXIT_INITIAL_STOP_PCT", "0.08", "Maximum loss before the trail activates."))),
    Component("chandelier", "Chandelier trail", "Chandelier-style ATR trail from the trade high with an activation threshold.", (("EXIT_ATR_PERIOD", "22", "ATR calculation period."), ("EXIT_CHANDELIER_ACTIVATION", "1.0", "ATR profit move required to activate."), ("EXIT_CHANDELIER_TRAIL", "3.0", "ATR distance behind the high."), ("EXIT_INITIAL_STOP_PCT", "0.08", "Maximum loss before the trail activates."))),
    Component("rsi_trailing", "RSI activated trail", "Activates after RSI strength, then trails price by a percentage.", (("EXIT_RSI_ACTIVATION", "68", "RSI threshold that arms the trail."), ("EXIT_RSI_TRAIL_PCT", "0.025", "Percentage distance below the high after activation."), ("EXIT_INITIAL_STOP_PCT", "0.08", "Maximum loss before the trail activates."))),
    Component("profit_trailing", "Profit-step trail", "Activates at a profit threshold, then trails from the trade high.", (("EXIT_PROFIT_ACTIVATION", "0.03", "Profit percentage that arms the trail."), ("EXIT_PROFIT_TRAIL_PCT", "0.02", "Percentage distance below the high after activation."), ("EXIT_INITIAL_STOP_PCT", "0.08", "Maximum loss before the trail activates."))),
)

COMMON_ENTRY_PARAMETERS = (
    ("ENTER_VOLUME_LOOKBACK", "20", "Rolling volume baseline used to filter illiquid signals."),
    ("ENTER_VOLUME_MULTIPLIER", "1.0", "Volume required relative to its rolling baseline."),
)

PRESETS = (
    ("fvg_atr", "FVG + ATR trail", "fvg", "atr_trailing"),
    ("vwap_atr", "VWAP pullback + ATR trail", "vwap_pullback", "atr_trailing"),
    ("ema_chandelier", "EMA crossover + Chandelier", "ema_cross", "chandelier"),
    ("rsi_profit", "RSI reversion + Profit-step trail", "rsi_reversion", "profit_trailing"),
    ("macd_atr", "MACD trend + ATR trail", "macd_trend", "atr_trailing"),
    ("bollinger_rsi", "Bollinger reversion + RSI trail", "bollinger_reversion", "rsi_trailing"),
    ("donchian_chandelier", "Donchian breakout + Chandelier", "donchian_breakout", "chandelier"),
    ("stochastic_profit", "Stochastic reversal + Profit-step trail", "stochastic_reversal", "profit_trailing"),
)


def list_templates() -> list[dict[str, str]]:
    return [{"id": preset_id, "label": label, "entry_id": entry_id, "exit_id": exit_id} for preset_id, label, entry_id, exit_id in PRESETS]


def list_entries() -> list[dict[str, str]]:
    return [{"id": item.id, "label": item.label, "description": item.description} for item in ENTRIES]


def list_exits() -> list[dict[str, str]]:
    return [{"id": item.id, "label": item.label, "description": item.description} for item in EXITS]


def make_template_strategy(name: str, template_id: str, workspace_path: str, entry_id: str = "", exit_id: str = "") -> StrategySetup:
    preset = _preset(template_id)
    entry_id = entry_id or preset[2]
    exit_id = exit_id or preset[3]
    entry, exit_rule = _component(ENTRIES, entry_id), _component(EXITS, exit_id)
    parameters = _parameters(entry, exit_rule)
    class_name = _class_name(name)
    return StrategySetup(
        name=name.strip() or f"{entry.label} {exit_rule.label}",
        source=f"{entry.description} {exit_rule.description}",
        workspace_path=workspace_path,
        template_id=_matching_preset(entry_id, exit_id) or "custom",
        parameters=parameters,
        freqtrade_payload={
            "format": "freqtrade-strategy-v2",
            "class_name": class_name,
            "template_id": _matching_preset(entry_id, exit_id) or "custom",
            "entry_id": entry_id,
            "exit_id": exit_id,
            "anti_overfit": {"validation": "Use a held-out timerange before promoting a hyperopt result.", "protections": ["cooldown", "max_drawdown"], "parameter_spaces": ["enter", "exit"]},
            "strategy_source": render_strategy(class_name, entry_id, exit_id),
        },
    )


def render_strategy(class_name: str, entry_id: str, exit_id: str) -> str:
    entry, exit_rule = _component(ENTRIES, entry_id), _component(EXITS, exit_id)
    declarations = "\n".join(_declaration(name, value) for name, value, _ in (*COMMON_ENTRY_PARAMETERS, *entry.parameters, *exit_rule.parameters))
    indicator_lines, condition = _entry_logic(entry_id)
    indicator_lines += _exit_indicators(exit_id)
    exit_logic = _exit_logic(exit_id)
    return f'''"""Generated by Backtest Studio. Safe to copy into user_data/strategies."""
from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, stoploss_from_absolute


class {class_name}(IStrategy):
    timeframe = "5m"
    startup_candle_count = 250
    can_short = False
    stoploss = -0.15
    minimal_roi = {{"0": 0.99}}
    use_exit_signal = True
    use_custom_stoploss = True
    protections = [
        {{"method": "CooldownPeriod", "stop_duration_candles": 5}},
        {{"method": "MaxDrawdown", "lookback_period_candles": 288, "trade_limit": 20, "stop_duration_candles": 48, "max_allowed_drawdown": 0.20}},
    ]

{declarations}

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['volume_mean'] = dataframe['volume'].rolling(self.enter_volume_lookback.value).mean()
{indicator_lines}
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        condition = ({condition}) & (dataframe['volume'] >= dataframe['volume_mean'] * self.enter_volume_multiplier.value)
        dataframe.loc[condition, ['enter_long', 'enter_tag']] = (1, "{entry_id}")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return None
        candle = dataframe.iloc[-1]
{exit_logic}
'''


def _parameters(entry: Component, exit_rule: Component) -> list[StrategyParameter]:
    return [StrategyParameter(name=name, value=value, notes=notes) for name, value, notes in (*COMMON_ENTRY_PARAMETERS, *entry.parameters, *exit_rule.parameters)]


def _declaration(name: str, value: str) -> str:
    key = name.lower()
    if "PCT" in name or "ACTIVATION" in name or "TRAIL" in name or "STDDEV" in name or "GAP" in name or "MULTIPLIER" in name or "BUFFER" in name:
        low, high, decimals = (0.0001, 0.20, 4) if "PCT" in name or "GAP" in name or "BUFFER" in name else (0.1, 6.0, 1)
        if "ACTIVATION" in name and "RSI" not in name: low, high, decimals = 0.5, 6.0, 1
        if "RSI" in name: low, high, decimals = 55, 90, 0
        kind = "IntParameter" if decimals == 0 else "DecimalParameter"
        space = "exit" if name.startswith("EXIT") else "enter"
        return f'    {key} = {kind}({low}, {high}, default={value}, decimals={decimals}, space="{space}", optimize=True)'
    if "RSI" in name or "STOCH" in name:
        return f'    {key} = IntParameter(5, 90, default={value}, space="enter", optimize=True)'
    if "MACD" in name or "EMA" in name or "PERIOD" in name or "DONCHIAN" in name or "LOOKBACK" in name:
        space = "exit" if name.startswith("EXIT") else "enter"
        return f'    {key} = IntParameter(3, 250, default={value}, space="{space}", optimize=True)'
    return f'    {key} = DecimalParameter(0.001, 0.20, default={value}, decimals=3, space="exit", optimize=True)'


def _entry_logic(entry_id: str) -> tuple[str, str]:
    if entry_id == "fvg":
        return "        dataframe['ema'] = ta.EMA(dataframe, timeperiod=self.enter_ema_period.value)\n        dataframe['fvg_gap'] = dataframe['low'] / dataframe['high'].shift(2) - 1", "(dataframe['fvg_gap'] >= self.enter_fvg_min_gap_pct.value) & (dataframe['fvg_gap'] <= self.enter_fvg_max_gap_pct.value) & (dataframe['close'] > dataframe['ema']) & (dataframe['rsi'] <= self.enter_rsi_max.value)"
    if entry_id == "vwap_pullback":
        return "        dataframe['ema'] = ta.EMA(dataframe, timeperiod=self.enter_ema_period.value)\n        dataframe['vwap'] = (dataframe['close'] * dataframe['volume']).cumsum() / dataframe['volume'].cumsum().replace(0, float('nan'))", "(dataframe['close'] >= dataframe['vwap'] * (1 - self.enter_vwap_distance_pct.value)) & (dataframe['close'].shift(1) <= dataframe['vwap'].shift(1)) & (dataframe['close'] > dataframe['ema']) & (dataframe['rsi'] >= self.enter_rsi_min.value) & (dataframe['rsi'] <= self.enter_rsi_max.value)"
    if entry_id == "ema_cross":
        return "        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.enter_ema_fast.value)\n        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.enter_ema_slow.value)\n        dataframe['ema_trend'] = ta.EMA(dataframe, timeperiod=self.enter_ema_trend.value)\n        dataframe['ema_cross_recent'] = ((dataframe['ema_fast'] > dataframe['ema_slow']) & (dataframe['ema_fast'].shift(1) <= dataframe['ema_slow'].shift(1))).rolling(self.enter_cross_lookback.value).max()", "(dataframe['ema_fast'] > dataframe['ema_slow']) & (dataframe['ema_cross_recent'] > 0) & (dataframe['close'] > dataframe['ema_trend'])"
    if entry_id == "rsi_reversion":
        return "        dataframe['ema'] = ta.EMA(dataframe, timeperiod=self.enter_ema_period.value)", "(dataframe['rsi'] >= self.enter_rsi_min.value) & (dataframe['rsi'] <= self.enter_rsi_max.value) & (dataframe['close'] > dataframe['ema'])"
    if entry_id == "macd_trend":
        return "        dataframe['ema'] = ta.EMA(dataframe, timeperiod=self.enter_ema_period.value)\n        macd = ta.MACD(dataframe, fastperiod=self.enter_macd_fast.value, slowperiod=self.enter_macd_slow.value, signalperiod=self.enter_macd_signal.value)\n        dataframe['macd'], dataframe['macdsignal'] = macd['macd'], macd['macdsignal']\n        dataframe['macd_cross_recent'] = ((dataframe['macd'] > dataframe['macdsignal']) & (dataframe['macd'].shift(1) <= dataframe['macdsignal'].shift(1))).rolling(self.enter_cross_lookback.value).max()", "(dataframe['macd'] > dataframe['macdsignal']) & (dataframe['macd_cross_recent'] > 0) & (dataframe['close'] > dataframe['ema'])"
    if entry_id == "bollinger_reversion":
        return "        bands = ta.BBANDS(dataframe, timeperiod=self.enter_bb_period.value, nbdevup=self.enter_bb_stddev.value, nbdevdn=self.enter_bb_stddev.value)\n        dataframe['bb_lower'] = bands['lowerband']", "(dataframe['close'] <= dataframe['bb_lower'] * (1 + self.enter_bb_reentry_pct.value)) & (dataframe['rsi'] >= self.enter_rsi_min.value) & (dataframe['rsi'] <= self.enter_rsi_max.value)"
    if entry_id == "donchian_breakout":
        return "        dataframe['ema'] = ta.EMA(dataframe, timeperiod=self.enter_ema_period.value)\n        dataframe['donchian_high'] = dataframe['high'].rolling(self.enter_donchian_period.value).max().shift(1)", "(dataframe['close'] >= dataframe['donchian_high'] * (1 - self.enter_donchian_buffer_pct.value)) & (dataframe['close'] > dataframe['ema'])"
    if entry_id == "stochastic_reversal":
        return "        stoch = ta.STOCH(dataframe, fastk_period=self.enter_stoch_k.value, slowk_period=self.enter_stoch_d.value, slowd_period=self.enter_stoch_d.value)\n        dataframe['slowk'], dataframe['slowd'] = stoch['slowk'], stoch['slowd']\n        dataframe['stoch_cross_recent'] = ((dataframe['slowk'] > dataframe['slowd']) & (dataframe['slowk'].shift(1) <= dataframe['slowd'].shift(1))).rolling(self.enter_cross_lookback.value).max()", "(dataframe['stoch_cross_recent'] > 0) & (dataframe['slowk'] >= self.enter_stoch_min.value) & (dataframe['slowk'] <= self.enter_stoch_max.value)"
    raise ValueError(f"Unknown entry template: {entry_id}")


def _exit_logic(exit_id: str) -> str:
    if exit_id == "atr_trailing":
        return "        atr = candle['exit_atr']\n        if trade.max_rate >= trade.open_rate + (atr * self.exit_atr_activation.value):\n            return stoploss_from_absolute(trade.max_rate - (atr * self.exit_atr_trail.value), current_rate, is_short=trade.is_short)\n        return -self.exit_initial_stop_pct.value"
    if exit_id == "chandelier":
        return "        atr = candle['exit_atr']\n        if trade.max_rate >= trade.open_rate + (atr * self.exit_chandelier_activation.value):\n            return stoploss_from_absolute(trade.max_rate - (atr * self.exit_chandelier_trail.value), current_rate, is_short=trade.is_short)\n        return -self.exit_initial_stop_pct.value"
    if exit_id == "rsi_trailing":
        return "        if candle['rsi'] >= self.exit_rsi_activation.value:\n            return stoploss_from_absolute(trade.max_rate * (1 - self.exit_rsi_trail_pct.value), current_rate, is_short=trade.is_short)\n        return -self.exit_initial_stop_pct.value"
    if exit_id == "profit_trailing":
        return "        if current_profit >= self.exit_profit_activation.value:\n            return stoploss_from_absolute(trade.max_rate * (1 - self.exit_profit_trail_pct.value), current_rate, is_short=trade.is_short)\n        return -self.exit_initial_stop_pct.value"
    raise ValueError(f"Unknown exit template: {exit_id}")


def _exit_indicators(exit_id: str) -> str:
    if exit_id in {"atr_trailing", "chandelier"}:
        return "\n        dataframe['exit_atr'] = ta.ATR(dataframe, timeperiod=self.exit_atr_period.value)\n"
    return ""


def _preset(template_id: str) -> tuple[str, str, str, str]:
    return next((item for item in PRESETS if item[0] == template_id), PRESETS[0])


def _matching_preset(entry_id: str, exit_id: str) -> str:
    return next((item[0] for item in PRESETS if item[2:] == (entry_id, exit_id)), "")


def _component(items: tuple[Component, ...], component_id: str) -> Component:
    return next((item for item in items if item.id == component_id), None) or _raise_unknown(component_id)


def _raise_unknown(component_id: str) -> Component:
    raise ValueError(f"Unknown strategy component: {component_id}")


def _class_name(name: str) -> str:
    parts = "".join(character if character.isalnum() else " " for character in name).split()
    return "".join(part[:1].upper() + part[1:] for part in parts) or "StudioStrategy"
