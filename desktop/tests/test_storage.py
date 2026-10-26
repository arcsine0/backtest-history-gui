import importlib.util
import json
import sqlite3
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
vibe = load("vibe")
auto_workflow = load("auto_workflow")


class StorageTests(unittest.TestCase):
    def test_saves_strategy_and_imported_backtest(self) -> None:
        setup = models.StrategySetup(name="VWAP ATR", source="entry when price crosses VWAP", optimization_goal="Reduce drawdown")
        with tempfile.TemporaryDirectory() as directory:
            setup.workspace_path = directory
            connection = storage.open_database(Path(directory) / "backtests.sqlite3")
            saved_setup = storage.save_strategy(connection, setup)
            payload = {"metrics": {"Return [%]": 1.2}, "trades": [{"EntryPrice": 100}], "equity_curve": [1000, 1012]}
            _, snapshot_path = storage.next_snapshot(connection, saved_setup, "raw")
            saved_setup = storage.save_strategy_file(saved_setup, payload, snapshot_path)
            saved_result = storage.import_backtest(connection, snapshot_path.name, payload)
            loaded = storage.load_backtest(connection, saved_result.id)
            loaded_setup, loaded_snapshot = storage.load_strategy_file(snapshot_path)
            connection.close()
            self.assertEqual(saved_setup.id, 1)
            self.assertTrue(Path(saved_setup.strategy_file).is_file())
            self.assertEqual(loaded.metrics["Return [%]"], 1.2)
            self.assertEqual(loaded.trades[0]["EntryPrice"], 100)
            self.assertEqual(loaded_setup.parameters, saved_setup.parameters)
            self.assertEqual(loaded_setup.optimization_goal, "Reduce drawdown")
            self.assertEqual(loaded_snapshot.equity_curve, [1000.0, 1012.0])

    def test_copies_recycles_and_restores_strategy_save_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "strategy-raw-1-10272026.sqlite3"
            source.write_text("snapshot", encoding="utf-8")
            good_copy = storage.copy_strategy_save_to_good(source, root / "good")
            recycled, previous = storage.recycle_strategy_save_file(source, root / "recycle-bin")
            restored = storage.restore_strategy_save_file(source, recycled, root / "recycle-bin")
            self.assertEqual(good_copy.read_text(encoding="utf-8"), "snapshot")
            self.assertIsNone(previous)
            self.assertEqual(restored, source.resolve())
            self.assertTrue(restored.is_file())

    def test_deletes_and_clears_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            connection = storage.open_database(Path(directory) / "backtests.sqlite3")
            first = storage.import_backtest(connection, "first", {"metrics": {}, "trades": [], "equity_curve": []})
            storage.import_backtest(connection, "second", {"metrics": {}, "trades": [], "equity_curve": []})
            storage.delete_backtest(connection, first.id)
            self.assertEqual(len(storage.list_backtests(connection)), 1)
            storage.clear_backtests(connection)
            self.assertEqual(storage.list_backtests(connection), [])
            connection.close()

    def test_redo_snapshot_uses_a_sub_iteration(self) -> None:
        setup = models.StrategySetup(name="VWAP ATR", source="entry")
        with tempfile.TemporaryDirectory() as directory:
            setup.workspace_path = directory
            connection = storage.open_database(Path(directory) / "backtests.sqlite3")
            storage.import_backtest(connection, "VWAP-ATR-raw-1-10272026.sqlite3", {"metrics": {}, "trades": [], "equity_curve": []})
            storage.import_backtest(connection, "VWAP-ATR-raw-1.1-10272026.sqlite3", {"metrics": {}, "trades": [], "equity_curve": []})
            iteration, path = storage.next_snapshot(connection, setup, "raw", "VWAP-ATR-raw-1.1-10272026.sqlite3")
            connection.close()
        self.assertEqual(iteration, "1.2")
        self.assertIn("-raw-1.2-", path.name)

    def test_backtest_prompt_requests_the_required_metrics_and_parameters(self) -> None:
        setup = models.StrategySetup(name="VWAP ATR", source="buy when price crosses VWAP")
        prompt = vibe.backtest_prompt(setup, "raw")
        self.assertIn(setup.name, prompt)
        self.assertIn(setup.source, prompt)
        self.assertIn("UPPER_CASE module-level constant", prompt)
        self.assertIn("Max. Drawdown [%]", prompt)
        self.assertIn("equity_curve", prompt)
        payload, parameters = vibe.parse_backtest_output(json.dumps({"parameters": [{"name": "VWAP", "value": "20"}], "metrics": {"P/L": 1}, "trades": [], "equity_curve": [1000]}))
        self.assertEqual(payload["metrics"]["P/L"], 1)
        self.assertEqual(parameters[0].name, "VWAP")
        nested, _ = vibe.parse_backtest_output(json.dumps({"response": json.dumps({"metrics": {"P/L": 2}, "trades": [], "equity_curve": [1000]})}))
        self.assertEqual(nested["metrics"]["P/L"], 2)

    def test_strategy_run_can_return_raw_output_without_a_backtest(self) -> None:
        setup = models.StrategySetup(name="VWAP ATR", source="buy when price crosses VWAP")
        diagnostic = models.StrategyRun(strategy=setup, output="plain-text provider response", error="Vibe-Trading did not return the required backtest JSON.")
        self.assertIsNone(diagnostic.backtest)
        self.assertEqual(diagnostic.output, "plain-text provider response")

    def test_parses_vibe_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            artifacts = run_dir / "artifacts"
            artifacts.mkdir()
            (artifacts / "metrics.csv").write_text("total_return,max_drawdown,win_rate,trade_count,profit_factor,sharpe,sortino\n0.1,-0.05,0.6,2,1.5,1.2,1.1\n")
            (artifacts / "equity.csv").write_text("timestamp,equity,drawdown\n1,100,0\n2,110,-0.01\n")
            (artifacts / "trades.csv").write_text("timestamp,side,pnl\n1,buy,0\n2,sell,10\n")
            (run_dir / "config.json").write_text(json.dumps({"parameters": {"atr_period": 14}}))
            payload, parameters = vibe.parse_vibe_artifacts(run_dir)
        self.assertEqual(payload["metrics"]["P/L"], 10)
        self.assertEqual(payload["metrics"]["Return [%]"], 10)
        self.assertEqual(payload["metrics"]["Win Rate [%]"], 60)
        self.assertNotIn("Vibe: Profit Factor", payload["metrics"])
        self.assertNotIn("P/L [%]", payload["metrics"])
        self.assertEqual(payload["trades"][1]["pnl"], "10")
        self.assertEqual(payload["equity_timestamps"], ["1", "2"])
        self.assertEqual(parameters[0].name, "atr_period")

    def test_extracts_tunable_parameters_from_strategy_code_when_config_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            strategy_code = Path(directory) / "signal_engine.py"
            strategy_code.write_text("ATR_PERIOD = 14\nTRAILING_MULTIPLIER = 3.0\nIGNORED = 1\n", encoding="utf-8")
            parameters = vibe._parameters_from_strategy_code(strategy_code)
        self.assertEqual([parameter.name for parameter in parameters], ["ATR_PERIOD", "TRAILING_MULTIPLIER"])

    def test_auto_optimization_prompt_includes_displayed_metrics(self) -> None:
        setup = models.StrategySetup(name="VWAP ATR", source="buy when price crosses VWAP", parameters=[models.StrategyParameter(name="atr_period", value="14"), models.StrategyParameter(name="risk_fraction", value="0.01", locked=True)])
        prompt = vibe.backtest_prompt(setup, "auto", {"P/L [%]": -2.5, "Win Rate [%]": 45})
        self.assertIn('"P/L [%]": -2.5', prompt)
        self.assertIn("atr_period=14 [OPTIMIZE]", prompt)
        self.assertIn("risk_fraction=0.01 [LOCKED]", prompt)
        self.assertIn("LOCKED and FIXED parameters must remain present and unchanged", prompt)
        selected_prompt = vibe.backtest_prompt(setup, "optimized", {"P/L [%]": -2.5})
        self.assertIn('Prioritize optimizing only these unlocked parameters: atr_period=14.', selected_prompt)
        self.assertIn('Use these displayed prior-backtest metrics as the second priority: {"P/L [%]": -2.5}', selected_prompt)
        goal_prompt = vibe.backtest_prompt(setup, "auto", {"P/L [%]": -2.5}, "Improve drawdown without reducing return")
        self.assertIn("Prioritize this goal: Improve drawdown without reducing return.", goal_prompt)
        discovery_prompt = vibe.backtest_prompt(models.StrategySetup(name="VWAP", source="buy on VWAP cross"), "auto", {"P/L [%]": -2.5})
        self.assertIn("first identifying the strategy's tunable constants", discovery_prompt)

    def test_reports_ambiguous_symbol_when_vibe_did_not_backtest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            artifacts = run_dir / "artifacts"
            artifacts.mkdir()
            (artifacts / "grounding_evidence.json").write_text(json.dumps({"identity": {"status": "ambiguous"}}))
            with self.assertRaisesRegex(ValueError, "market symbol is ambiguous"):
                vibe.parse_vibe_artifacts(run_dir)

    def test_adds_workspace_path_to_existing_strategy_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backtests.sqlite3"
            legacy = sqlite3.connect(path)
            legacy.execute("CREATE TABLE strategy_setups (id INTEGER PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL, parameters_json TEXT NOT NULL, updated_at TEXT NOT NULL)")
            legacy.execute("INSERT INTO strategy_setups VALUES (1, 'Legacy', 'source', '[]', '2026-01-01')")
            legacy.commit()
            legacy.close()
            connection = storage.open_database(path)
            loaded = storage.list_strategies(connection)[0]
            connection.close()
        self.assertEqual(loaded.workspace_path, models.DEFAULT_WORKSPACE)

    def test_auto_workflow_keeps_its_own_history_database_and_goal_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = models.AutoWorkflowRequest(
                strategy=models.StrategySetup(name="VWAP", source="entry"),
                baseline=models.StoredBacktest(id=1, name="base", imported_at="now", metrics={"Return [%]": 1, "Max. Drawdown [%]": -10}, trades=[], equity_curve=[]),
                prompt_limit=3,
                target_metrics=["Return [%]", "Max. Drawdown [%]"],
            )
            workflow = auto_workflow.create_workflow(Path(directory) / "history" / "auto-runs", request)
            loaded = auto_workflow.load_workflow(Path(workflow.path))
            self.assertTrue(Path(workflow.path, "backtest_history.sqlite3").is_file())
        self.assertEqual(loaded.prompt_limit, 3)
        self.assertGreater(auto_workflow._score({"Return [%]": 2, "Max. Drawdown [%]": -5}, request.baseline.metrics, request.target_metrics), 0)
        self.assertTrue(auto_workflow._goal_met({"Return [%]": 2, "Max. Drawdown [%]": -5}, request.baseline.metrics, request.target_metrics))
        collapsed = {"Return [%]": 2, "Max. Drawdown [%]": -5, "Win Rate [%]": 0}
        protected_baseline = {**request.baseline.metrics, "Win Rate [%]": 50}
        self.assertFalse(auto_workflow._goal_met(collapsed, protected_baseline, request.target_metrics))
        self.assertLess(auto_workflow._score(collapsed, protected_baseline, request.target_metrics), auto_workflow._score({"Return [%]": 2, "Max. Drawdown [%]": -5, "Win Rate [%]": 50}, protected_baseline, request.target_metrics))
