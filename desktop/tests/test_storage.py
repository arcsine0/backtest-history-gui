import importlib.util
import tempfile
import types
import unittest
from pathlib import Path
import sys

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
templates = load("freqtrade_templates")
snapshots = load("freqtrade_snapshot")
runner = load("freqtrade_runner")


class FreqtradeStorageTests(unittest.TestCase):
    def test_template_snapshot_exports_strategy_and_parameter_file(self):
        with tempfile.TemporaryDirectory() as directory:
            setup = templates.make_template_strategy("FVG ATR", "fvg_atr", directory)
            setup.freqtrade_payload["parameter_file"] = {"params": {"buy": {"ema_period": 120}}}
            database = storage.open_database(Path(directory) / "history.sqlite3")
            saved = storage.save_strategy(database, setup)
            snapshot_path = storage.next_snapshot(database, saved, "backtest")
            storage.save_strategy_file(saved, {"metrics": {"Return [%]": 1}, "trades": [], "equity_curve": [100, 101]}, snapshot_path)
            database.close()
            exported = snapshots.export_strategy(snapshot_path, Path(directory) / "strategies")
            loaded = snapshots.load_freqtrade_snapshot(snapshot_path)
            self.assertTrue(exported.is_file())
            self.assertTrue(exported.with_suffix(".json").is_file())
            self.assertEqual(loaded["template_id"], "fvg_atr")
            compile(exported.read_text(encoding="utf-8"), "<strategy>", "exec")

    def test_normalizes_freqtrade_result_to_existing_charts_contract(self):
        result = runner.normalise_result({"strategy": {"FvgAtr": {"starting_balance": 100, "profit_total": 0.1, "profit_total_abs": 10, "total_trades": 1, "trades": [{"close_date": "2026-01-01", "profit_abs": 10}]}}})
        self.assertEqual(result["metrics"]["Return [%]"], 10.0)
        self.assertEqual(result["equity_curve"], [100.0, 110.0])

    def test_builds_supported_freqtrade_cli_commands(self):
        command = runner.backtest_command(Path("config.json"), "FvgAtr", Path("strategies"), Path("results"), Path("data"), "20260101-20260201")
        self.assertEqual(command[3], "backtesting")
        self.assertIn("--timerange", command)
        download = runner.download_data_command("binance", "futures", ["BTC/USDT:USDT"], ["5m"], Path("data"))
        self.assertEqual(download[3], "download-data")
        self.assertIn("--datadir", download)
        hyperopt = runner.hyperopt_command(Path("config.json"), "FvgAtr", Path("strategies"), Path("data"), 10)
        self.assertEqual(hyperopt[3], "hyperopt")
        self.assertEqual(hyperopt[hyperopt.index("--spaces") + 1:hyperopt.index("--spaces") + 3], ["enter", "exit"])

    def test_templates_compose_entry_and_dynamic_exit_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            for entry in templates.list_entries():
                for exit_rule in templates.list_exits():
                    setup = templates.make_template_strategy("Test", "fvg_atr", directory, entry["id"], exit_rule["id"])
                    self.assertEqual(setup.freqtrade_payload["entry_id"], entry["id"])
                    self.assertEqual(setup.freqtrade_payload["exit_id"], exit_rule["id"])
                    compile(setup.freqtrade_payload["strategy_source"], "<strategy>", "exec")

    def test_generates_safe_workspace_config_when_not_supplied(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = runner.ensure_config("", Path(directory), "binance", "futures", ["BTC/USDT:USDT"], ["5m"])
            config = __import__("json").loads(config_path.read_text(encoding="utf-8"))
            self.assertTrue(config["dry_run"])
            self.assertEqual(config["exchange"]["pair_whitelist"], ["BTC/USDT:USDT"])
            self.assertEqual(config["trading_mode"], "futures")


if __name__ == "__main__":
    unittest.main()
