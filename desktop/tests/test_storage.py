import importlib.util
import tempfile
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from zipfile import ZipFile
from pathlib import Path
import sys
from threading import Event

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
        download = runner.download_data_command("binance", "futures", ["BTC/USDT:USDT"], ["5m"], Path("data"), "20210101-20260101")
        self.assertEqual(download[3], "download-data")
        self.assertIn("--datadir", download)
        self.assertIn("--prepend", download)
        hyperopt = runner.hyperopt_command(Path("config.json"), "FvgAtr", Path("strategies"), Path("data"), 10)
        self.assertEqual(hyperopt[3], "hyperopt")
        self.assertEqual(hyperopt[hyperopt.index("--spaces") + 1:hyperopt.index("--spaces") + 3], ["enter", "exit"])
        custom = runner.hyperopt_command(Path("config.json"), "FvgAtr", Path("strategies"), Path("data"), 10, loss_name="StudioGoalHyperOptLoss", hyperopt_path=Path("hyperopts"))
        self.assertEqual(custom[custom.index("--hyperopt-loss") + 1], "StudioGoalHyperOptLoss")
        self.assertIn("--hyperopt-path", custom)

    def test_goal_loss_and_validation_score_reward_trade_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            loss_name, loss_path = runner.write_goal_hyperopt_loss(Path(directory), {"profile": "higher_frequency", "target_trades_per_year": 200, "max_drawdown_pct": 20, "min_profit_factor": 1.2})
            self.assertEqual(loss_name, "StudioGoalHyperOptLoss")
            source = (loss_path / "StudioGoalHyperOptLoss.py").read_text(encoding="utf-8")
            self.assertIn("annualized_trades", source)
            compile(source, "<goal-loss>", "exec")
        high_coverage, _ = runner.validation_stability_score([1.0, 1.1], [20, 20], 10)
        low_coverage, _ = runner.validation_stability_score([1.0, 1.1], [1, 1], 10)
        self.assertGreater(high_coverage, low_coverage)

    def test_validation_snapshot_contains_all_splits(self):
        with tempfile.TemporaryDirectory() as directory:
            setup = templates.make_template_strategy("FVG ATR", "fvg_atr", directory)
            payload = {"training": {"backtest": {"metrics": {"Return [%]": 1}, "trades": [], "equity_curve": [100, 101]}}, "tests": [{"label": "Test 1", "backtest": {"metrics": {"Return [%]": 2}, "trades": [], "equity_curve": [100, 102]}}]}
            path = Path(directory) / "validation.sqlite3"
            storage.save_validation_file(setup, payload, path)
            self.assertEqual(snapshots.load_freqtrade_snapshot(path)["validations"], [payload])

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
            self.assertEqual(config["entry_pricing"]["price_side"], "same")
            self.assertEqual(config["exit_pricing"]["price_side"], "same")
            self.assertTrue(config["entry_pricing"]["use_order_book"])
            self.assertTrue(config["exit_pricing"]["use_order_book"])

    def test_initializes_freqtrade_user_data_directory(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(runner, "run") as run_command:
            user_data = runner.ensure_userdir(Path(directory))
            self.assertEqual(user_data, Path(directory) / "user_data")
            run_command.assert_called_once_with(runner.userdir_command(user_data), Path(directory))

    def test_reads_freqtrade_zip_backtest_result(self):
        with tempfile.TemporaryDirectory() as directory:
            result_dir = Path(directory)
            archive = result_dir / "backtest-result-2026-10-29_05-10-00.zip"
            with ZipFile(archive, "w") as output:
                output.writestr("backtest-result-2026-10-29_05-10-00.json", '{"strategy": {"Test": {"starting_balance": 100, "profit_total": 0.1, "trades": []}}}')
                output.writestr("backtest-result-2026-10-29_05-10-00_config.json", "{}")
            (result_dir / ".last_result.json").write_text('{"latest_backtest": "backtest-result-2026-10-29_05-10-00.zip"}', encoding="utf-8")
            self.assertEqual(runner.parse_backtest_directory(result_dir)["metrics"]["Return [%]"], 10.0)

    def test_walk_forward_ranges_reserve_training_and_ten_tests(self):
        training, tests = runner.walk_forward_ranges(datetime(2021, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertTrue(training.startswith("20210101T0000-"))
        self.assertEqual(len(tests), 10)
        self.assertTrue(tests[0].startswith(training.split("-")[1]))
        self.assertEqual(len(runner.walk_forward_ranges(datetime(2021, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, tzinfo=timezone.utc), 5)[1]), 5)

    def test_uses_local_candle_cache_only_when_it_covers_the_requested_range(self):
        with patch.object(runner, "available_candle_range", return_value=(datetime(2021, 1, 1, tzinfo=timezone.utc), datetime(2026, 11, 2, tzinfo=timezone.utc))):
            self.assertTrue(runner.data_covers_timerange(Path("data"), ["BTC/USDT:USDT"], ["5m"], "20231029-20261029"))
            self.assertFalse(runner.data_covers_timerange(Path("data"), ["BTC/USDT:USDT"], ["5m"], "20201029-20261029"))

    def test_cancels_running_freqtrade_command_without_returning_output(self):
        cancelled = Event()
        cancelled.set()
        with self.assertRaises(runner.RunCancelled):
            runner.run([sys.executable, "-c", "import time; time.sleep(10)"], Path.cwd(), cancelled)

    def test_streams_command_output_to_progress_callback(self):
        lines: list[str] = []
        runner.run([sys.executable, "-c", "print('Epoch 1/2')"], Path.cwd(), on_output=lines.append)
        self.assertEqual(lines, ["Epoch 1/2\n"])

    def test_polls_running_command_when_output_is_not_line_based(self):
        polls: list[bool] = []
        runner.run([sys.executable, "-c", "import time; time.sleep(.3)"], Path.cwd(), on_poll=lambda: polls.append(True))
        self.assertTrue(polls)


if __name__ == "__main__":
    unittest.main()
