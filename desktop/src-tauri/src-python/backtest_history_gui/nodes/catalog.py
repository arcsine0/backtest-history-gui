"""The immutable node catalog supplied to future graph editors and AI planners."""

from __future__ import annotations

from .contracts import NodeDefinition
from .indicators.adx import NODE as ADX
from .indicators.atr import NODE as ATR
from .indicators.bollinger import NODE as BOLLINGER
from .indicators.donchian import NODE as DONCHIAN
from .indicators.ema import NODE as EMA
from .indicators.macd import NODE as MACD
from .indicators.obv import NODE as OBV
from .indicators.rsi import NODE as RSI
from .indicators.sma import NODE as SMA
from .indicators.stochastic import NODE as STOCHASTIC
from .indicators.vwap import NODE as VWAP
from .inputs.constant import NODE as CONSTANT
from .inputs.ohlcv import NODE as OHLCV
from .inputs.parameter import NODE as PARAMETER
from .inputs.trade_state import NODE as TRADE_STATE
from .processing.arithmetic import NODE as ARITHMETIC
from .processing.boolean_logic import NODE as BOOLEAN
from .processing.breakout import NODE as BREAKOUT
from .processing.comparison import NODE as COMPARISON
from .processing.crossover import NODE as CROSSOVER
from .processing.fair_value_gap import NODE as FAIR_VALUE_GAP
from .processing.forward_fill import NODE as FORWARD_FILL
from .processing.lookback import NODE as LOOKBACK
from .processing.offset import NODE as OFFSET
from .processing.range import NODE as RANGE
from .processing.retest import NODE as RETEST
from .processing.rolling import NODE as ROLLING
from .processing.swing import NODE as SWING
from .processing.threshold_zone import NODE as THRESHOLD_ZONE
from .processing.volume_filter import NODE as VOLUME_FILTER
from .risk.atr_trailing import NODE as ATR_TRAILING
from .risk.initial_stop import NODE as INITIAL_STOP
from .risk.profit_trailing import NODE as PROFIT_TRAILING
from .risk.rsi_trailing import NODE as RSI_TRAILING
from .risk.time_stop import NODE as TIME_STOP
from .signals.enter_long import NODE as ENTER_LONG
from .signals.exit_long import NODE as EXIT_LONG
from .signals.skip import NODE as SKIP

CATALOG_VERSION = 1
NODES: tuple[NodeDefinition, ...] = (
    OHLCV,
    CONSTANT,
    PARAMETER,
    TRADE_STATE,
    EMA,
    SMA,
    RSI,
    ATR,
    VWAP,
    MACD,
    BOLLINGER,
    STOCHASTIC,
    ADX,
    DONCHIAN,
    OBV,
    ARITHMETIC,
    COMPARISON,
    BOOLEAN,
    OFFSET,
    ROLLING,
    CROSSOVER,
    THRESHOLD_ZONE,
    RETEST,
    SWING,
    RANGE,
    BREAKOUT,
    FAIR_VALUE_GAP,
    FORWARD_FILL,
    VOLUME_FILTER,
    LOOKBACK,
    INITIAL_STOP,
    ATR_TRAILING,
    PROFIT_TRAILING,
    RSI_TRAILING,
    TIME_STOP,
    ENTER_LONG,
    EXIT_LONG,
    SKIP,
)


def node_catalog() -> dict:
    """Return a JSON-serializable catalog; callers must never accept arbitrary node types."""
    return {"version": CATALOG_VERSION, "nodes": [node.as_dict() for node in NODES]}


def node_by_id(node_id: str) -> NodeDefinition:
    return next(node for node in NODES if node.id == node_id)
