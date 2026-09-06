import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

PACKAGE = Path(__file__).parents[1] / "src-tauri" / "src-python" / "backtest_history_gui"
package = types.ModuleType("backtest_history_gui")
package.__path__ = [str(PACKAGE)]
sys.modules["backtest_history_gui"] = package


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"backtest_history_gui.{name}", PACKAGE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


models = load("models")
storage = load("storage")


class StorageTests(unittest.TestCase):
    def test_save_result(self) -> None:
        request = models.BacktestRequest(models.MarketDataRequest("binance", "BTC/USDT", "1h"), "Demo")
        result = models.BacktestResult(request, {"Return [%]": 1.2}, [])
        with tempfile.TemporaryDirectory() as directory:
            connection = storage.open_database(Path(directory) / "backtests.sqlite3")
            row_id = storage.save_result(connection, result)
            count = connection.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]
            connection.close()
        self.assertEqual(row_id, 1)
        self.assertEqual(count, 1)
