# Backtest History GUI

This workspace contains a PyTauri desktop shell with a local Vibe-Trading companion GUI and a Python backtesting backend scaffold.

- `desktop/src-tauri/src-python/backtest_history_gui/models.py`: typed contracts for strategy setups, backtest runs, and the existing local backend seams.
- `desktop/src-tauri/src-python/backtest_history_gui/market_data.py`: CCXT market-data TODO.
- `desktop/src-tauri/src-python/backtest_history_gui/backtest_service.py`: Backtesting.py TODO.
- `desktop/src-tauri/src-python/backtest_history_gui/storage.py`: SQLite persistence for strategy setups, portable run snapshots, and imported results.
- `desktop/src-tauri/src-python/backtest_history_gui/vibe.py`: safe subprocess bridge to the Vibe-Trading CLI.

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

The `pnpm tauri` script uses the active venv (or `desktop/.venv`) and adds its
base Python directory to `PATH`, allowing Windows to locate `python312.dll`
for PyTauri.

## Backend libraries

The Python environment includes `backtesting` and `ccxt`. SQLite uses Python's built-in `sqlite3` module; local database files under `data/` are ignored by Git.

## Vibe-Trading companion

Install and initialize Vibe-Trading separately so its `vibe-trading` command is available on `PATH`:

```powershell
pip install vibe-trading-ai
vibe-trading init
```

The desktop app keeps its local history in `data/backtest_history.sqlite3`. A **Run backtest** action also exports a portable SQLite strategy save file to the selected workspace (the project root by default): `[strategy_name]-[raw|optimized]-[iteration]-[MMDDYYYY].sqlite3`. Each snapshot contains the strategy prompt, discovered parameters, metrics, trades, and equity curve. Paste its path into **Load strategy save file** to resume from it.
