import importlib.util
import json
import tempfile
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from zipfile import ZipFile
from pathlib import Path
import sys
from threading import Event

PACKAGE = (
    Path(__file__).parents[1] / "src-tauri" / "src-python" / "backtest_history_gui"
)
package = types.ModuleType("backtest_history_gui")
package.__path__ = [str(PACKAGE)]
sys.modules["backtest_history_gui"] = package


def load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"backtest_history_gui.{name}", PACKAGE / f"{name}.py"
    )
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
ai_strategy = load("ai_strategy")
from backtest_history_gui.nodes import (
    NODES,
    NodeCompileError,
    node_catalog,
    node_compile_context,
)
from backtest_history_gui.graph_compiler import (
    GraphCompileError,
    compile_graph_fragments,
    graph_parameters,
    topological_nodes,
)
from backtest_history_gui.graph_schema import GraphEdge, GraphNode, StrategyGraph
from backtest_history_gui.preset_graphs import PRESET_GRAPHS


class FreqtradeStorageTests(unittest.TestCase):
    def test_declared_input_parameter_uses_its_own_hyperopt_range(self):
        graph = StrategyGraph(
            nodes=(
                GraphNode(
                    "rsi_cap",
                    "input.parameter",
                    {
                        "name": "PARAMETER",
                        "default": 70,
                        "minimum": 55,
                        "maximum": 85,
                    },
                ),
            ),
            edges=(),
        )
        parameters = graph_parameters(graph)
        self.assertEqual(len(parameters), 1)
        self.assertEqual(parameters[0].name, "rsi_cap")
        self.assertEqual(parameters[0].value, 70)
        self.assertEqual(parameters[0].definition.minimum, 55)
        self.assertEqual(parameters[0].definition.maximum, 85)

    def test_ai_graph_envelope_is_normalized_and_compiled_before_persistence(self):
        graph = next(iter(PRESET_GRAPHS.values()))()
        envelope = {
            "filename": "AI FVG Strategy.py",
            "graph": {
                "version": graph.version,
                "nodes": [
                    {
                        "id": node.id,
                        "type": node.type,
                        "parameters": [
                            {"key": key, "value": str(value).lower()}
                            for key, value in node.parameters.items()
                        ],
                    }
                    for node in graph.nodes
                ],
                "edges": [
                    {
                        "source_node": edge.source_node,
                        "source_port": edge.source_port,
                        "target_node": edge.target_node,
                        "target_port": edge.target_port,
                    }
                    for edge in graph.edges
                ],
            },
        }
        setup = ai_strategy.strategy_from_envelope(
            envelope,
            models.AiStrategyGraphRequest(
                prompt="Create an FVG strategy.",
                workspace_path="data",
                exchange="binance",
                trading_mode="futures",
                pairs="BTC/USDT:USDT",
                timeframes="5m",
            ),
        )
        self.assertTrue(setup.name.startswith("AI-FVG-Strategy-Futures-BTC-USDT-5m-"))
        self.assertEqual(setup.template_id, "ai_graph")
        self.assertEqual(setup.freqtrade_payload["ai"]["model"], "gpt-6-luna")
        compile(setup.freqtrade_payload["strategy_source"], "<strategy>", "exec")

    def test_ai_schema_requires_lowercase_snake_case_node_ids(self):
        node_schema = ai_strategy._OUTPUT_SCHEMA["properties"]["graph"]["properties"][
            "nodes"
        ]["items"]
        self.assertEqual(
            node_schema["properties"]["id"]["pattern"],
            "^[a-z][a-z0-9_]*$",
        )

    def test_saved_graph_payload_accepts_parameter_objects(self):
        graph = PRESET_GRAPHS["fvg_atr"]()
        restored = ai_strategy.graph_from_payload(json.loads(json.dumps(graph.as_dict())))
        self.assertEqual(
            [node.type for node in restored.nodes],
            [node.type for node in graph.nodes],
        )
        self.assertEqual(
            next(node for node in restored.nodes if node.id == "exit_trailing").parameters[
                "trail_atr"
            ],
            2.5,
        )

    def test_saved_version_one_graph_is_normalized_to_the_current_version(self):
        payload = json.loads(json.dumps(PRESET_GRAPHS["fvg_atr"]().as_dict()))
        payload["version"] = 1
        self.assertEqual(ai_strategy.graph_from_payload(payload).version, 2)

    def test_node_catalog_is_unique_serializable_and_exposes_indicator_parameters(self):
        catalog = node_catalog()
        json.dumps(catalog)
        self.assertEqual(catalog["version"], 2)
        self.assertEqual(
            len(catalog["nodes"]), len({node["id"] for node in catalog["nodes"]})
        )
        self.assertIn("input.ohlcv", {node["id"] for node in catalog["nodes"]})
        indicators = [node for node in NODES if node.group == "indicators"]
        self.assertTrue(indicators)
        self.assertTrue(
            all(
                parameter.optimizable
                for node in indicators
                for parameter in node.parameters
            )
        )

    def test_shared_node_compile_context_validates_and_collects_source(self):
        context = node_compile_context(
            "indicator.ema",
            "trend_ema",
            inputs={"source": "dataframe['close']"},
            parameter_values={"period": 50},
            parameter_references={"period": "self.enter_ema_period.value"},
        )
        self.assertEqual(context.input("source"), "dataframe['close']")
        self.assertEqual(context.parameter_value("period"), 50)
        self.assertEqual(context.parameter("period"), "self.enter_ema_period.value")
        self.assertEqual(
            context.bind_output(
                "value", "ta.EMA(dataframe, timeperiod=self.enter_ema_period.value)"
            ),
            "dataframe['node_trend_ema_value']",
        )
        context.require_import("import talib.abstract as ta")
        compiled = context.finalize()
        self.assertEqual(compiled.outputs["value"], "dataframe['node_trend_ema_value']")
        self.assertEqual(compiled.imports, ("import talib.abstract as ta",))
        with self.assertRaises(NodeCompileError):
            node_compile_context(
                "indicator.ema", "invalid-id", inputs={"source": "close"}
            )

    def test_shared_node_compile_context_supports_every_catalog_node(self):
        for index, node in enumerate(NODES):
            inputs = {
                port.key: f"input_{port.key}" for port in node.inputs
            }
            for port in node.inputs:
                for connection in range(2, port.minimum_connections + 1):
                    inputs[f"{port.key}_{connection}"] = (
                        f"input_{port.key}_{connection}"
                    )
            context = node_compile_context(
                node.id,
                f"node_{index}",
                inputs=inputs,
            )
            for output in node.outputs:
                self.assertIn(
                    f"node_node_{index}_{output.key}", context.output(output.key)
                )

    def test_graph_compiler_orders_and_compiles_catalog_nodes(self):
        graph = StrategyGraph(
            nodes=(
                GraphNode("candles", "input.ohlcv"),
                GraphNode("trend", "indicator.ema", {"period": 50}),
            ),
            edges=(GraphEdge("candles", "close", "trend", "source"),),
        )
        compiled = compile_graph_fragments(graph)
        self.assertEqual(compiled["order"], ("candles", "trend"))
        self.assertIn(
            "node_trend_value", "\n".join(compiled["statements"]["indicators"])
        )

    def test_variadic_logic_gates_compile_with_numbered_ports(self):
        graph = StrategyGraph(
            nodes=(
                GraphNode("candles", "input.ohlcv"),
                GraphNode("first", "process.comparison"),
                GraphNode("second", "process.comparison"),
                GraphNode("third", "process.comparison"),
                GraphNode("gate", "logic.xor"),
            ),
            edges=(
                GraphEdge("candles", "close", "first", "left"),
                GraphEdge("candles", "open", "first", "right"),
                GraphEdge("candles", "high", "second", "left"),
                GraphEdge("candles", "low", "second", "right"),
                GraphEdge("candles", "volume", "third", "left"),
                GraphEdge("candles", "volume", "third", "right"),
                GraphEdge("first", "result", "gate", "inputs"),
                GraphEdge("second", "result", "gate", "inputs_2"),
                GraphEdge("third", "result", "gate", "inputs_3"),
            ),
        )
        compiled = compile_graph_fragments(graph)
        statements = "\n".join(compiled["statements"]["conditions"])
        self.assertIn("node_first_result", statements)
        self.assertIn("node_second_result", statements)
        self.assertIn("node_third_result", statements)
        self.assertIn("^", statements)

    def test_variadic_nodes_require_their_minimum_connections(self):
        graph = StrategyGraph(
            nodes=(
                GraphNode("candles", "input.ohlcv"),
                GraphNode("first", "process.comparison"),
                GraphNode("gate", "logic.and"),
            ),
            edges=(
                GraphEdge("candles", "close", "first", "left"),
                GraphEdge("candles", "open", "first", "right"),
                GraphEdge("first", "result", "gate", "inputs"),
            ),
        )
        with self.assertRaisesRegex(GraphCompileError, "at least 2 connection"):
            compile_graph_fragments(graph)

    def test_variadic_arithmetic_and_statistics_compile(self):
        graph = StrategyGraph(
            nodes=(
                GraphNode("candles", "input.ohlcv"),
                GraphNode(
                    "combined", "arithmetic.operations", {"operation": "multiply"}
                ),
                GraphNode(
                    "average", "statistic.aggregate", {"operation": "average"}
                ),
            ),
            edges=(
                GraphEdge("candles", "close", "combined", "inputs"),
                GraphEdge("candles", "high", "combined", "inputs_2"),
                GraphEdge("candles", "low", "combined", "inputs_3"),
                GraphEdge("candles", "close", "average", "inputs"),
                GraphEdge("candles", "high", "average", "inputs_2"),
                GraphEdge("candles", "low", "average", "inputs_3"),
            ),
        )
        compiled = compile_graph_fragments(graph)
        statements = "\n".join(compiled["statements"]["indicators"])
        self.assertIn("*", statements)
        self.assertIn("pd.concat", statements)
        self.assertIn("import pandas as pd", compiled["imports"])

    def test_logic_and_unary_arithmetic_nodes_emit_real_source(self):
        modules = {
            "logic.and": "logic.and_gate",
            "logic.or": "logic.or_gate",
            "logic.nand": "logic.nand",
            "logic.nor": "logic.nor",
            "logic.xor": "logic.xor",
            "logic.not": "logic.not_gate",
            "arithmetic.round": "arithmetic.round",
            "arithmetic.flatten": "arithmetic.flatten",
        }
        for node_id, module_name in modules.items():
            inputs = (
                {"condition": "condition"}
                if node_id == "logic.not"
                else (
                    {"source": "dataframe['close']"}
                    if node_id.startswith("arithmetic.")
                    else {"inputs": "first", "inputs_2": "second"}
                )
            )
            context = node_compile_context(node_id, "test_node", inputs=inputs)
            module = importlib.import_module(
                f"backtest_history_gui.nodes.{module_name}"
            )
            fragment = module.compile_node(context)
            self.assertIn("value" if node_id.startswith("arithmetic.") else "result", fragment.outputs)
            self.assertTrue(fragment.statements)

    def test_registered_preset_graphs_have_valid_node_connections(self):
        for graph_factory in PRESET_GRAPHS.values():
            graph = graph_factory()
            self.assertTrue(topological_nodes(graph))
            self.assertTrue(compile_graph_fragments(graph)["order"])

    def test_strategy_run_accepts_optional_optimization_report(self):
        setup = models.StrategySetup(name="Test", template_id="fvg_atr")
        report = models.OptimizationReport(
            target_trades_per_year=100,
            best_trade_count=20,
            best_annualized_trades=20,
            max_observed_trades=30,
            max_observed_annualized_trades=30,
            feasible_candidate_count=0,
            goal_met=False,
            summary="Goal not met",
        )
        self.assertFalse(
            models.StrategyRun(
                strategy=setup, output="", optimization_report=report
            ).optimization_report.goal_met
        )

    def test_template_snapshot_exports_strategy_and_parameter_file(self):
        with tempfile.TemporaryDirectory() as directory:
            setup = templates.make_template_strategy("FVG ATR", "fvg_atr", directory)
            setup.freqtrade_payload["parameter_file"] = {
                "params": {"buy": {"ema_period": 120}}
            }
            database = storage.open_database(Path(directory) / "history.sqlite3")
            saved = storage.save_strategy(database, setup)
            snapshot_path = storage.next_snapshot(database, saved, "backtest")
            storage.save_strategy_file(
                saved,
                {
                    "metrics": {"Return [%]": 1},
                    "trades": [],
                    "equity_curve": [100, 101],
                },
                snapshot_path,
            )
            database.close()
            exported = snapshots.export_strategy(
                snapshot_path, Path(directory) / "strategies"
            )
            loaded = snapshots.load_freqtrade_snapshot(snapshot_path)
            self.assertTrue(exported.is_file())
            self.assertTrue(exported.with_suffix(".json").is_file())
            self.assertEqual(loaded["template_id"], "fvg_atr")
            compile(exported.read_text(encoding="utf-8"), "<strategy>", "exec")

    def test_templates_persist_schema_and_compile_through_the_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            setup = templates.make_template_strategy("FVG ATR", "fvg_atr", directory)
            graph = setup.freqtrade_payload["graph"]
            self.assertEqual(setup.freqtrade_payload["format"], "freqtrade-graph-v1")
            self.assertEqual(graph["version"], 2)
            self.assertEqual(setup.freqtrade_payload["entry_id"], "fvg")
            self.assertEqual(setup.freqtrade_payload["exit_id"], "atr_trailing")
            self.assertIn(
                "risk.atr_trailing", {node["type"] for node in graph["nodes"]}
            )
            self.assertIn(
                "class FVGATR(IStrategy):", setup.freqtrade_payload["strategy_source"]
            )
            self.assertIn(
                "isinstance(candle['node_exit_atr_value'], Real)",
                setup.freqtrade_payload["strategy_source"],
            )

    def test_writes_exported_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = storage.write_text_file(Path(directory) / "logs" / "run.log", "run output")
            self.assertEqual(target.read_text(encoding="utf-8"), "run output")

    def test_caches_openai_key_outside_strategy_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache" / "settings.sqlite3"
            self.assertEqual(storage.cached_openai_api_key(cache), "")
            storage.save_cached_openai_api_key("test-key", cache)
            self.assertEqual(storage.cached_openai_api_key(cache), "test-key")
            storage.clear_cached_openai_api_key(cache)
            self.assertEqual(storage.cached_openai_api_key(cache), "")

    def test_normalizes_freqtrade_result_to_existing_charts_contract(self):
        result = runner.normalise_result(
            {
                "strategy": {
                    "FvgAtr": {
                        "starting_balance": 100,
                        "profit_total": 0.1,
                        "profit_total_abs": 10,
                        "total_trades": 1,
                        "trades": [{"close_date": "2026-01-01", "profit_abs": 10}],
                    }
                }
            }
        )
        self.assertEqual(result["metrics"]["Return [%]"], 10.0)
        self.assertEqual(result["equity_curve"], [100.0, 110.0])

    def test_clears_only_requested_result_class_and_keeps_candle_data(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(storage, "_move_to_recycle") as recycle,
        ):
            workspace = Path(directory)
            backtest_snapshot = workspace / "Test-backtest-1-01012026.sqlite3"
            hyperopt_snapshot = workspace / "Test-hyperopt-1-01012026.sqlite3"
            candle = (
                workspace
                / "freqtrade"
                / "data"
                / "binance"
                / "BTC_USDT-5m-feather.feather"
            )
            backtest_snapshot.touch()
            hyperopt_snapshot.touch()
            candle.parent.mkdir(parents=True)
            candle.write_bytes(b"candle")
            results = workspace / "freqtrade" / "backtest_results"
            results.mkdir(parents=True)
            database = storage.open_database(workspace / "history.sqlite3")
            storage.import_backtest(
                database,
                backtest_snapshot.name,
                {"metrics": {}, "trades": [], "equity_curve": []},
            )
            storage.import_backtest(
                database,
                hyperopt_snapshot.name,
                {"metrics": {}, "trades": [], "equity_curve": []},
            )
            cleared = storage.clear_freqtrade_results(database, workspace, "backtests")
            self.assertEqual(cleared["history"], 1)
            self.assertEqual(len(storage.list_backtests(database)), 1)
            self.assertTrue(candle.is_file())
            self.assertEqual(
                storage.list_downloaded_datasets(workspace)[0]["path"],
                "binance\\BTC_USDT-5m-feather.feather",
            )
            self.assertGreaterEqual(recycle.call_count, 2)
            database.close()

    def test_builds_supported_freqtrade_cli_commands(self):
        command = runner.backtest_command(
            Path("config.json"),
            "FvgAtr",
            Path("strategies"),
            Path("results"),
            Path("data"),
            "20260101-20260201",
        )
        self.assertEqual(command[3], "backtesting")
        self.assertIn("--timerange", command)
        download = runner.download_data_command(
            "binance",
            "futures",
            ["BTC/USDT:USDT"],
            ["5m"],
            Path("data"),
            "20210101-20260101",
        )
        self.assertEqual(download[3], "download-data")
        self.assertIn("--datadir", download)
        self.assertIn("--prepend", download)
        hyperopt = runner.hyperopt_command(
            Path("config.json"), "FvgAtr", Path("strategies"), Path("data"), 10
        )
        self.assertEqual(hyperopt[3], "hyperopt")
        self.assertEqual(
            hyperopt[hyperopt.index("--spaces") + 1 : hyperopt.index("--spaces") + 3],
            ["enter", "exit"],
        )
        custom = runner.hyperopt_command(
            Path("config.json"),
            "FvgAtr",
            Path("strategies"),
            Path("data"),
            10,
            loss_name="StudioGoalHyperOptLoss",
            hyperopt_path=Path("hyperopts"),
        )
        self.assertEqual(
            custom[custom.index("--hyperopt-loss") + 1], "StudioGoalHyperOptLoss"
        )
        self.assertIn("--hyperopt-path", custom)

    def test_goal_loss_and_validation_score_reward_trade_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            loss_name, loss_path = runner.write_goal_hyperopt_loss(
                Path(directory),
                {
                    "profile": "higher_frequency",
                    "target_trades_per_year": 200,
                    "max_drawdown_pct": 20,
                    "min_profit_factor": 1.2,
                },
            )
            self.assertEqual(loss_name, "StudioGoalHyperOptLoss")
            source = (loss_path / "StudioGoalHyperOptLoss.py").read_text(
                encoding="utf-8"
            )
            self.assertIn("annualized_trades", source)
            self.assertIn("if frequency_shortfall > 0", source)
            compile(source, "<goal-loss>", "exec")
        high_coverage, _ = runner.validation_stability_score([1.0, 1.1], [20, 20], 10)
        low_coverage, _ = runner.validation_stability_score([1.0, 1.1], [1, 1], 10)
        self.assertGreater(high_coverage, low_coverage)

    def test_validation_snapshot_contains_all_splits(self):
        with tempfile.TemporaryDirectory() as directory:
            setup = templates.make_template_strategy("FVG ATR", "fvg_atr", directory)
            payload = {
                "training": {
                    "backtest": {
                        "metrics": {"Return [%]": 1},
                        "trades": [],
                        "equity_curve": [100, 101],
                    }
                },
                "tests": [
                    {
                        "label": "Test 1",
                        "backtest": {
                            "metrics": {"Return [%]": 2},
                            "trades": [],
                            "equity_curve": [100, 102],
                        },
                    }
                ],
            }
            path = Path(directory) / "validation.sqlite3"
            storage.save_validation_file(setup, payload, path)
            self.assertEqual(
                snapshots.load_freqtrade_snapshot(path)["validations"], [payload]
            )

    def test_templates_compose_entry_and_dynamic_exit_parameters(self):
        with tempfile.TemporaryDirectory() as directory:
            for entry in templates.list_entries():
                for exit_rule in templates.list_exits():
                    setup = templates.make_template_strategy(
                        "Test", "fvg_atr", directory, entry["id"], exit_rule["id"]
                    )
                    self.assertEqual(setup.freqtrade_payload["entry_id"], entry["id"])
                    self.assertEqual(
                        setup.freqtrade_payload["exit_id"], exit_rule["id"]
                    )
                    compile(
                        setup.freqtrade_payload["strategy_source"], "<strategy>", "exec"
                    )

    def test_blank_template_name_uses_compact_strategy_context(self):
        setup = templates.make_template_strategy(
            "",
            "fvg_atr",
            ".",
            "fvg",
            "atr_trailing",
            "futures",
            "BTC/USDT:USDT,ETH/USDT:USDT",
            "5m,1h",
        )
        self.assertRegex(setup.name, r"^FVG-ATR-Futures-BTC-USDT-5m-\d{8}-\d{6}$")
        self.assertTrue(all(item["file_label"] for item in templates.list_entries()))
        self.assertTrue(all(item["file_label"] for item in templates.list_exits()))

    def test_bakes_hyperopt_values_and_safe_stoploss_into_strategy_source(self):
        source = templates.make_template_strategy(
            "FVG", "fvg_atr", "."
        ).freqtrade_payload["strategy_source"]
        parameter_file = runner.normalize_parameter_file(
            {
                "params": {
                    "enter": {"ema_period": 42},
                    "exit": {"initial_stop_loss_pct": 0.05},
                    "stoploss": {"stoploss": -0.15},
                }
            }
        )
        baked = runner.apply_parameter_file_to_source(source, parameter_file)
        self.assertIn("stoploss = -0.25", baked)
        self.assertIn("ema_period = IntParameter(5, 300, default=42", baked)
        self.assertIn(
            "initial_stop_loss_pct = DecimalParameter(0.01, 0.15, default=0.05", baked
        )
        self.assertEqual(
            runner.normalize_parameter_file(
                {"params": {"exit": {"initial_stop_loss_pct": 0.19}}}
            )["params"]["exit"]["initial_stop_loss_pct"],
            0.15,
        )

    def test_clamps_saved_hyperopt_values_to_current_catalog_ranges(self):
        source = templates.make_template_strategy(
            "FVG", "fvg_atr", "."
        ).freqtrade_payload["strategy_source"]
        baked = runner.apply_parameter_file_to_source(
            source,
            {
                "params": {
                    "enter": {
                        "fvg_minimum_gap_pct": 0.0883,
                        "fvg_maximum_gap_pct": 0.2547,
                        "ema_period": 500,
                    }
                }
            },
        )
        self.assertIn(
            "fvg_minimum_gap_pct = DecimalParameter(0.0005, 0.0095, default=0.0095",
            baked,
        )
        self.assertIn(
            "fvg_maximum_gap_pct = DecimalParameter(0.01, 0.05, default=0.05",
            baked,
        )
        self.assertIn("ema_period = IntParameter(5, 300, default=300", baked)

    def test_reports_when_frequency_goal_is_not_feasible(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "user_data" / "hyperopt_results"
            results.mkdir(parents=True)
            records = [
                {
                    "current_epoch": 1,
                    "is_best": True,
                    "loss": 1,
                    "results_metrics": {
                        "total_trades": 12,
                        "profit_total": 0.03,
                        "profit_factor": 1.3,
                        "max_drawdown_account": 0.02,
                    },
                },
                {
                    "current_epoch": 2,
                    "loss": 2,
                    "params_details": {"enter": {"enter_ema_period": 42}},
                    "params_not_optimized": {"stoploss": {"stoploss": -0.25}},
                    "results_metrics": {
                        "total_trades": 30,
                        "profit_total": -0.1,
                        "profit_factor": 0.8,
                        "max_drawdown_account": 0.03,
                    },
                },
            ]
            (results / "strategy_Test_1.fthypt").write_text(
                "\n".join(__import__("json").dumps(record) for record in records),
                encoding="utf-8",
            )
            report, parameter_file = runner.read_hyperopt_report(
                Path(directory),
                "Test",
                "20250101-20260101",
                {
                    "profile": "higher_frequency",
                    "target_trades_per_year": 100,
                    "max_drawdown_pct": 25,
                    "min_profit_factor": 1.1,
                },
            )
            self.assertFalse(report.goal_met)
            self.assertEqual(report.max_observed_trades, 30)
            self.assertEqual(report.best_trade_count, 30)
            self.assertEqual(report.selection_status, "infeasible_closest_frequency")
            self.assertEqual(parameter_file["strategy_name"], "Test")
            self.assertEqual(parameter_file["params"]["enter"]["enter_ema_period"], 42)

    def test_prefers_a_feasible_hyperopt_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            results = Path(directory) / "user_data" / "hyperopt_results"
            results.mkdir(parents=True)
            records = [
                {
                    "current_epoch": 1,
                    "loss": 3,
                    "params_details": {"enter": {"enter_ema_period": 12}},
                    "results_metrics": {
                        "total_trades": 120,
                        "profit_total": 0.02,
                        "profit_factor": 1.2,
                        "max_drawdown_account": 0.02,
                    },
                },
                {
                    "current_epoch": 2,
                    "loss": 1,
                    "params_details": {"enter": {"enter_ema_period": 24}},
                    "results_metrics": {
                        "total_trades": 130,
                        "profit_total": 0.03,
                        "profit_factor": 1.4,
                        "max_drawdown_account": 0.02,
                    },
                },
            ]
            (results / "strategy_Test_1.fthypt").write_text(
                "\n".join(__import__("json").dumps(record) for record in records),
                encoding="utf-8",
            )
            report, parameter_file = runner.read_hyperopt_report(
                Path(directory),
                "Test",
                "20250101-20260101",
                {
                    "profile": "higher_frequency",
                    "target_trades_per_year": 100,
                    "max_drawdown_pct": 25,
                    "min_profit_factor": 1.1,
                },
            )
            self.assertTrue(report.goal_met)
            self.assertEqual(report.selection_status, "feasible")
            self.assertEqual(parameter_file["params"]["enter"]["enter_ema_period"], 24)

    def test_rebacktest_trade_count_mismatch_rejects_the_hyperopt_result(self):
        report = models.OptimizationReport(
            target_trades_per_year=100,
            best_trade_count=6,
            best_annualized_trades=6,
            max_observed_trades=20,
            max_observed_annualized_trades=20,
            feasible_candidate_count=0,
            goal_met=False,
            summary="Infeasible",
        )
        with self.assertRaisesRegex(
            ValueError, "Hyperopt parameter handoff verification failed"
        ):
            runner.reconcile_optimization_report(report, 7, "20251030-20261029")

    def test_node_catalog_uses_feasible_fvg_ranges_and_fixed_constants(self):
        nodes = {node.id: node for node in NODES}
        fvg = {parameter.key: parameter for parameter in nodes["pattern.fair_value_gap"].parameters}
        self.assertLess(fvg["minimum_gap_pct"].maximum, fvg["maximum_gap_pct"].minimum)
        constant = nodes["input.constant"].parameters[0]
        self.assertFalse(constant.optimizable)

    def test_graph_parameters_reject_invalid_linked_parameter_values(self):
        graph = StrategyGraph(
            nodes=(
                GraphNode(
                    "invalid_fvg",
                    "pattern.fair_value_gap",
                    {"minimum_gap_pct": 0.01, "maximum_gap_pct": 0.01},
                ),
            ),
            edges=(),
        )
        with self.assertRaisesRegex(GraphCompileError, "minimum_gap_pct"):
            graph_parameters(graph)

    def test_generates_safe_workspace_config_when_not_supplied(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = runner.ensure_config(
                "", Path(directory), "binance", "futures", ["BTC/USDT:USDT"], ["5m"]
            )
            config = __import__("json").loads(config_path.read_text(encoding="utf-8"))
            self.assertTrue(config["dry_run"])
            self.assertEqual(config["exchange"]["pair_whitelist"], ["BTC/USDT:USDT"])
            self.assertEqual(config["trading_mode"], "futures")
            self.assertEqual(config["entry_pricing"]["price_side"], "same")
            self.assertEqual(config["exit_pricing"]["price_side"], "same")
            self.assertTrue(config["entry_pricing"]["use_order_book"])
            self.assertTrue(config["exit_pricing"]["use_order_book"])

    def test_initializes_freqtrade_user_data_directory(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(runner, "run") as run_command,
        ):
            user_data = runner.ensure_userdir(Path(directory))
            self.assertEqual(user_data, Path(directory) / "user_data")
            run_command.assert_called_once_with(
                runner.userdir_command(user_data), Path(directory)
            )

    def test_reads_freqtrade_zip_backtest_result(self):
        with tempfile.TemporaryDirectory() as directory:
            result_dir = Path(directory)
            archive = result_dir / "backtest-result-2026-10-29_05-10-00.zip"
            with ZipFile(archive, "w") as output:
                output.writestr(
                    "backtest-result-2026-10-29_05-10-00.json",
                    '{"strategy": {"Test": {"starting_balance": 100, "profit_total": 0.1, "trades": []}}}',
                )
                output.writestr("backtest-result-2026-10-29_05-10-00_config.json", "{}")
            (result_dir / ".last_result.json").write_text(
                '{"latest_backtest": "backtest-result-2026-10-29_05-10-00.zip"}',
                encoding="utf-8",
            )
            self.assertEqual(
                runner.parse_backtest_directory(result_dir)["metrics"]["Return [%]"],
                10.0,
            )

    def test_walk_forward_ranges_reserve_training_and_ten_tests(self):
        training, tests = runner.walk_forward_ranges(
            datetime(2021, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.assertTrue(training.startswith("20210101T0000-"))
        self.assertEqual(len(tests), 10)
        self.assertTrue(tests[0].startswith(training.split("-")[1]))
        self.assertEqual(
            len(
                runner.walk_forward_ranges(
                    datetime(2021, 1, 1, tzinfo=timezone.utc),
                    datetime(2026, 1, 1, tzinfo=timezone.utc),
                    5,
                )[1]
            ),
            5,
        )

    def test_uses_local_candle_cache_only_when_it_covers_the_requested_range(self):
        with patch.object(
            runner,
            "available_candle_range",
            return_value=(
                datetime(2021, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 11, 2, tzinfo=timezone.utc),
            ),
        ):
            self.assertTrue(
                runner.data_covers_timerange(
                    Path("data"), ["BTC/USDT:USDT"], ["5m"], "20231029-20261029"
                )
            )
            self.assertFalse(
                runner.data_covers_timerange(
                    Path("data"), ["BTC/USDT:USDT"], ["5m"], "20201029-20261029"
                )
            )

    def test_cancels_running_freqtrade_command_without_returning_output(self):
        cancelled = Event()
        cancelled.set()
        with self.assertRaises(runner.RunCancelled):
            runner.run(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                Path.cwd(),
                cancelled,
            )

    def test_streams_command_output_to_progress_callback(self):
        lines: list[str] = []
        runner.run(
            [sys.executable, "-c", "print('Epoch 1/2')"],
            Path.cwd(),
            on_output=lines.append,
        )
        self.assertEqual(lines, ["Epoch 1/2\n"])

    def test_polls_running_command_when_output_is_not_line_based(self):
        polls: list[bool] = []
        runner.run(
            [sys.executable, "-c", "import time; time.sleep(.3)"],
            Path.cwd(),
            on_poll=lambda: polls.append(True),
        )
        self.assertTrue(polls)


if __name__ == "__main__":
    unittest.main()
