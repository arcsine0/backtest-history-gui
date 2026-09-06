# Backtest History GUI

This workspace contains a PyTauri desktop shell with a Python backtesting backend scaffold.

- `desktop/src-tauri/src-python/backtest_history_gui/models.py`: typed request/result boundaries.
- `desktop/src-tauri/src-python/backtest_history_gui/market_data.py`: CCXT market-data TODO.
- `desktop/src-tauri/src-python/backtest_history_gui/backtest_service.py`: Backtesting.py TODO.
- `desktop/src-tauri/src-python/backtest_history_gui/storage.py`: SQLite result backup schema and save function.

## Prerequisites

- Node.js and pnpm
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Rust toolchain

## Install

```powershell
cd desktop
uv sync
pnpm install
```

Start the desktop development app from an activated environment:

```powershell
cd desktop
.venv\Scripts\Activate.ps1
pnpm tauri dev
```

## Backend libraries

The Python environment includes `backtesting` and `ccxt`. SQLite uses Python's built-in `sqlite3` module; local database files under `data/` are ignored by Git.
