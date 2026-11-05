<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  BadgeCheck,
  Bot,
  ChartLine,
  ChartNoAxesCombined,
  FileText,
  FolderOpen,
  RotateCcw,
  Settings,
  SlidersHorizontal,
} from "@lucide/vue";
import { open, save } from "@tauri-apps/plugin-dialog";
import { pyInvoke } from "tauri-plugin-pytauri-api";
import EquityChart from "./components/EquityChart.vue";
import PathInput from "./components/PathInput.vue";
import StrategyGraph from "./components/StrategyGraph.vue";
import strataraSymbol from "./assets/stratara-symbol.png";
import LogsPage from "./pages/LogsPage.vue";
import SettingsPage from "./pages/SettingsPage.vue";

type Parameter = {
  name: string;
  value: string;
  notes: string;
  enabled: boolean;
  locked: boolean;
};
type Strategy = {
  id?: number;
  name: string;
  source: string;
  workspace_path: string;
  template_id: string;
  parameters: Parameter[];
  freqtrade_payload?: Record<string, unknown>;
  strategy_file?: string | null;
};
type Backtest = {
  id: number;
  name: string;
  imported_at: string;
  metrics: Record<string, unknown>;
  trades: Record<string, unknown>[];
  equity_curve: number[];
  equity_timestamps: string[];
};
type OptimizationReport = {
  target_trades_per_year: number;
  best_trade_count: number;
  best_annualized_trades: number;
  max_observed_trades: number;
  max_observed_annualized_trades: number;
  feasible_candidate_count: number;
  goal_met: boolean;
  selection_status: string;
  summary: string;
};
type StrategyRun = {
  strategy: Strategy;
  backtest: Backtest | null;
  output: string;
  error?: string | null;
  optimization_report?: OptimizationReport | null;
};
type ValidationSlice = { label: string; timerange: string; backtest: Backtest };
type OptimizationGoal = {
  profile:
    | "balanced"
    | "higher_frequency"
    | "return_focused"
    | "capital_preservation";
  target_trades_per_year: number;
  min_trades_per_test: number;
  max_drawdown_pct: number;
  min_profit_factor: number;
};
type ValidationRun = {
  training: ValidationSlice;
  tests: ValidationSlice[];
  stability_score: number;
  mean_return: number;
  return_stddev: number;
  total_test_trades: number;
  minimum_test_trades: number;
  coverage: string;
  output: string;
  snapshot_path?: string | null;
};
type Dataset = { path: string; bytes: number };
type ApiKeyStatus = {
  configured: boolean;
  source: string;
  cache_configured: boolean;
  environment_configured: boolean;
};
type ClearKind = "backtests" | "hyperopts" | "validations";
type Template = {
  id: string;
  label: string;
  entry_id: string;
  exit_id: string;
};
type StrategyComponent = {
  id: string;
  label: string;
  file_label: string;
  description: string;
};
type SortDirection = "asc" | "desc" | null;
type StrategyGraphSchema = {
  version: number;
  nodes: { id: string; type: string; parameters?: Record<string, unknown> }[];
  edges: {
    source_node: string;
    source_port: string;
    target_node: string;
    target_port: string;
  }[];
};
type StrategyNodePort = {
  key: string;
  value_type: string;
  required?: boolean;
  description?: string;
};
type StrategyNodeParameter = {
  key: string;
  value_type: "integer" | "decimal" | "boolean" | "choice";
  default: string | number | boolean;
  description: string;
  minimum?: number | null;
  maximum?: number | null;
  decimals?: number | null;
  choices?: string[];
  optimizable?: boolean;
};
type StrategyNodeCatalog = {
  version: number;
  nodes: {
    id: string;
    group: string;
    label: string;
    description: string;
    inputs: StrategyNodePort[];
    outputs: StrategyNodePort[];
    parameters: StrategyNodeParameter[];
  }[];
};
type ParameterView = "parameters" | "nodes" | "json";
type CreationMode = "manual" | "ai";
type PageId = "builder" | "optimizer" | "validation" | "logs" | "settings";

const strategy = ref<Strategy>({
  name: "",
  source: "",
  workspace_path: "",
  template_id: "fvg_atr",
  parameters: [],
});
const templates = ref<Template[]>([]);
const entries = ref<StrategyComponent[]>([]);
const exits = ref<StrategyComponent[]>([]);
const nodeCatalog = ref<StrategyNodeCatalog>({ version: 1, nodes: [] });
const entryId = ref("fvg");
const exitId = ref("atr_trailing");
const history = ref<Backtest[]>([]);
const datasets = ref<Dataset[]>([]);
const selected = ref<Backtest | null>(null);
const configPath = ref("");
function calendarTimerange(years: number) {
  const end = new Date();
  const start = new Date(end);
  start.setFullYear(end.getFullYear() - years);
  const format = (value: Date) =>
    `${value.getFullYear()}${String(value.getMonth() + 1).padStart(2, "0")}${String(value.getDate()).padStart(2, "0")}`;
  return `${format(start)}-${format(end)}`;
}
function calendarTimerangeMonths(months: number) {
  const end = new Date();
  const start = new Date(end);
  start.setMonth(start.getMonth() - months);
  const format = (value: Date) =>
    `${value.getFullYear()}${String(value.getMonth() + 1).padStart(2, "0")}${String(value.getDate()).padStart(2, "0")}`;
  return `${format(start)}-${format(end)}`;
}
const timerange = ref(calendarTimerange(1));
const validationTimerange = ref(calendarTimerange(5));
const quickValidationTimerange = ref(calendarTimerangeMonths(30));
const epochs = ref(100);
const optimizationGoal = ref<OptimizationGoal>({
  profile: "balanced",
  target_trades_per_year: 100,
  min_trades_per_test: 10,
  max_drawdown_pct: 25,
  min_profit_factor: 1.1,
});
const optimizationReport = ref<OptimizationReport | null>(null);
const exchange = ref("binance");
const tradingMode = ref("futures");
const pairs = ref("BTC/USDT:USDT");
const timeframes = ref("5m");
const output = ref("");
const error = ref("");
const busy = ref(false);
const resultVersion = ref(0);
const openAiApiKeyStatus = ref<ApiKeyStatus>({
  configured: false,
  source: "",
  cache_configured: false,
  environment_configured: false,
});
const savingOpenAiApiKey = ref(false);
const activeTab = ref<PageId>("builder");
const creationMode = ref<CreationMode>("manual");
const hasLoadedStrategy = computed(() =>
  Boolean(
    strategy.value.strategy_file ||
      strategy.value.name ||
      strategy.value.source ||
      strategy.value.parameters.length,
  ),
);
const clearingKind = ref("");
const pendingClearKind = ref<ClearKind | null>(null);
const validation = ref<ValidationRun | null>(null);
type Progress = {
  active: boolean;
  label: string;
  percent: number;
  sub_label: string;
  sub_percent: number;
  steps: string[];
  output: string;
};
const progress = ref<Progress | null>(null);
let progressPoller: number | undefined;
const sortColumn = ref<string | null>(null);
const sortDirection = ref<SortDirection>(null);
const page = ref(1);
const perPage = 25;
const nameClock = ref(Date.now());
let nameClockTimer: number | undefined;
const parameterView = ref<ParameterView>("parameters");
const navItems = [
  { id: "builder", label: "Builder", icon: ChartLine },
  { id: "optimizer", label: "Optimizer", icon: SlidersHorizontal },
  { id: "validation", label: "Validation", icon: BadgeCheck },
  { id: "logs", label: "Logs", icon: FileText },
  { id: "settings", label: "Settings", icon: Settings },
] as const;
const strategyGraph = computed<StrategyGraphSchema | null>(() => {
  const graph = strategy.value.freqtrade_payload?.graph;
  if (!graph || typeof graph !== "object") return null;
  const candidate = graph as Partial<StrategyGraphSchema>;
  return Array.isArray(candidate.nodes) && Array.isArray(candidate.edges)
    ? (candidate as StrategyGraphSchema)
    : null;
});
const strategyGraphJson = computed(() =>
  strategyGraph.value
    ? JSON.stringify(strategyGraph.value, null, 2)
    : "No node graph is available for this strategy.",
);

function generatedName(now = new Date()) {
  const entry =
    entries.value.find((item) => item.id === entryId.value)?.file_label ||
    "Entry";
  const exit =
    exits.value.find((item) => item.id === exitId.value)?.file_label || "Exit";
  const pair = (pairs.value.split(",").find((item) => item.trim()) || "market")
    .trim()
    .split(":", 1)[0]
    .replace("/", "-");
  const timeframe = (
    timeframes.value.split(",").find((item) => item.trim()) || "timeframe"
  ).trim();
  const market =
    (
      { futures: "Futures", margin: "Margin", spot: "Spot" } as Record<
        string,
        string
      >
    )[tradingMode.value] || "Market";
  const date = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}`;
  const time = `${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`;
  return `${entry}-${exit}-${market}-${pair}-${timeframe}-${date}-${time}`;
}

const generatedNamePreview = computed(() => {
  nameClock.value;
  return generatedName();
});

async function call<T>(command: string, body?: unknown) {
  error.value = "";
  return pyInvoke<T>(command, body);
}

async function refreshProgress() {
  try {
    const current = await pyInvoke<Progress>("get_freqtrade_progress");
    if (current.active || busy.value) {
      progress.value = current;
      output.value = current.output;
    }
  } catch {
    // Browser previews do not have the PyTauri command bridge.
  }
}

function startProgress(label: string) {
  progress.value = {
    active: true,
    label,
    percent: 0,
    sub_label: "Preparing",
    sub_percent: 0,
    steps: [label],
    output: "",
  };
  if (progressPoller === undefined)
    progressPoller = window.setInterval(() => void refreshProgress(), 350);
}

function stopProgress() {
  if (progressPoller !== undefined) window.clearInterval(progressPoller);
  progressPoller = undefined;
  progress.value = null;
}

async function cancelRun() {
  try {
    await pyInvoke<boolean>("cancel_freqtrade_run");
    if (progress.value)
      progress.value = {
        ...progress.value,
        label: "Stopping Freqtrade process",
        sub_label: "Terminating the active Freqtrade process tree",
        steps: [...progress.value.steps, "Stopping Freqtrade process"],
      };
  } catch (cause) {
    error.value = String(cause);
  }
}

async function refresh() {
  const [
    workspace,
    savedTemplates,
    savedEntries,
    savedExits,
    savedHistory,
    savedNodeCatalog,
    apiKeyStatus,
  ] = await Promise.all([
    call<string>("default_workspace"),
    call<Template[]>("list_freqtrade_templates"),
    call<StrategyComponent[]>("list_freqtrade_entries"),
    call<StrategyComponent[]>("list_freqtrade_exits"),
    call<Backtest[]>("list_imported_backtests"),
    call<StrategyNodeCatalog>("get_strategy_node_catalog"),
    call<ApiKeyStatus>("get_openai_api_key_status"),
  ]);
  if (!strategy.value.workspace_path) strategy.value.workspace_path = workspace;
  templates.value = savedTemplates;
  entries.value = savedEntries;
  exits.value = savedExits;
  history.value = savedHistory;
  nodeCatalog.value = savedNodeCatalog;
  openAiApiKeyStatus.value = apiKeyStatus;
  datasets.value = await call<Dataset[]>("list_freqtrade_datasets", {
    workspace_path: strategy.value.workspace_path,
  });
}

async function refreshDatasets() {
  datasets.value = await call<Dataset[]>("list_freqtrade_datasets", {
    workspace_path: strategy.value.workspace_path,
  });
}

function requestClear(kind: ClearKind) {
  pendingClearKind.value = kind;
}

async function clearResults() {
  const kind = pendingClearKind.value;
  if (!kind) return;
  pendingClearKind.value = null;
  clearingKind.value = kind;
  startProgress(`Preparing ${kind} cleanup`);
  try {
    const result = await call<{ history: number; files: number }>(
      "clear_freqtrade_results",
      { workspace_path: strategy.value.workspace_path, kind },
    );
    output.value = `Cleared ${kind}: ${result.history} history record(s) and ${result.files} local artifact(s) moved to the Recycle Bin.`;
    selected.value = null;
    validation.value = null;
    await refresh();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    clearingKind.value = "";
    stopProgress();
  }
}

function loadSettings() {
  Promise.all([
    refreshDatasets(),
    call<ApiKeyStatus>("get_openai_api_key_status").then(
      (status) => (openAiApiKeyStatus.value = status),
    ),
  ]).catch((cause) => (error.value = String(cause)));
}

function navigate(page: PageId) {
  activeTab.value = page;
  if (page === "settings") loadSettings();
}

async function saveOpenAiApiKey(apiKey: string) {
  if (!apiKey.trim()) return;
  savingOpenAiApiKey.value = true;
  try {
    openAiApiKeyStatus.value = await call<ApiKeyStatus>("save_openai_api_key", {
      api_key: apiKey.trim(),
    });
  } catch (cause) {
    error.value = String(cause);
  } finally {
    savingOpenAiApiKey.value = false;
  }
}

async function clearOpenAiApiKey() {
  savingOpenAiApiKey.value = true;
  try {
    openAiApiKeyStatus.value = await call<ApiKeyStatus>("clear_openai_api_key");
  } catch (cause) {
    error.value = String(cause);
  } finally {
    savingOpenAiApiKey.value = false;
  }
}

function applyPreset() {
  const preset = templates.value.find(
    (item) => item.id === strategy.value.template_id,
  );
  if (!preset) return;
  entryId.value = preset.entry_id;
  exitId.value = preset.exit_id;
}

function syncPreset() {
  strategy.value.template_id =
    templates.value.find(
      (item) =>
        item.entry_id === entryId.value && item.exit_id === exitId.value,
    )?.id || "custom";
}

function updateStrategyGraph(graph: StrategyGraphSchema) {
  strategy.value = {
    ...strategy.value,
    freqtrade_payload: {
      ...(strategy.value.freqtrade_payload ?? {}),
      graph,
    },
  };
  resultVersion.value += 1;
  output.value =
    "Node graph updated. Its connections will be validated and compiled on the next run.";
}

async function createTemplate() {
  busy.value = true;
  try {
    nameClock.value = Date.now();
    strategy.value = await call<Strategy>("create_freqtrade_template", {
      name: strategy.value.name.trim() || generatedNamePreview.value,
      template_id: strategy.value.template_id,
      entry_id: entryId.value,
      exit_id: exitId.value,
      workspace_path: strategy.value.workspace_path,
      trading_mode: tradingMode.value,
      pairs: pairs.value,
      timeframes: timeframes.value,
    });
    resultVersion.value += 1;
    output.value =
      "Template created. Its parameter schema is deterministic and ready for Freqtrade hyperopt.";
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
  }
}

async function createAiStrategy() {
  if (!strategy.value.source.trim()) {
    error.value = "Enter a strategy brief before generating an AI strategy.";
    return;
  }
  busy.value = true;
  startProgress("Generating AI strategy");
  try {
    strategy.value = await call<Strategy>("create_ai_strategy", {
      prompt: strategy.value.source,
      workspace_path: strategy.value.workspace_path,
      exchange: exchange.value,
      trading_mode: tradingMode.value,
      pairs: pairs.value,
      timeframes: timeframes.value,
      timerange: timerange.value,
    });
    parameterView.value = "nodes";
    resultVersion.value += 1;
    output.value =
      "AI strategy generated, validated against the local node catalog, and saved locally.";
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
    stopProgress();
  }
}

async function copyGraphJson() {
  try {
    await navigator.clipboard.writeText(strategyGraphJson.value);
    output.value = "Node graph JSON copied to the clipboard.";
  } catch (cause) {
    error.value = `Unable to copy node graph JSON: ${String(cause)}`;
  }
}

async function copyRunOutput() {
  try {
    await navigator.clipboard.writeText(output.value);
  } catch (cause) {
    error.value = `Unable to copy run output: ${String(cause)}`;
  }
}

async function exportRunOutput() {
  if (!output.value) return;
  const path = await save({
    defaultPath: "backtest-studio.log",
    filters: [{ name: "Log file", extensions: ["log", "txt"] }],
  });
  if (typeof path !== "string") return;
  try {
    await call<string>("export_run_log", {
      destination: path,
      content: output.value,
    });
  } catch (cause) {
    error.value = `Unable to export run output: ${String(cause)}`;
  }
}

async function chooseConfig() {
  const path = await open({
    filters: [{ name: "Freqtrade config", extensions: ["json"] }],
    multiple: false,
  });
  if (typeof path === "string") configPath.value = path;
}

async function chooseWorkspace() {
  const path = await open({
    defaultPath: strategy.value.workspace_path,
    directory: true,
    multiple: false,
  });
  if (typeof path === "string") strategy.value.workspace_path = path;
}

function serializableStrategy() {
  return JSON.parse(JSON.stringify(strategy.value)) as Strategy;
}

function serializableGoal(): OptimizationGoal {
  return { ...optimizationGoal.value };
}

function hydrateGoal(next: unknown) {
  if (!next || typeof next !== "object") return;
  const value = next as Partial<OptimizationGoal>;
  if (
    [
      "balanced",
      "higher_frequency",
      "return_focused",
      "capital_preservation",
    ].includes(String(value.profile))
  )
    optimizationGoal.value.profile =
      value.profile as OptimizationGoal["profile"];
  for (const key of [
    "target_trades_per_year",
    "min_trades_per_test",
    "max_drawdown_pct",
    "min_profit_factor",
  ] as const) {
    if (typeof value[key] === "number" && Number.isFinite(value[key]))
      optimizationGoal.value[key] = value[key];
  }
}

async function run(hyperopt = false) {
  busy.value = true;
  output.value = "";
  startProgress(hyperopt ? "Starting optimization" : "Starting backtest");
  try {
    const run = await call<StrategyRun>("run_freqtrade_backtest", {
      strategy: serializableStrategy(),
      config_path: configPath.value,
      exchange: exchange.value,
      trading_mode: tradingMode.value,
      pairs: pairs.value,
      timeframes: timeframes.value,
      timerange: timerange.value,
      hyperopt_epochs: hyperopt ? epochs.value : 0,
      optimization_goal: serializableGoal(),
    });
    strategy.value = run.strategy;
    entryId.value = String(
      run.strategy.freqtrade_payload?.entry_id || entryId.value,
    );
    exitId.value = String(
      run.strategy.freqtrade_payload?.exit_id || exitId.value,
    );
    hydrateGoal(run.strategy.freqtrade_payload?.optimization_goal);
    optimizationReport.value =
      run.optimization_report ||
      (run.strategy.freqtrade_payload?.optimization_report as
        | OptimizationReport
        | undefined) ||
      null;
    output.value = run.output;
    if (run.error) error.value = run.error;
    if (run.backtest) selected.value = run.backtest;
    resultVersion.value += 1;
    await refresh();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
    stopProgress();
  }
}

async function runValidation(quick = false) {
  busy.value = true;
  startProgress(
    quick ? "Starting quick validation" : "Starting walk-forward validation",
  );
  try {
    validation.value = await call<ValidationRun>("run_freqtrade_validation", {
      strategy: serializableStrategy(),
      config_path: configPath.value,
      exchange: exchange.value,
      trading_mode: tradingMode.value,
      pairs: pairs.value,
      timeframes: timeframes.value,
      timerange: quick
        ? quickValidationTimerange.value
        : validationTimerange.value,
      validation_test_count: quick ? 5 : 10,
      optimization_goal: serializableGoal(),
    });
    selected.value = validation.value.training.backtest;
    resultVersion.value += 1;
    output.value = validation.value.output;
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
    stopProgress();
  }
}

async function chooseSnapshot() {
  const path = await open({
    defaultPath: strategy.value.workspace_path,
    filters: [
      { name: "Freqtrade snapshot", extensions: ["sqlite", "sqlite3"] },
    ],
    multiple: false,
  });
  if (typeof path !== "string") return;
  try {
    const run = await call<StrategyRun>("load_strategy_save_file", { path });
    strategy.value = run.strategy;
    entryId.value = String(
      run.strategy.freqtrade_payload?.entry_id || entryId.value,
    );
    exitId.value = String(
      run.strategy.freqtrade_payload?.exit_id || exitId.value,
    );
    hydrateGoal(run.strategy.freqtrade_payload?.optimization_goal);
    optimizationReport.value =
      (run.strategy.freqtrade_payload?.optimization_report as
        | OptimizationReport
        | undefined) || null;
    selected.value = run.backtest;
    resultVersion.value += 1;
    output.value = run.output;
  } catch (cause) {
    error.value = String(cause);
  }
}

function clearStrategy() {
  const workspacePath = strategy.value.workspace_path;
  strategy.value = {
    name: "",
    source: "",
    workspace_path: workspacePath,
    template_id: "fvg_atr",
    parameters: [],
  };
  entryId.value = "fvg";
  exitId.value = "atr_trailing";
  optimizationReport.value = null;
  selected.value = null;
  validation.value = null;
  parameterView.value = "parameters";
  error.value = "";
  output.value = "Loaded strategy cleared.";
  resultVersion.value += 1;
}

function selectHistory(item: Backtest) {
  selected.value = item;
  page.value = 1;
  sortColumn.value = null;
  sortDirection.value = null;
}
function toggleSort(column: string) {
  sortDirection.value =
    sortColumn.value === column
      ? sortDirection.value === "asc"
        ? "desc"
        : sortDirection.value === "desc"
          ? null
          : "asc"
      : "asc";
  sortColumn.value = sortDirection.value ? column : null;
  page.value = 1;
}
const tradeColumns = computed(() =>
  Array.from(
    new Set(
      (selected.value?.trades ?? []).flatMap((item) => Object.keys(item)),
    ),
  ),
);
const sortedTrades = computed(() => {
  const items = [...(selected.value?.trades ?? [])];
  if (!sortColumn.value || !sortDirection.value) return items;
  return items.sort(
    (left, right) =>
      String(left[sortColumn.value!]).localeCompare(
        String(right[sortColumn.value!]),
        undefined,
        { numeric: true },
      ) * (sortDirection.value === "asc" ? 1 : -1),
  );
});
const visibleTrades = computed(() =>
  sortedTrades.value.slice((page.value - 1) * perPage, page.value * perPage),
);
const pageCount = computed(() =>
  Math.max(1, Math.ceil(sortedTrades.value.length / perPage)),
);
function metricValue(value: unknown) {
  return typeof value === "number"
    ? value.toLocaleString(undefined, { maximumFractionDigits: 4 })
    : String(value ?? "—");
}
function numericValue(value: unknown) {
  return typeof value === "number"
    ? value
    : typeof value === "string" && value.trim() !== ""
      ? Number(value)
      : Number.NaN;
}
function valueTone(label: string, value: unknown) {
  const key = label.toLowerCase();
  if (key === "side" || key === "is_short") {
    const side = String(value).toLowerCase();
    return side === "short" || side === "sell" || value === true
      ? "text-error"
      : side === "long" || side === "buy" || value === false
        ? "text-success"
        : "text-base-content";
  }
  if (
    !/(profit|p\/l|pnl|return|win.?rate|sharpe|sortino|drawdown|loss|factor)/.test(
      key,
    )
  )
    return "text-base-content";
  const numeric = numericValue(value);
  if (Number.isNaN(numeric)) return "text-base-content";
  if (key.includes("win"))
    return numeric >= 40
      ? "text-success"
      : numeric >= 30
        ? "text-warning"
        : "text-error";
  if (key.includes("factor"))
    return numeric >= 1.2
      ? "text-success"
      : numeric >= 1
        ? "text-warning"
        : "text-error";
  if (key.includes("sharpe") || key.includes("sortino"))
    return numeric >= 1
      ? "text-success"
      : numeric >= 0
        ? "text-warning"
        : "text-error";
  if (key.includes("drawdown"))
    return Math.abs(numeric) <= 15
      ? "text-success"
      : Math.abs(numeric) <= 30
        ? "text-warning"
        : "text-error";
  return numeric > 0
    ? "text-success"
    : numeric < 0
      ? "text-error"
      : "text-warning";
}
function tableValue(column: string, value: unknown) {
  if (column.toLowerCase() === "is_short" && typeof value === "boolean")
    return value ? "Short" : "Long";
  return metricValue(value);
}

onMounted(() => {
  nameClockTimer = window.setInterval(
    () => (nameClock.value = Date.now()),
    1000,
  );
  refresh().catch((cause) => (error.value = String(cause)));
});
onBeforeUnmount(() => {
  stopProgress();
  if (nameClockTimer !== undefined) window.clearInterval(nameClockTimer);
});
</script>

<template>
  <div class="min-h-screen bg-base-300">
    <aside
      class="fixed inset-y-0 left-0 z-40 flex w-18 flex-col border-r border-base-300 bg-base-200 py-5"
    >
      <nav
        class="flex flex-col items-center gap-3"
        aria-label="Studio workflow"
      >
        <div v-for="item in navItems" :key="item.id" class="group relative">
          <button
            class="btn btn-square btn-ghost btn-lg border-none bg-transparent text-base-content transition-colors hover:bg-base-300 focus-visible:bg-base-300"
            :class="
              activeTab === item.id
                ? 'bg-white text-neutral shadow-sm hover:bg-white focus-visible:bg-white'
                : ''
            "
            type="button"
            :aria-label="item.label"
            :aria-current="activeTab === item.id ? 'page' : undefined"
            @click="navigate(item.id)"
          >
            <component
              :is="item.icon"
              class="size-7"
              :stroke-width="2"
              aria-hidden="true"
            />
          </button>
          <span
            role="tooltip"
            class="pointer-events-none absolute top-1/2 left-full z-50 ml-3 -translate-x-2 -translate-y-1/2 whitespace-nowrap rounded-box bg-neutral px-3 py-1.5 text-sm text-neutral-content opacity-0 transition-all duration-150 group-hover:translate-x-0 group-hover:opacity-100"
            >{{ item.label }}</span
          >
        </div>
      </nav>
    </aside>
    <main class="ml-18 min-h-screen px-4 py-8 sm:px-8">
      <section class="mx-auto max-w-6xl space-y-5">
        <header class="flex items-end justify-between gap-4">
          <div class="flex items-center gap-3">
            <img
              :src="strataraSymbol"
              alt="Stratara"
              class="size-12 shrink-0"
            />
            <div>
              <p class="text-sm text-base-content/60">
                Local Freqtrade strategy studio
              </p>
              <h1 class="text-3xl font-semibold">Stratara</h1>
              <p class="mt-1 text-base-content/70">
                Create deterministic strategies, run native Freqtrade backtests
                and hyperopt, then export portable snapshots.
              </p>
            </div>
          </div>
          <div
            v-if="
              activeTab === 'builder' ||
              activeTab === 'optimizer' ||
              activeTab === 'validation'
            "
            class="flex shrink-0 gap-2"
          >
            <button
              class="btn btn-square btn-md"
              type="button"
              :disabled="busy"
              aria-label="Load strategy snapshot"
              title="Load strategy snapshot"
              @click="chooseSnapshot"
            >
              <FolderOpen class="size-5" :stroke-width="2" aria-hidden="true" />
            </button>
            <button
              class="btn btn-square btn-md"
              type="button"
              :disabled="busy || !hasLoadedStrategy"
              aria-label="Clear loaded strategy"
              title="Clear loaded strategy"
              @click="clearStrategy"
            >
              <RotateCcw class="size-5" :stroke-width="2" aria-hidden="true" />
            </button>
          </div>
        </header>
        <div v-if="error" role="alert" class="alert alert-error">
          <span>{{ error }}</span>
        </div>
        <section
          v-if="activeTab === 'builder'"
          class="page-enter card bg-base-200"
        >
          <div class="card-body">
            <h2 class="card-title">Strategy builder</h2>
            <div class="mt-4 flex items-center gap-3">
              <div
                role="tablist"
                class="tabs tabs-box w-fit"
                aria-label="Strategy creation mode"
              >
                <button
                  role="tab"
                  class="tab gap-3 py-3 text-base"
                  :class="creationMode === 'manual' ? 'tab-active' : ''"
                  :aria-selected="creationMode === 'manual'"
                  @click="creationMode = 'manual'"
                >
                  <ChartNoAxesCombined
                    class="size-5"
                    :stroke-width="2"
                    aria-hidden="true"
                  />
                  Manual
                </button>
                <button
                  role="tab"
                  class="tab gap-3 py-3 text-base"
                  :class="creationMode === 'ai' ? 'tab-active' : ''"
                  :aria-selected="creationMode === 'ai'"
                  @click="creationMode = 'ai'"
                >
                  <Bot class="size-5" :stroke-width="2" aria-hidden="true" />
                  AI
                </button>
              </div>
            </div>
            <div class="mt-4 grid gap-3 lg:grid-cols-3">
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Name</legend>
                <input
                  v-model="strategy.name"
                  class="input w-full"
                  :placeholder="generatedNamePreview"
                />
              </fieldset>
              <PathInput
                v-model="strategy.workspace_path"
                label="Workspace"
                help="SQLite snapshots and generated strategy files stay here."
                browse-label="Choose workspace folder"
                @browse="chooseWorkspace"
              />
              <PathInput
                v-model="configPath"
                label="Freqtrade config (optional)"
                placeholder="config.json"
                help="An empty field creates a safe local dry-run config."
                browse-label="Choose Freqtrade config"
                @browse="chooseConfig"
              />
              <fieldset
                v-if="creationMode === 'manual'"
                class="fieldset lg:col-start-1 lg:row-start-2"
              >
                <legend class="fieldset-legend">Preset pairing</legend>
                <select
                  v-model="strategy.template_id"
                  class="select w-full"
                  @change="applyPreset"
                >
                  <option value="custom">Custom selection</option>
                  <option
                    v-for="item in templates"
                    :key="item.id"
                    :value="item.id"
                  >
                    {{ item.label }}
                  </option>
                </select>
              </fieldset>
              <fieldset
                v-if="creationMode === 'manual'"
                class="fieldset lg:col-start-2 lg:row-start-2"
              >
                <legend class="fieldset-legend">Entry</legend>
                <select
                  v-model="entryId"
                  class="select w-full"
                  @change="syncPreset"
                >
                  <option
                    v-for="item in entries"
                    :key="item.id"
                    :value="item.id"
                  >
                    {{ item.label }}
                  </option>
                </select>
                <p class="label">
                  {{ entries.find((item) => item.id === entryId)?.description }}
                </p>
              </fieldset>
              <fieldset
                v-if="creationMode === 'manual'"
                class="fieldset lg:col-start-3 lg:row-start-2"
              >
                <legend class="fieldset-legend">Exit</legend>
                <select
                  v-model="exitId"
                  class="select w-full"
                  @change="syncPreset"
                >
                  <option v-for="item in exits" :key="item.id" :value="item.id">
                    {{ item.label }}
                  </option>
                </select>
                <p class="label">
                  {{ exits.find((item) => item.id === exitId)?.description }}
                </p>
              </fieldset>
              <fieldset v-else class="fieldset lg:col-span-3 lg:row-start-2">
                <legend class="fieldset-legend">Strategy brief</legend>
                <textarea
                  v-model="strategy.source"
                  class="textarea h-28 w-full"
                  placeholder="Describe the strategy logic the AI should compose from the node catalog."
                />
                <p class="label">
                  The AI receives the selected market data plus the complete
                  validated node catalog.
                </p>
              </fieldset>
            </div>
            <div class="mt-3 grid gap-3 md:grid-cols-2 lg:grid-cols-5">
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Exchange</legend>
                <input
                  v-model="exchange"
                  class="input w-full"
                  placeholder="binance"
                />
              </fieldset>
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Market type</legend>
                <select v-model="tradingMode" class="select w-full">
                  <option value="futures">Futures</option>
                  <option value="spot">Spot</option>
                  <option value="margin">Margin</option>
                </select>
              </fieldset>
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Pairs</legend>
                <input
                  v-model="pairs"
                  class="input w-full"
                  placeholder="BTC/USDT:USDT"
                />
                <p class="label">Comma-separated.</p>
              </fieldset>
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Timeframes</legend>
                <input
                  v-model="timeframes"
                  class="input w-full"
                  placeholder="5m,1h"
                />
                <p class="label">Comma-separated.</p>
              </fieldset>
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Timerange</legend>
                <input
                  v-model="timerange"
                  class="input w-full"
                  placeholder="20260101-20261231"
                />
              </fieldset>
            </div>
            <div class="mt-3 flex flex-wrap items-end gap-3">
              <button
                class="btn btn-secondary"
                :disabled="
                  busy || (creationMode === 'ai' && !strategy.source.trim())
                "
                @click="
                  creationMode === 'manual'
                    ? createTemplate()
                    : createAiStrategy()
                "
              >
                <span>{{
                  creationMode === "manual" ? "Create" : "Generate"
                }}</span>
              </button>
              <button
                class="btn btn-primary"
                :disabled="busy || !strategy.parameters.length"
                @click="run()"
              >
                <span>Run Backtest</span>
              </button>
            </div>
            <div
              v-if="busy"
              class="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3"
              aria-busy="true"
              aria-label="Loading strategy parameters"
            >
              <div
                v-for="index in 6"
                :key="index"
                class="rounded-box border border-base-300 p-3"
              >
                <div class="skeleton h-4 w-32"></div>
                <div class="skeleton mt-3 h-4 w-48"></div>
              </div>
            </div>
            <div
              v-else-if="strategy.parameters.length"
              class="mt-4 result-hydrate"
              :key="`parameters-${resultVersion}`"
            >
              <div class="flex items-center justify-between gap-3">
                <h3 class="font-medium">Template parameters</h3>
                <label class="sr-only" for="template-parameter-view"
                  >Template parameter view</label
                >
                <select
                  id="template-parameter-view"
                  v-model="parameterView"
                  class="select select-sm"
                >
                  <option value="parameters">Parameters</option>
                  <option value="nodes">Nodes</option>
                  <option value="json">JSON</option>
                </select>
              </div>
              <div
                v-if="parameterView === 'parameters'"
                class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3"
              >
                <div
                  v-for="parameter in strategy.parameters"
                  :key="parameter.name"
                  class="rounded-box border border-base-300 p-3"
                >
                  <div class="font-medium">{{ parameter.name }}</div>
                  <div class="text-sm text-base-content/70">
                    {{ parameter.value }} · {{ parameter.notes }}
                  </div>
                </div>
              </div>
              <StrategyGraph
                v-else-if="parameterView === 'nodes' && strategyGraph"
                class="mt-2"
                :graph="strategyGraph"
                :catalog="nodeCatalog.nodes"
                editable
                @update:graph="updateStrategyGraph"
              />
              <div v-else class="group relative mt-2">
                <pre
                  class="max-h-[32rem] overflow-auto rounded-box border border-base-300 bg-base-100 p-4 pr-20 text-xs text-base-content/80"
                  >{{ strategyGraphJson }}</pre
                >
                <button
                  class="btn btn-ghost btn-square btn-sm absolute top-2 right-6 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
                  type="button"
                  aria-label="Copy node graph JSON"
                  title="Copy node graph JSON"
                  @click="copyGraphJson"
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    aria-hidden="true"
                    class="size-4"
                  >
                    <rect x="9" y="9" width="11" height="11" rx="2" />
                    <path
                      d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </section>
        <section
          v-if="activeTab === 'optimizer'"
          class="page-enter card bg-base-200"
        >
          <div class="card-body">
            <h2 class="card-title">Hyperopt optimizer</h2>
            <p class="text-sm text-base-content/70">
              Hyperopt refreshes the Builder market data first, then evaluates
              the deterministic template parameter ranges.
            </p>
            <div class="mt-3 grid gap-3 md:grid-cols-2">
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Hyperopt epochs</legend>
                <input
                  v-model.number="epochs"
                  type="number"
                  min="1"
                  max="10000"
                  class="input w-full"
                />
                <p class="label">
                  Higher values explore more parameter combinations.
                </p>
              </fieldset>
              <div class="rounded-box border border-base-300 p-4">
                <div class="text-sm text-base-content/60">
                  Current run context
                </div>
                <div class="mt-1 font-medium">
                  {{ strategy.name || "Create a template in Builder" }}
                </div>
                <div class="mt-1 text-sm text-base-content/70">
                  {{ exchange }} · {{ tradingMode }} · {{ pairs }} ·
                  {{ timeframes
                  }}<span v-if="timerange"> · {{ timerange }}</span>
                </div>
              </div>
            </div>
            <div class="mt-4 grid gap-3 md:grid-cols-2">
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Optimization goal</legend>
                <select
                  v-model="optimizationGoal.profile"
                  class="select w-full"
                >
                  <option value="balanced">Balanced</option>
                  <option value="higher_frequency">Higher frequency</option>
                  <option value="return_focused">Return focused</option>
                  <option value="capital_preservation">
                    Capital preservation
                  </option>
                </select>
                <p class="label">
                  Generates the Freqtrade loss objective; it does not invent new
                  logic.
                </p>
              </fieldset>
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Target trades / year</legend>
                <input
                  v-model.number="optimizationGoal.target_trades_per_year"
                  type="number"
                  min="1"
                  max="100000"
                  class="input w-full"
                />
                <p class="label">
                  A target, not a reason to accept losing churn.
                </p>
              </fieldset>
              <fieldset class="fieldset">
                <legend class="fieldset-legend">
                  Minimum trades / validation test
                </legend>
                <input
                  v-model.number="optimizationGoal.min_trades_per_test"
                  type="number"
                  min="1"
                  max="10000"
                  class="input w-full"
                />
                <p class="label">
                  Low-sample tests reduce the stability score.
                </p>
              </fieldset>
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Maximum drawdown [%]</legend>
                <input
                  v-model.number="optimizationGoal.max_drawdown_pct"
                  type="number"
                  min="0.1"
                  max="100"
                  step="0.1"
                  class="input w-full"
                />
              </fieldset>
              <fieldset class="fieldset">
                <legend class="fieldset-legend">Minimum profit factor</legend>
                <input
                  v-model.number="optimizationGoal.min_profit_factor"
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  class="input w-full"
                />
              </fieldset>
            </div>
            <div class="mt-3">
              <button
                class="btn btn-primary"
                :disabled="busy || !strategy.parameters.length"
                @click="run(true)"
              >
                <span>Optimize</span>
              </button>
            </div>
            <div
              v-if="busy"
              class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
              aria-busy="true"
              aria-label="Loading optimization results"
            >
              <div
                v-for="index in 8"
                :key="index"
                class="rounded-box border border-base-300 bg-base-100 p-4"
              >
                <div class="skeleton h-4 w-28"></div>
                <div class="skeleton mt-3 h-7 w-20"></div>
              </div>
            </div>
            <div
              v-else-if="optimizationReport"
              :key="`optimization-${resultVersion}`"
              class="result-hydrate mt-4 rounded-box border border-base-300 bg-base-100 p-4"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <h3 class="font-medium">Optimization feasibility</h3>
                <span
                  class="badge"
                  :class="
                    optimizationReport.goal_met
                      ? 'badge-success'
                      : 'badge-warning'
                  "
                  >{{
                    optimizationReport.goal_met
                      ? "Goal met"
                      : "Infeasible fallback"
                  }}</span
                >
              </div>
              <div
                v-if="!optimizationReport.goal_met"
                role="alert"
                class="alert alert-warning alert-soft mt-3 text-sm"
              >
                <span
                  >This snapshot uses the best available fallback, not a
                  strategy that met every goal.</span
                >
              </div>
              <p class="mt-2 text-sm text-base-content/70">
                {{ optimizationReport.summary }}
              </p>
              <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <div class="text-xs text-base-content/60">
                    Target trades / year
                  </div>
                  <div class="font-medium">
                    {{ metricValue(optimizationReport.target_trades_per_year) }}
                  </div>
                </div>
                <div>
                  <div class="text-xs text-base-content/60">
                    Selected trades / year
                  </div>
                  <div class="font-medium">
                    {{ metricValue(optimizationReport.best_annualized_trades) }}
                  </div>
                </div>
                <div>
                  <div class="text-xs text-base-content/60">
                    Search maximum / year
                  </div>
                  <div class="font-medium">
                    {{
                      metricValue(
                        optimizationReport.max_observed_annualized_trades,
                      )
                    }}
                  </div>
                </div>
                <div>
                  <div class="text-xs text-base-content/60">
                    Compliant candidates
                  </div>
                  <div class="font-medium">
                    {{
                      metricValue(optimizationReport.feasible_candidate_count)
                    }}
                  </div>
                </div>
              </div>
            </div>
            <div v-if="strategy.parameters.length" class="mt-5">
              <h3 class="font-medium">Optimizable parameters</h3>
              <div class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                <div
                  v-for="parameter in strategy.parameters"
                  :key="parameter.name"
                  class="rounded-box border border-base-300 p-3"
                >
                  <div class="font-medium">{{ parameter.name }}</div>
                  <div class="text-sm text-base-content/70">
                    {{ parameter.value }} · {{ parameter.notes }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
        <section
          v-if="activeTab === 'validation'"
          class="page-enter card bg-base-200"
        >
          <div class="card-body">
            <h2 class="card-title">Walk-forward validation</h2>
            <p class="text-sm text-base-content/70">
              Standard validation uses 70% chronological training and 10 equal
              out-of-sample test windows. Quick validation uses 2.5 years and 5
              test windows. The score is
              <span class="font-medium">100 ÷ (1 + σ test return)</span>, and
              becomes zero when mean test return is not positive.
            </p>
            <div class="mt-3 flex flex-wrap gap-3">
              <fieldset class="fieldset min-w-0 w-full md:w-72">
                <legend class="fieldset-legend">Validation range</legend>
                <input
                  v-model="validationTimerange"
                  class="input min-w-0 w-full"
                  placeholder="20210101-20260101"
                />
                <p class="label">Standard: five years and 10 test windows.</p>
              </fieldset>
              <fieldset class="fieldset min-w-0 w-full md:w-80">
                <legend class="fieldset-legend">Quick validation</legend>
                <input
                  :value="quickValidationTimerange"
                  readonly
                  class="input min-w-0 w-full"
                />
                <p class="label">
                  2.5 years and 5 test windows. Reuses local candles when
                  coverage is available.
                </p>
              </fieldset>
            </div>
            <div class="mt-3 flex flex-wrap gap-3">
              <button
                class="btn"
                :disabled="busy || !strategy.parameters.length"
                @click="runValidation(true)"
              >
                <span>Quick Validate</span>
              </button>
              <button
                class="btn btn-primary"
                :disabled="busy || !strategy.parameters.length"
                @click="runValidation()"
              >
                <span>Validate</span>
              </button>
            </div>
            <div
              v-if="busy"
              class="mt-5 grid gap-3 sm:grid-cols-3"
              aria-busy="true"
              aria-label="Loading validation results"
            >
              <div
                v-for="index in 3"
                :key="index"
                class="rounded-box bg-base-100 p-4"
              >
                <div class="skeleton h-4 w-28"></div>
                <div class="skeleton mt-3 h-8 w-20"></div>
              </div>
              <div class="skeleton h-64 sm:col-span-3"></div>
            </div>
            <template v-else-if="validation"
              ><div
                :key="`validation-${resultVersion}`"
                class="result-hydrate mt-5 grid gap-3 sm:grid-cols-3"
              >
                <div class="rounded-box bg-base-100 p-4">
                  <div class="text-sm text-base-content/60">
                    Stability score
                  </div>
                  <div
                    class="mt-1 text-2xl font-medium"
                    :class="valueTone('Return [%]', validation.mean_return)"
                  >
                    {{ metricValue(validation.stability_score) }}
                  </div>
                  <div class="text-xs text-base-content/60">
                    Higher is more stable.
                  </div>
                </div>
                <div class="rounded-box bg-base-100 p-4">
                  <div class="text-sm text-base-content/60">
                    Mean test return [%]
                  </div>
                  <div
                    class="mt-1 text-xl font-medium"
                    :class="valueTone('Return [%]', validation.mean_return)"
                  >
                    {{ metricValue(validation.mean_return) }}
                  </div>
                </div>
                <div class="rounded-box bg-base-100 p-4">
                  <div class="text-sm text-base-content/60">Test return σ</div>
                  <div
                    class="mt-1 text-xl font-medium"
                    :class="
                      valueTone('Drawdown [%]', -validation.return_stddev)
                    "
                  >
                    {{ metricValue(validation.return_stddev) }}
                  </div>
                  <div class="text-xs text-base-content/60">
                    {{ validation.coverage }}
                  </div>
                </div>
              </div>
              <div
                class="mt-5 max-h-96 overflow-auto rounded-box border border-base-300"
              >
                <table class="table table-pin-rows table-sm">
                  <thead>
                    <tr>
                      <th>Split</th>
                      <th>Timerange</th>
                      <th>Return [%]</th>
                      <th>Win Rate [%]</th>
                      <th>Profit Factor</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="slice in [
                        validation.training,
                        ...validation.tests,
                      ]"
                      :key="slice.label"
                    >
                      <td>{{ slice.label }}</td>
                      <td>{{ slice.timerange }}</td>
                      <td
                        :class="
                          valueTone(
                            'Return [%]',
                            slice.backtest.metrics['Return [%]'],
                          )
                        "
                      >
                        {{ metricValue(slice.backtest.metrics["Return [%]"]) }}
                      </td>
                      <td
                        :class="
                          valueTone(
                            'Win Rate [%]',
                            slice.backtest.metrics['Win Rate [%]'],
                          )
                        "
                      >
                        {{
                          metricValue(slice.backtest.metrics["Win Rate [%]"])
                        }}
                      </td>
                      <td
                        :class="
                          valueTone(
                            'Profit Factor',
                            slice.backtest.metrics['Profit Factor'],
                          )
                        "
                      >
                        {{
                          metricValue(slice.backtest.metrics["Profit Factor"])
                        }}
                      </td>
                      <td>
                        <button
                          class="btn btn-ghost btn-xs"
                          @click="selectHistory(slice.backtest)"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div></template
            >
            <div
              v-if="validation"
              class="mt-5 rounded-box border border-base-300 p-4"
            >
              <h3 class="font-medium">Validation confidence</h3>
              <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div class="rounded-box bg-base-100 p-3">
                  <div class="text-sm text-base-content/60">
                    Sample-adjusted stability
                  </div>
                  <div
                    class="mt-1 text-xl font-medium"
                    :class="valueTone('Return [%]', validation.mean_return)"
                  >
                    {{ metricValue(validation.stability_score) }}
                  </div>
                </div>
                <div class="rounded-box bg-base-100 p-3">
                  <div class="text-sm text-base-content/60">
                    Out-of-sample trades
                  </div>
                  <div class="mt-1 text-xl font-medium">
                    {{ validation.total_test_trades }}
                  </div>
                  <div class="text-xs text-base-content/60">
                    Minimum {{ validation.minimum_test_trades }} per test.
                  </div>
                </div>
                <div class="rounded-box bg-base-100 p-3">
                  <div class="text-sm text-base-content/60">
                    Mean test return [%]
                  </div>
                  <div
                    class="mt-1 text-xl font-medium"
                    :class="valueTone('Return [%]', validation.mean_return)"
                  >
                    {{ metricValue(validation.mean_return) }}
                  </div>
                </div>
                <div class="rounded-box bg-base-100 p-3">
                  <div class="text-sm text-base-content/60">
                    Test return deviation
                  </div>
                  <div class="mt-1 text-xl font-medium">
                    {{ metricValue(validation.return_stddev) }}
                  </div>
                </div>
              </div>
              <p
                v-if="validation.snapshot_path"
                class="mt-3 text-sm text-base-content/70"
              >
                Saved validation snapshot: {{ validation.snapshot_path }}
              </p>
              <div
                class="mt-3 max-h-80 overflow-auto rounded-box border border-base-300"
              >
                <table class="table table-pin-rows table-sm">
                  <thead>
                    <tr>
                      <th>Split</th>
                      <th>Trades</th>
                      <th>Return [%]</th>
                      <th>Profit Factor</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="slice in [
                        validation.training,
                        ...validation.tests,
                      ]"
                      :key="`confidence-${slice.label}`"
                    >
                      <td>{{ slice.label }}</td>
                      <td>
                        {{
                          metricValue(slice.backtest.metrics["Total Trades"])
                        }}
                      </td>
                      <td
                        :class="
                          valueTone(
                            'Return [%]',
                            slice.backtest.metrics['Return [%]'],
                          )
                        "
                      >
                        {{ metricValue(slice.backtest.metrics["Return [%]"]) }}
                      </td>
                      <td
                        :class="
                          valueTone(
                            'Profit Factor',
                            slice.backtest.metrics['Profit Factor'],
                          )
                        "
                      >
                        {{
                          metricValue(slice.backtest.metrics["Profit Factor"])
                        }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>
        <LogsPage
          v-if="activeTab === 'logs'"
          class="page-enter"
          :output="output"
          @copy="copyRunOutput"
          @export="exportRunOutput"
        />
        <SettingsPage
          v-if="activeTab === 'settings'"
          class="page-enter"
          :api-key-status="openAiApiKeyStatus"
          :saving-api-key="savingOpenAiApiKey"
          :clearing-kind="clearingKind"
          :datasets="datasets"
          @save-api-key="saveOpenAiApiKey"
          @clear-api-key="clearOpenAiApiKey"
          @request-clear="requestClear"
          @refresh-datasets="refreshDatasets"
        />
        <!--
      <section class="card bg-base-200"><div class="card-body"><h2 class="card-title">Settings</h2>
        <div class="mt-3 rounded-box border border-base-300 bg-base-100 p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 class="font-medium">OpenAI API key</h3>
              <p class="mt-1 text-sm text-base-content/70">Used only for AI strategy generation. The key is kept in Stratara’s local app cache and is never included in strategy snapshots.</p>
            </div>
            <span v-if="openAiApiKeyStatus.configured" class="badge badge-success">Configured{{ openAiApiKeyStatus.source ? ` · ${openAiApiKeyStatus.source}` : "" }}</span>
            <span v-else class="badge">Not configured</span>
          </div>
          <div class="mt-4 flex flex-wrap items-end gap-2">
            <fieldset class="fieldset min-w-0 flex-1">
              <legend class="fieldset-legend">API key</legend>
              <input
                :value="apiKeyInputValue"
                type="password"
                autocomplete="off"
                class="input w-full disabled:cursor-not-allowed disabled:border-base-300 disabled:bg-base-200 disabled:text-base-content/60"
                :disabled="apiKeyInputDisabled"
                :placeholder="openAiApiKeyStatus.cache_configured ? '' : 'Paste a new key to save or replace it'"
                @input="openAiApiKey = ($event.target as HTMLInputElement).value"
                @keyup.enter="saveOpenAiApiKey"
              />
            </fieldset>
            <button class="btn btn-primary" type="button" :disabled="apiKeyInputDisabled || !openAiApiKey.trim()" @click="saveOpenAiApiKey">
              Save
              <span v-if="savingOpenAiApiKey" class="loading loading-spinner loading-sm"></span>
            </button>
            <button class="btn" type="button" :disabled="savingOpenAiApiKey || !openAiApiKeyStatus.cache_configured" @click="clearOpenAiApiKey">Clear saved key</button>
          </div>
          <p v-if="openAiApiKeyStatus.environment_configured" class="mt-2 text-xs text-base-content/60">OPENAI_API_KEY from the environment or .env takes precedence over the saved key.</p>
        </div>
        <div class="mt-3 rounded-box border border-error/50 bg-error/5 p-4"><h3 class="font-medium text-error">Danger zone</h3><p class="mt-1 text-sm text-base-content/70">Clear run records and matching Freqtrade artifacts for the active workspace.</p><div role="alert" class="alert alert-error alert-soft mt-3 text-sm"><span>Clearing moves matching local snapshots and Freqtrade artifacts to the Recycle Bin. Downloaded datasets and strategy templates are kept.</span></div><div class="mt-3 grid gap-3 md:grid-cols-3"><div class="rounded-box border border-error/35 bg-base-100 p-4"><h4 class="font-medium">Backtests</h4><p class="mt-1 text-sm text-base-content/70">Clears saved backtest history and Freqtrade backtest exports.</p><button class="btn btn-error btn-sm mt-3" :disabled="clearingKind !== ''" @click="requestClear('backtests')">Clear backtests<span v-if="clearingKind === 'backtests'" class="loading loading-spinner loading-xs"></span></button></div><div class="rounded-box border border-error/35 bg-base-100 p-4"><h4 class="font-medium">Hyperopts</h4><p class="mt-1 text-sm text-base-content/70">Clears saved Hyperopt history and Freqtrade search artifacts.</p><button class="btn btn-error btn-sm mt-3" :disabled="clearingKind !== ''" @click="requestClear('hyperopts')">Clear hyperopts<span v-if="clearingKind === 'hyperopts'" class="loading loading-spinner loading-xs"></span></button></div><div class="rounded-box border border-error/35 bg-base-100 p-4"><h4 class="font-medium">Validations</h4><p class="mt-1 text-sm text-base-content/70">Clears validation snapshots and split-result artifacts.</p><button class="btn btn-error btn-sm mt-3" :disabled="clearingKind !== ''" @click="requestClear('validations')">Clear validations<span v-if="clearingKind === 'validations'" class="loading loading-spinner loading-xs"></span></button></div></div></div>
        <div class="mt-6"><div class="flex flex-wrap items-center justify-between gap-2"><div><h3 class="font-medium">Downloaded datasets</h3><p class="text-sm text-base-content/70">Cached Freqtrade candles are listed only; clearing them is not available yet.</p></div><button class="btn btn-sm" @click="refreshDatasets">Refresh</button></div><ul v-if="datasets.length" class="list mt-2 rounded-box border border-base-300"><li v-for="dataset in datasets" :key="dataset.path" class="list-row"><span class="list-col-grow break-all">{{ dataset.path }}</span><span class="text-sm text-base-content/60">{{ (dataset.bytes / 1024 / 1024).toFixed(2) }} MB</span></li></ul><p v-else class="mt-3 text-sm text-base-content/60">No downloaded Freqtrade datasets in this workspace.</p></div>
      </div></section>
      -->
        <template
          v-if="
            activeTab === 'builder' ||
            activeTab === 'optimizer' ||
            activeTab === 'validation'
          "
        >
          <section class="card bg-base-200">
            <div class="card-body">
              <h2 class="card-title">Data visualization</h2>
              <div
                v-if="busy"
                class="space-y-4"
                aria-busy="true"
                aria-label="Loading backtest results"
              >
                <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div
                    v-for="index in 8"
                    :key="index"
                    class="rounded-box bg-base-100 p-4"
                  >
                    <div class="skeleton h-4 w-24"></div>
                    <div class="skeleton mt-3 h-7 w-20"></div>
                  </div>
                </div>
                <div class="skeleton h-80 w-full"></div>
                <div class="space-y-2">
                  <div class="skeleton h-5 w-28"></div>
                  <div
                    v-for="index in 6"
                    :key="`position-${index}`"
                    class="skeleton h-10 w-full"
                  ></div>
                </div>
              </div>
              <template v-else-if="selected"
                ><div
                  :key="`backtest-${resultVersion}`"
                  class="result-hydrate grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
                >
                  <div
                    v-for="(value, name) in selected.metrics"
                    :key="String(name)"
                    class="rounded-box bg-base-100 p-4"
                  >
                    <div class="text-sm text-base-content/60">{{ name }}</div>
                    <div
                      class="mt-1 text-xl font-medium"
                      :class="valueTone(String(name), value)"
                    >
                      {{ metricValue(value) }}
                    </div>
                  </div>
                </div>
                <div class="mt-4">
                  <EquityChart
                    :equity="selected.equity_curve"
                    :timestamps="selected.equity_timestamps"
                  />
                </div>
                <div class="mt-4">
                  <h3 class="mb-2 font-medium">Positions</h3>
                  <div
                    class="max-h-96 overflow-auto rounded-box border border-base-300"
                  >
                    <table class="table table-pin-rows table-sm">
                      <thead>
                        <tr>
                          <th v-for="column in tradeColumns" :key="column">
                            <button
                              class="btn btn-ghost btn-xs"
                              @click="toggleSort(column)"
                            >
                              {{ column }}
                              <span v-if="sortColumn === column">{{
                                sortDirection === "asc" ? "▲" : "▼"
                              }}</span>
                            </button>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr
                          v-for="(trade, index) in visibleTrades"
                          :key="index"
                        >
                          <td v-for="column in tradeColumns" :key="column">
                            <span :class="valueTone(column, trade[column])">{{
                              tableValue(column, trade[column])
                            }}</span>
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                  <div class="mt-3 flex items-center justify-end gap-2">
                    <button
                      class="btn btn-sm"
                      :disabled="page === 1"
                      @click="page--"
                    >
                      Previous</button
                    ><span class="text-sm">{{ page }} / {{ pageCount }}</span
                    ><button
                      class="btn btn-sm"
                      :disabled="page === pageCount"
                      @click="page++"
                    >
                      Next
                    </button>
                  </div>
                </div></template
              >
              <p v-else class="text-base-content/60">
                Run or load a Freqtrade strategy to view metrics, charts, and
                positions.
              </p>
            </div>
          </section>
          <section class="card bg-base-200">
            <div class="card-body">
              <h2 class="card-title">Local history</h2>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="item in history"
                  :key="item.id"
                  class="btn btn-sm"
                  :class="selected?.id === item.id ? 'btn-neutral' : ''"
                  @click="selectHistory(item)"
                >
                  {{ item.name }}</button
                ><span
                  v-if="!history.length"
                  class="text-sm text-base-content/60"
                  >No Freqtrade runs saved yet.</span
                >
              </div>
            </div>
          </section>
        </template>
      </section>
    </main>
  </div>
  <dialog
    class="modal"
    :open="pendingClearKind !== null"
    @cancel.prevent="pendingClearKind = null"
  >
    <div class="modal-box border border-error/50">
      <h3 class="text-lg font-bold text-error">
        Clear {{ pendingClearKind }}?
      </h3>
      <p class="py-4">
        Saved {{ pendingClearKind }} and matching Freqtrade artifacts will move
        to the Recycle Bin. Downloaded datasets will stay untouched.
      </p>
      <div class="modal-action">
        <button class="btn" type="button" @click="pendingClearKind = null">
          Cancel</button
        ><button class="btn btn-error" type="button" @click="clearResults">
          Clear {{ pendingClearKind }}
        </button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop">
      <button
        type="button"
        aria-label="Cancel clear operation"
        @click="pendingClearKind = null"
      >
        Cancel
      </button>
    </form>
  </dialog>
  <div
    v-if="progress"
    class="fixed inset-x-0 bottom-0 z-50 bg-base-100 px-5 py-3 shadow-2xl"
  >
    <div
      class="pointer-events-none absolute -top-20 right-0 h-36 w-64 rounded-tl-[4rem] bg-gradient-to-tl from-base-300/55 via-base-300/25 to-transparent blur-xl shadow-[inset_-2rem_-1.5rem_3rem_-1rem_rgba(0,0,0,0.35)]"
    ></div>
    <div class="absolute -top-20 right-4 z-10 grid size-16 place-items-center">
      <span
        class="loading loading-spinner absolute size-16 text-error"
        aria-hidden="true"
      ></span>
      <button
        class="btn btn-circle btn-error btn-md relative z-10 shadow-xl"
        type="button"
        aria-label="Emergency stop current run"
        title="Emergency stop"
        @click="cancelRun"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true" class="size-5 fill-current">
          <rect x="6" y="6" width="12" height="12" rx="1" />
        </svg>
      </button>
    </div>
    <div class="flex justify-between gap-4 text-sm font-medium">
      <span class="truncate">{{ progress.label }}</span
      ><span class="shrink-0">{{ progress.percent }}%</span>
    </div>
    <progress
      class="progress progress-primary mt-1 block w-full"
      :value="progress.percent"
      max="100"
    ></progress>
    <div class="mt-2 flex justify-between gap-4 text-xs text-base-content/70">
      <span class="truncate">{{ progress.sub_label }}</span
      ><span class="shrink-0">{{ progress.sub_percent }}%</span>
    </div>
    <progress
      class="progress progress-accent mt-1 block w-full"
      :value="progress.sub_percent"
      max="100"
    ></progress>
    <div
      class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-base-content/60"
    >
      <span v-for="(step, index) in progress.steps" :key="`${index}-${step}`">{{
        step
      }}</span>
    </div>
  </div>
</template>

<style>
@keyframes stratara-page-enter {
  from {
    opacity: 0;
    transform: translateY(0.75rem);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.page-enter,
.result-hydrate {
  animation: stratara-page-enter 180ms cubic-bezier(0.23, 1, 0.32, 1) both;
}

@media (prefers-reduced-motion: reduce) {
  .page-enter,
  .result-hydrate {
    animation-duration: 1ms;
  }
}
</style>
