"""CCXT OHLCV cache for the local Backtesting.py adapter."""

import re
from pathlib import Path

import pandas as pd


def list_reference_ohlcv(references_root: Path) -> list[str]:
    if not references_root.is_dir():
        return []
    return [str(path.resolve()) for path in sorted(references_root.rglob("*.csv"))]


def reference_ohlcv(path: Path, references_root: Path) -> pd.DataFrame:
    """Load only CSV candles the user selected from the project's references folder."""
    candidate = path.resolve(strict=True)
    root = references_root.resolve()
    if candidate.suffix.lower() != ".csv" or not candidate.is_relative_to(root):
        raise ValueError("OHLCV data must be a CSV inside data/references.")
    return _normalise(pd.read_csv(candidate, index_col="timestamp", parse_dates=True))


def cached_ccxt_ohlcv(config: dict, cache_root: Path) -> pd.DataFrame:
    codes = config.get("codes", [])
    if not isinstance(codes, list) or len(codes) != 1:
        raise ValueError("Backtesting.py conversion supports exactly one Vibe-Trading symbol.")
    source = str(config.get("source", "ccxt")).lower()
    exchange_id = str(config.get("exchange") or ("okx" if source == "okx" else "binance"))
    symbol = str(codes[0]).replace("-", "/")
    timeframe = str(config.get("interval", "1D")).lower()
    start, end = str(config.get("start_date", "")), str(config.get("end_date", ""))
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{exchange_id}-{symbol}-{timeframe}-{start}-{end}")
    path = cache_root / f"{safe}.csv"
    if path.is_file():
        return _normalise(pd.read_csv(path, index_col="timestamp", parse_dates=True))
    import ccxt
    exchange_cls = getattr(ccxt, exchange_id, None)
    if exchange_cls is None:
        raise ValueError(f"Unsupported CCXT exchange: {exchange_id}.")
    exchange = exchange_cls({"enableRateLimit": True})
    since = exchange.parse8601(f"{start}T00:00:00Z") if start else None
    end_ms = exchange.parse8601(f"{end}T23:59:59Z") if end else None
    rows = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        since = int(batch[-1][0]) + 1
        if len(batch) < 1000 or (end_ms is not None and since >= end_ms):
            break
    if not rows:
        raise ValueError("CCXT returned no OHLCV candles for this Vibe snapshot.")
    frame = pd.DataFrame(rows, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    frame = frame.set_index("timestamp")
    cache_root.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index_label="timestamp")
    return _normalise(frame)


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    required = ["Open", "High", "Low", "Close", "Volume"]
    if not set(required).issubset(frame.columns):
        raise ValueError("Cached OHLCV data is missing required Backtesting.py columns.")
    return frame[required].sort_index().dropna()
