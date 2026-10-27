<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, toRaw, watch } from "vue";
import { open } from "@tauri-apps/plugin-dialog";
import { pyInvoke } from "tauri-plugin-pytauri-api";
import EquityChart from "./components/EquityChart.vue";
import OptimizationChart from "./components/OptimizationChart.vue";

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
  optimization_goal: string;
  parameters: Parameter[];
  vibe_payload?: Record<string, unknown>;
  strategy_file?: string | null;
};
type Trade = Record<string, unknown>;
type Backtest = {
  id: number;
  name: string;
  imported_at: string;
  metrics: Record<string, unknown>;
  trades: Trade[];
  equity_curve: number[];
  equity_timestamps: string[];
};
type StrategyRun = {
  strategy: Strategy;
  backtest: Backtest | null;
  output: string;
  error?: string | null;
};
type SortDirection = "asc" | "desc" | null;
type Metric = [string, unknown];
type RecycledStrategyFile = {
  original_path: string;
  recycle_path: string;
  previous_path: string | null;
};
type RunType = "raw" | "optimized" | "auto";
type RedoContext = {
  strategy: Strategy;
  run_type: RunType;
  metrics: Record<string, unknown>;
  goal: string;
};
type GlobalProgress = { scope: "manual" | "auto"; label: string; percent: number };
type AutoTrialColumn = "Trial" | "Status" | "Score" | "Parameters";
type AutoTrial = { number: number; status: string; score: number | null; parameters: Parameter[]; metrics: Record<string, unknown>; error: string; snapshot_path: string; backtest_id: number | null };
type AutoWorkflow = { id: string; name: string; path: string; status: string; prompt_limit: number; target_metrics: string[]; completed_trials: number; stop_requested: boolean; best_trial: AutoTrial | null; best_backtest: Backtest | null; trials: AutoTrial[] };

const strategy = ref<Strategy>({
  name: "",
  source: "",
  workspace_path: "",
  optimization_goal: "",
  parameters: [],
});
const strategies = ref<Strategy[]>([]);
const history = ref<Backtest[]>([]);
const selected = ref<Backtest | null>(null);
const output = ref("");
const error = ref("");
const busy = ref(false);
const runningPrompt = ref<"raw" | "optimized" | "auto" | "redo" | null>(null);
const useOptimizationGoal = ref(false);
const saveFilePath = ref("");
const resultsPanel = ref<HTMLElement | null>(null);
const sortColumn = ref<string | null>(null);
const sortDirection = ref<SortDirection>(null);
const tradePage = ref(1);
const tradesPerPage = 25;
const defaultWorkspace = ref("");
const loadedSavePaths = ref<string[]>([]);
const saveControlsOpen = ref(true);
const recentDeletion = ref<RecycledStrategyFile | null>(null);
const currentSavePath = computed(() => strategy.value.strategy_file ?? "");
const lastRedoContext = ref<RedoContext | null>(null);
const activeTab = ref<"manual" | "auto">("manual");
const autoStartPath = ref("");
const autoStartBacktest = ref<Backtest | null>(null);
const autoPromptLimit = ref(5);
const autoTargetMetrics = ref<string[]>([]);
const autoTargetSearch = ref("");
const autoWorkflows = ref<AutoWorkflow[]>([]);
const autoWorkflow = ref<AutoWorkflow | null>(null);
const autoBusy = ref(false);
const autoError = ref("");
const autoEngine = ref<"vibe" | "backtesting">("vibe");
const referenceOhlcvFiles = ref<string[]>([]);
const referencesRoot = ref("");
const autoOhlcvPath = ref("");
const autoTrialSortColumn = ref<AutoTrialColumn | null>(null);
const autoTrialSortDirection = ref<SortDirection>(null);
const autoTrialPage = ref(1);
const parameterTrial = ref<AutoTrial | null>(null);
const comparedTrial = ref<AutoTrial | null>(null);
const comparePickerOpen = ref(false);
const compareTrialNumber = ref<number | null>(null);
const compareSearch = ref("");
const globalProgress = ref<GlobalProgress | null>(null);
let autoPoll: ReturnType<typeof setInterval> | undefined;
let undoToastTimeout: ReturnType<typeof setTimeout> | undefined;

async function call<T>(command: string, body?: unknown) {
  error.value = "";
  return pyInvoke<T>(command, body);
}

function clonePayload<T>(value: T): T {
  return structuredClone(toRaw(value));
}

function startProgress(scope: GlobalProgress["scope"], label: string, percent: number) {
  globalProgress.value = { scope, label, percent };
}

function updateProgress(label: string, percent: number) {
  if (globalProgress.value) globalProgress.value = { ...globalProgress.value, label, percent };
}

function finishProgress(scope: GlobalProgress["scope"]) {
  if (globalProgress.value?.scope === scope) globalProgress.value = null;
}

function showResults() {
  resultsPanel.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function refresh() {
  try {
    const [workspace, savedStrategies, savedHistory, referenceRoot, referenceFiles] = await Promise.all([
      call<string>("default_workspace"),
      call<Strategy[]>("list_strategy_setups"),
      call<Backtest[]>("list_imported_backtests"),
      call<string>("references_root"),
      call<string[]>("list_reference_ohlcv_files"),
    ]);
    if (!strategy.value.workspace_path)
      strategy.value.workspace_path = workspace;
    defaultWorkspace.value = workspace;
    strategies.value = savedStrategies;
    history.value = savedHistory;
    referencesRoot.value = referenceRoot;
    referenceOhlcvFiles.value = referenceFiles;
  } catch (cause) {
    error.value = String(cause);
  }
}

async function refreshAutoWorkflows() {
  try {
    autoWorkflows.value = await call<AutoWorkflow[]>("list_auto_workflows");
    if (autoWorkflow.value) {
      autoWorkflow.value = await call<AutoWorkflow>("load_auto_workflow", autoWorkflow.value.path);
      const workflow = autoWorkflow.value;
      if (["queued", "running"].includes(workflow.status)) {
        startProgress("auto", workflow.status === "queued" ? "Preparing automated workflow" : `Running trial ${workflow.completed_trials + 1} of ${workflow.prompt_limit}`, Math.min(95, Math.round((workflow.completed_trials / workflow.prompt_limit) * 100)));
      } else {
        finishProgress("auto");
      }
    }
  } catch (cause) {
    error.value = String(cause);
  }
}

function updateAutoPolling() {
  if (autoPoll) clearInterval(autoPoll);
  autoPoll = undefined;
  if (["queued", "running"].includes(autoWorkflow.value?.status ?? "")) {
    autoPoll = setInterval(refreshAutoWorkflows, 1_500);
  }
}

async function chooseAutoStartFile() {
  const path = await open({
    defaultPath: strategy.value.workspace_path,
    filters: [{ name: "Strategy save", extensions: ["sqlite", "sqlite3"] }],
    multiple: false,
  });
  if (typeof path !== "string") return;
  autoStartPath.value = path;
  await loadAutoStartFile();
}

function referenceOhlcvLabel(path: string) {
  const root = referencesRoot.value.replace(/[\\/]+$/, "");
  return root && path.startsWith(root) ? path.slice(root.length).replace(/^[\\/]+/, "") : path;
}

async function chooseAutoOhlcvFile() {
  const path = await open({
    defaultPath: referencesRoot.value,
    filters: [{ name: "OHLCV CSV", extensions: ["csv"] }],
    multiple: false,
  });
  if (typeof path !== "string") return;
  autoOhlcvPath.value = path;
  if (!referenceOhlcvFiles.value.includes(path))
    referenceOhlcvFiles.value = [...referenceOhlcvFiles.value, path].sort();
}

async function loadAutoStartFile() {
  if (!autoStartPath.value) return;
  autoBusy.value = true;
  try {
    const [preview, owningWorkflow] = await Promise.all([
      call<StrategyRun>("preview_strategy_save_file", { path: autoStartPath.value }),
      call<AutoWorkflow | null>("auto_workflow_for_snapshot", { path: autoStartPath.value }),
    ]);
    autoStartBacktest.value = preview.backtest;
    autoTargetMetrics.value = [];
    autoWorkflow.value = owningWorkflow;
    if (owningWorkflow) {
      autoWorkflows.value = [owningWorkflow, ...autoWorkflows.value.filter((workflow) => workflow.path !== owningWorkflow.path)];
      updateAutoPolling();
    }
  } catch (cause) {
    autoStartBacktest.value = null;
    autoWorkflow.value = null;
    error.value = String(cause);
  } finally {
    autoBusy.value = false;
  }
}

async function startAutoWorkflow() {
  if (!selected.value && !autoStartPath.value && !currentSavePath.value) return;
  autoBusy.value = true;
  autoError.value = "";
  startProgress("auto", "Preparing automated workflow", 5);
  try {
    const startPath = autoStartPath.value || currentSavePath.value;
    if (autoEngine.value === "backtesting") {
      updateProgress("Loading saved Vibe strategy and cached OHLCV", 20);
      const workflow = await call<AutoWorkflow>("run_backtesting_optimization", {
        strategy: clonePayload(strategy.value),
        start_path: startPath,
        prompt_limit: autoPromptLimit.value,
        target_metrics: clonePayload(autoTargetMetrics.value),
        ohlcv_path: autoOhlcvPath.value,
      });
      updateProgress("Saving Backtesting.py snapshot", 85);
      autoWorkflow.value = workflow;
      activeTab.value = "auto";
      if (workflow.status === "failed") autoError.value = workflow.trials[workflow.trials.length - 1]?.error || "Backtesting.py optimization stopped.";
      await refreshAutoWorkflows();
      showResults();
      return;
    }
    const workflow = await call<AutoWorkflow>("start_auto_workflow", {
      strategy: clonePayload(strategy.value),
      baseline: startPath ? clonePayload(autoStartBacktest.value) : clonePayload(selected.value),
      start_path: startPath,
      prompt_limit: autoPromptLimit.value,
      target_metrics: clonePayload(autoTargetMetrics.value),
    });
    autoWorkflow.value = workflow;
    activeTab.value = "auto";
    await refreshAutoWorkflows();
    updateAutoPolling();
  } catch (cause) {
    autoError.value = String(cause);
  } finally {
    autoBusy.value = false;
    finishProgress("auto");
  }
}

async function loadAutoWorkflow(path: string) {
  autoBusy.value = true;
  try {
    autoWorkflow.value = await call<AutoWorkflow>("load_auto_workflow", path);
    updateAutoPolling();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    autoBusy.value = false;
  }
}

async function stopAutoWorkflow() {
  if (!autoWorkflow.value) return;
  autoBusy.value = true;
  try {
    autoWorkflow.value = await call<AutoWorkflow>("stop_auto_workflow", autoWorkflow.value.path);
    updateAutoPolling();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    autoBusy.value = false;
  }
}

async function applyRun(run: StrategyRun) {
  strategy.value = run.strategy;
  selected.value = run.backtest;
  output.value = run.output;
  saveFilePath.value = run.strategy.strategy_file ?? "";
  useOptimizationGoal.value = Boolean(run.strategy.optimization_goal);
  if (run.error) {
    error.value = run.error;
    return;
  }
  rememberSavePath(run.strategy.strategy_file);
  await refresh();
}

function rememberSavePath(path: string | null | undefined) {
  if (!path) return;
  loadedSavePaths.value = [...loadedSavePaths.value.filter((item) => item !== path), path];
}

function showUndoToast(deletion: RecycledStrategyFile) {
  if (undoToastTimeout) clearTimeout(undoToastTimeout);
  recentDeletion.value = deletion;
  undoToastTimeout = setTimeout(() => {
    recentDeletion.value = null;
    undoToastTimeout = undefined;
  }, 5_000);
}

function dismissUndoToast() {
  if (undoToastTimeout) clearTimeout(undoToastTimeout);
  undoToastTimeout = undefined;
  recentDeletion.value = null;
}

async function runRaw() {
  busy.value = true;
  runningPrompt.value = "raw";
  startProgress("manual", "Preparing strategy prompt", 10);
  try {
    const request = clonePayload(strategy.value);
    updateProgress("Running Vibe-Trading backtest", 45);
    const run = await call<StrategyRun>("run_strategy_backtest", request);
    updateProgress("Saving strategy snapshot", 85);
    await applyRun(run);
    if (!run.error) lastRedoContext.value = { strategy: request, run_type: "raw", metrics: {}, goal: "" };
    showResults();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
    runningPrompt.value = null;
    finishProgress("manual");
  }
}

async function optimize() {
  if (!selected.value) return;
  busy.value = true;
  runningPrompt.value = "optimized";
  startProgress("manual", "Preparing parameter optimization", 10);
  try {
    const request = clonePayload(strategy.value);
    const metrics = clonePayload(selected.value.metrics);
    updateProgress("Running Vibe-Trading optimization", 45);
    const run = await call<StrategyRun>("optimize_strategy_backtest", { strategy: request, metrics });
    updateProgress("Saving optimized snapshot", 85);
    await applyRun(run);
    if (!run.error) lastRedoContext.value = { strategy: request, run_type: "optimized", metrics, goal: "" };
    showResults();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
    runningPrompt.value = null;
    finishProgress("manual");
  }
}

async function autoOptimize() {
  if (!selected.value) return;
  busy.value = true;
  runningPrompt.value = "auto";
  startProgress("manual", "Preparing data-driven optimization", 10);
  try {
    const request = clonePayload(strategy.value);
    const metrics = clonePayload(selected.value.metrics);
    const goal = useOptimizationGoal.value ? request.optimization_goal : "";
    request.optimization_goal = goal;
    updateProgress("Running Vibe-Trading optimization", 45);
    const run = await call<StrategyRun>("auto_optimize_strategy_backtest", { strategy: request, metrics, goal });
    updateProgress("Saving optimized snapshot", 85);
    await applyRun(run);
    if (!run.error) lastRedoContext.value = { strategy: request, run_type: "auto", metrics, goal };
    showResults();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
    runningPrompt.value = null;
    finishProgress("manual");
  }
}

async function chooseStrategyFile() {
  const path = await open({
    defaultPath: strategy.value.workspace_path,
    filters: [{ name: "Strategy save", extensions: ["sqlite", "sqlite3"] }],
    multiple: false,
  });
  if (typeof path !== "string") return;
  saveFilePath.value = path;
  await loadStrategyFile();
}

async function loadStrategyFile() {
  busy.value = true;
  try {
    await loadStrategyPath(saveFilePath.value);
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
  }
}

async function loadStrategyPath(path: string) {
  saveFilePath.value = path;
  await applyRun(await call<StrategyRun>("load_strategy_save_file", { path }));
}

async function importResult(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  busy.value = true;
  try {
    selected.value = await call<Backtest>("import_backtest_result", {
      name: file.name,
      payload: JSON.parse(await file.text()),
    });
    await refresh();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
  }
}

async function selectBacktest(id: number) {
  busy.value = true;
  try {
    selected.value = await call<Backtest>("load_imported_backtest", id);
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
  }
}

async function deleteHistory(id: number) {
  busy.value = true;
  try {
    await call<void>("delete_imported_backtest", id);
    if (selected.value?.id === id) selected.value = null;
    await refresh();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
  }
}

async function clearHistory() {
  if (!history.value.length || !window.confirm("Clear all run history? Snapshot files will remain.")) return;
  busy.value = true;
  try {
    await call<void>("clear_imported_backtests");
    selected.value = null;
    await refresh();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
  }
}

async function copyCurrentSaveToGood() {
  if (!currentSavePath.value) return;
  busy.value = true;
  try {
    await call<string>("copy_strategy_save_to_good_file", { path: currentSavePath.value });
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
  }
}

function clearLoadedStrategy() {
  strategy.value = { name: "", source: "", workspace_path: defaultWorkspace.value, optimization_goal: "", parameters: [] };
  useOptimizationGoal.value = false;
  selected.value = null;
  output.value = "";
  saveFilePath.value = "";
}

async function recycleCurrentSave() {
  if (!currentSavePath.value) return;
  busy.value = true;
  try {
    const deleted = await call<RecycledStrategyFile>("recycle_strategy_save_file_command", { path: currentSavePath.value });
    showUndoToast(deleted);
    loadedSavePaths.value = loadedSavePaths.value.filter((path) => path !== deleted.original_path);
    const previous = loadedSavePaths.value[loadedSavePaths.value.length - 1] ?? deleted.previous_path;
    if (previous) await loadStrategyPath(previous);
    else clearLoadedStrategy();
    await refresh();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
  }
}

function inferredRedoContext(): RedoContext {
  const match = currentSavePath.value.match(/-(raw|optimized|auto)-\d+(?:\.\d+)?-\d{8}\.sqlite3$/);
  return {
    strategy: clonePayload(strategy.value),
    run_type: (match?.[1] as RunType | undefined) ?? "raw",
    metrics: clonePayload(selected.value?.metrics ?? {}),
    goal: strategy.value.optimization_goal,
  };
}

async function redoCurrentPrompt() {
  if (!currentSavePath.value) return;
  const context = lastRedoContext.value ?? inferredRedoContext();
  const redoSource = currentSavePath.value;
  busy.value = true;
  runningPrompt.value = "redo";
  startProgress("manual", "Preparing redo", 10);
  let deleted: RecycledStrategyFile | null = null;
  try {
    deleted = await call<RecycledStrategyFile>("recycle_strategy_save_file_command", { path: redoSource });
    dismissUndoToast();
    loadedSavePaths.value = loadedSavePaths.value.filter((path) => path !== redoSource);
    updateProgress("Running Vibe-Trading redo", 45);
    const run = await call<StrategyRun>("redo_strategy_backtest", { ...context, redo_source: redoSource });
    updateProgress("Saving redo snapshot", 85);
    if (run.error) throw new Error(run.error);
    await applyRun(run);
    lastRedoContext.value = context;
  } catch (cause) {
    let message = String(cause);
    if (deleted) {
      try {
        const restored = await call<string>("restore_strategy_save_file_command", deleted);
        await loadStrategyPath(restored);
      } catch (restoreCause) {
        message += `\n\nCould not restore the deleted snapshot: ${String(restoreCause)}`;
      }
    }
    if (!deleted) clearLoadedStrategy();
    error.value = message;
  } finally {
    busy.value = false;
    runningPrompt.value = null;
    finishProgress("manual");
  }
}

async function undoRecycle() {
  if (!recentDeletion.value) return;
  const deletion = recentDeletion.value;
  busy.value = true;
  try {
    const restored = await call<string>("restore_strategy_save_file_command", deletion);
    dismissUndoToast();
    await loadStrategyPath(restored);
  } catch (cause) {
    error.value = String(cause);
  } finally {
    busy.value = false;
  }
}

function loadStrategy(value: Strategy) {
  strategy.value = clonePayload(value);
  saveFilePath.value = value.strategy_file ?? "";
  useOptimizationGoal.value = Boolean(value.optimization_goal);
  rememberSavePath(value.strategy_file);
}

function parameterState(parameter: Parameter) {
  if (parameter.locked) return "border-warning bg-warning/10";
  return parameter.enabled
    ? "border-primary bg-primary/10"
    : "border-base-300 bg-base-100 opacity-70";
}

function toggleParameterLock(parameter: Parameter) {
  parameter.locked = !parameter.locked;
  if (parameter.locked) parameter.enabled = false;
}

function isNumber(value: unknown) {
  return (
    (typeof value === "number" && Number.isFinite(value)) ||
    (typeof value === "string" &&
      value.trim() !== "" &&
      Number.isFinite(Number(value)))
  );
}

function formatMetric(value: unknown) {
  return isNumber(value)
    ? Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })
    : String(value ?? "—");
}

function metricTone(name: string, value: unknown) {
  if (!isNumber(value) || /trade count|holding|turnover|adjustment/i.test(name))
    return "text-base-content";
  const numeric = Number(value);
  if (/drawdown/i.test(name))
    return numeric < 0
      ? "text-error"
      : numeric === 0
        ? "text-warning"
        : "text-success";
  if (/win rate/i.test(name))
    return numeric >= 50
      ? "text-success"
      : numeric > 0
        ? "text-warning"
        : "text-error";
  if (/profit factor/i.test(name))
    return numeric > 1
      ? "text-success"
      : numeric === 1
        ? "text-warning"
        : "text-error";
  return numeric > 0
    ? "text-success"
    : numeric < 0
      ? "text-error"
      : "text-warning";
}

function tradeValueTone(column: string, value: unknown) {
  if (/^side$/i.test(column)) {
    if (/^(buy|long)$/i.test(String(value))) return "text-success";
    if (/^(sell|short)$/i.test(String(value))) return "text-error";
    return "text-warning";
  }
  return /pnl|profit|return|drawdown|fee|commission/i.test(column)
    ? metricTone(column, value)
    : "";
}

function displayMetricName(name: string) {
  return name.replace(/^Vibe:\s*/, "");
}

function canonicalMetricName(name: string) {
  const title = displayMetricName(name).toLowerCase();
  return (
    {
      "total return": "return [%]",
      "p/l [%]": "return [%]",
      "win rate": "win rate [%]",
      "avg drawdown": "avg. drawdown [%]",
      "max drawdown": "max. drawdown [%]",
      "trade count": "total trades",
      sharpe: "sharpe ratio",
      sortino: "sortino ratio",
    }[title] ?? title
  );
}

function metricGroup(name: string) {
  const title = displayMetricName(name).toLowerCase();
  if (
    [
      "p/l",
      "p/l [%]",
      "return [%]",
      "win rate [%]",
      "avg. drawdown [%]",
      "max. drawdown [%]",
      "total trades",
      "profit factor",
      "sharpe ratio",
      "sortino ratio",
    ].includes(title)
  )
    return "Core metrics";
  if (/drawdown|risk|volatility/.test(title)) return "Risk";
  if (/trade|win rate|exposure|turnover|holding/.test(title))
    return "Trading activity";
  if (/return|profit|p\/l|sharpe|sortino|sqn/.test(title)) return "Performance";
  return "Additional metrics";
}

function metricPillTone(name: string) {
  const group = metricGroup(name);
  if (group === "Risk") return "badge-warning";
  if (group === "Performance") return "badge-success";
  if (group === "Trading activity") return "badge-info";
  return "badge-primary";
}

function toggleAutoTarget(metric: string) {
  autoTargetMetrics.value = autoTargetMetrics.value.includes(metric)
    ? autoTargetMetrics.value.filter((item) => item !== metric)
    : [...autoTargetMetrics.value, metric];
}

const autoTargetPresets = [
  { name: "Core", metrics: ["return [%]", "max. drawdown [%]", "sharpe ratio", "profit factor"] },
  { name: "Profitability", metrics: ["return [%]", "p/l", "p/l [%]", "profit factor", "win rate [%]"] },
  { name: "Risk-adjusted", metrics: ["max. drawdown [%]", "avg. drawdown [%]", "sharpe ratio", "sortino ratio"] },
] as const;

function presetMetrics(metrics: readonly string[]) {
  return goalMetricChoices.value.filter((metric) => metrics.includes(canonicalMetricName(metric) as (typeof metrics)[number]));
}

function applyAutoTargetPreset(metrics: readonly string[]) {
  autoTargetMetrics.value = presetMetrics(metrics);
}

function autoTargetPresetActive(metrics: readonly string[]) {
  const selected = presetMetrics(metrics);
  return selected.length > 0 && selected.length === autoTargetMetrics.value.length && selected.every((metric) => autoTargetMetrics.value.includes(metric));
}

function toggleSort(column: string) {
  if (sortColumn.value !== column) {
    sortColumn.value = column;
    sortDirection.value = "asc";
  } else if (sortDirection.value === "asc") sortDirection.value = "desc";
  else if (sortDirection.value === "desc") {
    sortColumn.value = null;
    sortDirection.value = null;
  } else sortDirection.value = "asc";
  tradePage.value = 1;
}

function toggleAutoTrialSort(column: AutoTrialColumn) {
  if (autoTrialSortColumn.value !== column) {
    autoTrialSortColumn.value = column;
    autoTrialSortDirection.value = "asc";
  } else if (autoTrialSortDirection.value === "asc") autoTrialSortDirection.value = "desc";
  else if (autoTrialSortDirection.value === "desc") {
    autoTrialSortColumn.value = null;
    autoTrialSortDirection.value = null;
  } else autoTrialSortDirection.value = "asc";
  autoTrialPage.value = 1;
}

function autoTrialValue(trial: AutoTrial, column: AutoTrialColumn): string | number {
  if (column === "Trial") return trial.number;
  if (column === "Status") return trial.status;
  if (column === "Score") return trial.score ?? "";
  return trial.parameters.map((parameter) => `${parameter.name}=${parameter.value}`).join(", ") || trial.error;
}

function openParameterModal(trial: AutoTrial) {
  parameterTrial.value = trial;
  comparedTrial.value = null;
  comparePickerOpen.value = false;
}

function closeParameterModal() {
  parameterTrial.value = null;
  comparedTrial.value = null;
  comparePickerOpen.value = false;
}

function openComparePicker() {
  compareTrialNumber.value = comparedTrial.value?.number ?? null;
  compareSearch.value = "";
  comparePickerOpen.value = true;
}

function confirmComparison() {
  comparedTrial.value = autoWorkflow.value?.trials.find((trial) => trial.number === compareTrialNumber.value) ?? null;
  comparePickerOpen.value = false;
}

function parameterValue(trial: AutoTrial | null, name: string) {
  return trial?.parameters.find((parameter) => parameter.name === name)?.value ?? "—";
}

function parameterDiff(name: string) {
  const base = Number(parameterValue(parameterTrial.value, name));
  const comparison = Number(parameterValue(comparedTrial.value, name));
  return Number.isFinite(base) && Number.isFinite(comparison) ? comparison - base : null;
}

function formatParameterDiff(diff: number | null) {
  if (diff === null) return "—";
  const value = Number(diff.toFixed(8));
  return `(${value > 0 ? "+" : ""}${value})`;
}

function parameterDiffTone(diff: number | null) {
  return diff === null || diff === 0 ? "text-base-content/60" : diff > 0 ? "text-success" : "text-error";
}

const metricGroups = computed(() => {
  const order = [
    "Core metrics",
    "Performance",
    "Risk",
    "Trading activity",
    "Additional metrics",
  ];
  const groups = new Map(order.map((title) => [title, [] as Metric[]]));
  const entries = Object.entries(visibleBacktest.value?.metrics ?? {});
  for (const metric of entries) {
    const canonical = canonicalMetricName(metric[0]);
    const hasCanonicalMetric = entries.some(
      ([name]) =>
        name !== metric[0] &&
        canonicalMetricName(name) === canonical &&
        canonicalMetricName(name) === displayMetricName(name).toLowerCase(),
    );
    if (!hasCanonicalMetric) groups.get(metricGroup(metric[0]))?.push(metric);
  }
  return order
    .map((title) => ({ title, metrics: groups.get(title) ?? [] }))
    .filter((group) => group.metrics.length);
});
const tradeColumns = computed(() => [
  ...new Set(
    visibleBacktest.value?.trades.flatMap((trade) => Object.keys(trade)) ?? [],
  ),
]);
const sortedTrades = computed(() => {
  const trades = [...(visibleBacktest.value?.trades ?? [])];
  if (!sortColumn.value || !sortDirection.value) return trades;
  const column = sortColumn.value;
  const direction = sortDirection.value === "asc" ? 1 : -1;
  return trades.sort((left, right) => {
    const a = left[column];
    const b = right[column];
    if (isNumber(a) && isNumber(b)) return (Number(a) - Number(b)) * direction;
    return (
      String(a ?? "").localeCompare(String(b ?? ""), undefined, {
        numeric: true,
      }) * direction
    );
  });
});
const totalTradePages = computed(() =>
  Math.max(1, Math.ceil(sortedTrades.value.length / tradesPerPage)),
);
const pagedTrades = computed(() =>
  sortedTrades.value.slice(
    (tradePage.value - 1) * tradesPerPage,
    tradePage.value * tradesPerPage,
  ),
);
const autoTrialColumns: AutoTrialColumn[] = ["Trial", "Status", "Score", "Parameters"];
const sortedAutoTrials = computed(() => {
  const trials = [...(autoWorkflow.value?.trials ?? [])];
  if (!autoTrialSortColumn.value || !autoTrialSortDirection.value) return trials;
  const column = autoTrialSortColumn.value;
  const direction = autoTrialSortDirection.value === "asc" ? 1 : -1;
  return trials.sort((left, right) => {
    const a = autoTrialValue(left, column);
    const b = autoTrialValue(right, column);
    if (isNumber(a) && isNumber(b)) return (Number(a) - Number(b)) * direction;
    return String(a).localeCompare(String(b), undefined, { numeric: true }) * direction;
  });
});
const totalAutoTrialPages = computed(() => Math.max(1, Math.ceil(sortedAutoTrials.value.length / tradesPerPage)));
const pagedAutoTrials = computed(() => sortedAutoTrials.value.slice((autoTrialPage.value - 1) * tradesPerPage, autoTrialPage.value * tradesPerPage));
const comparisonParameterNames = computed(() => {
  const names = [
    ...(parameterTrial.value?.parameters.map((parameter) => parameter.name) ?? []),
    ...(comparedTrial.value?.parameters.map((parameter) => parameter.name) ?? []),
  ];
  return [...new Set(names)];
});
const filteredComparisonTrials = computed(() => {
  const query = compareSearch.value.trim().toLowerCase();
  return (autoWorkflow.value?.trials ?? []).filter((trial) => trial.number !== parameterTrial.value?.number && (!query || `trial ${trial.number} ${trial.status} ${autoTrialValue(trial, "Parameters")}`.toLowerCase().includes(query)));
});

const visibleBacktest = computed(() => activeTab.value === "auto" ? autoWorkflow.value?.best_backtest ?? autoStartBacktest.value ?? selected.value : selected.value);
const autoBaseline = computed(() => autoStartBacktest.value ?? selected.value);
const goalMetricChoices = computed(() => Object.keys(autoBaseline.value?.metrics ?? {}));
const filteredGoalMetricChoices = computed(() => {
  const query = autoTargetSearch.value.trim().toLowerCase();
  return query ? goalMetricChoices.value.filter((metric) => displayMetricName(metric).toLowerCase().includes(query)) : goalMetricChoices.value;
});

watch([selected, visibleBacktest], () => {
  tradePage.value = 1;
  sortColumn.value = null;
  sortDirection.value = null;
});
watch(() => autoWorkflow.value?.path, () => {
  autoTrialPage.value = 1;
  autoTrialSortColumn.value = null;
  autoTrialSortDirection.value = null;
});
watch(autoWorkflow, updateAutoPolling, { deep: true });
onMounted(async () => { await refresh(); await refreshAutoWorkflows(); });
onBeforeUnmount(() => { dismissUndoToast(); if (autoPoll) clearInterval(autoPoll); });
</script>

<template>
  <main class="h-screen snap-y snap-mandatory overflow-y-auto">
    <section
      class="mx-auto flex min-h-screen max-w-5xl snap-start flex-col justify-center gap-5 px-4 py-8 sm:px-8"
    >
      <header>
        <p class="text-sm text-base-content/60">
          Local companion for Vibe-Trading
        </p>
        <h1 class="text-3xl font-semibold">Backtest Studio</h1>
        <p class="mt-1 text-base-content/70">
          Describe a strategy here, then run its complete backtest below.
        </p>
      </header>
      <div class="card bg-base-200">
        <div class="card-body">
          <h2 class="card-title font-semibold">Strategy controls</h2>
          <div class="grid gap-3 md:grid-cols-2">
            <fieldset class="fieldset">
              <legend class="fieldset-legend">Name</legend>
              <input
                v-model="strategy.name"
                class="input w-full"
                placeholder="VWAP ATR trail"
              />
            </fieldset>
            <fieldset class="fieldset">
              <legend class="fieldset-legend">Workspace</legend>
              <input
                v-model="strategy.workspace_path"
                class="input w-full"
                placeholder="Project data directory"
              />
              <p class="label">
                Each completed run exports a named SQLite save file here.
              </p>
            </fieldset>
            <fieldset class="fieldset md:col-span-2">
              <legend class="fieldset-legend">Prompt</legend>
              <textarea
                v-model="strategy.source"
                class="textarea h-48 w-full"
                placeholder="Describe the indicators, entries, exits, risk controls, market, and timeframe."
              />
            </fieldset>
          </div>
          <div class="card-actions mt-4 justify-start">
            <button
              class="btn btn-primary"
              :disabled="busy || !strategy.name || !strategy.source"
              @click="runRaw"
            >
              <span>Run strategy</span
              ><span
                v-if="runningPrompt === 'raw'"
                role="status"
                aria-label="Running strategy"
                class="loading loading-spinner loading-sm"
              ></span></button
            ><button
              class="btn"
              :disabled="busy || !selected || !strategy.parameters.length"
              @click="optimize"
            >
              <span>Auto optimize parameters</span
              ><span
                v-if="runningPrompt === 'optimized'"
                role="status"
                aria-label="Optimizing strategy"
                class="loading loading-spinner loading-sm"
              ></span></button
            ><button
              class="btn"
              :disabled="busy || !selected"
              @click="autoOptimize"
            >
              <span>Auto optimize from results</span
              ><span
                v-if="runningPrompt === 'auto'"
                role="status"
                aria-label="Auto optimizing strategy"
                class="loading loading-spinner loading-sm"
              ></span>
            </button>
          </div>
          <label class="mt-3 flex items-center gap-2 text-sm">
            <input
              v-model="useOptimizationGoal"
              type="checkbox"
              class="checkbox checkbox-primary checkbox-sm"
            />
            Use an optimization goal
          </label>
          <fieldset v-if="useOptimizationGoal" class="fieldset mt-2">
            <legend class="fieldset-legend">Optimization goal</legend>
            <textarea
              v-model="strategy.optimization_goal"
              class="textarea h-24 w-full"
              placeholder="For example: reduce maximum drawdown while retaining as much return as possible."
            />
          </fieldset>
          <div v-if="strategy.parameters.length" class="mt-4">
            <h3 class="font-medium">Strategy parameters</h3>
            <p class="mt-1 text-sm text-base-content/70">
              Checked parameters can be optimized. Locked parameters stay fixed.
            </p>
            <ul class="list mt-2 rounded-box border border-base-300">
              <li
                v-for="parameter in strategy.parameters"
                :key="parameter.name"
                class="list-row border-b border-base-300 last:border-b-0"
                :class="parameterState(parameter)"
              >
                <input
                  v-model="parameter.enabled"
                  type="checkbox"
                  class="checkbox checkbox-primary"
                  :disabled="parameter.locked"
                  :aria-label="`Optimize ${parameter.name}`"
                />
                <div class="list-col-grow">
                  <div class="font-medium">{{ parameter.name }}</div>
                  <div class="text-sm text-base-content/70">
                    {{ parameter.value
                    }}<span v-if="parameter.notes">
                      · {{ parameter.notes }}</span
                    ><span v-if="parameter.locked"> · Do not edit</span>
                  </div>
                </div>
                <button
                  type="button"
                  class="btn btn-sm"
                  :class="parameter.locked ? 'btn-warning' : 'btn-ghost'"
                  :aria-pressed="parameter.locked"
                  @click="toggleParameterLock(parameter)"
                >
                  {{ parameter.locked ? "Unlock" : "Lock" }}
                </button>
              </li>
            </ul>
          </div>
          <fieldset class="fieldset mt-4">
            <legend class="fieldset-legend">Load strategy save file</legend>
            <div class="join w-full">
              <input
                v-model="saveFilePath"
                class="input join-item w-full"
                placeholder="C:\path\to\strategy-raw-1-10262026.sqlite3"
              /><button
                class="btn join-item"
                :disabled="busy"
                @click="chooseStrategyFile"
              >
                Browse</button
              ><button
                class="btn join-item"
                :disabled="busy || !saveFilePath"
                @click="loadStrategyFile"
              >
                Load
              </button>
            </div>
          </fieldset>
          <div
            v-if="strategies.length"
            class="mt-3 border-t border-base-300 pt-3"
          >
            <p class="mb-2 text-sm font-medium">Saved strategies</p>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="item in strategies"
                :key="item.id"
                class="btn btn-sm"
                :disabled="busy"
                @click="loadStrategy(item)"
              >
                {{ item.name }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section
      ref="resultsPanel"
      class="mx-auto min-h-screen max-w-5xl snap-start px-4 py-8 sm:px-8"
    >
      <div v-if="error" role="alert" class="alert alert-error mb-5">
        <span>{{ error }}</span>
      </div>
      <div role="tablist" class="tabs tabs-box mb-5">
        <button role="tab" class="tab" :class="{ 'tab-active': activeTab === 'manual' }" @click="activeTab = 'manual'">Manual</button>
        <button role="tab" class="tab" :class="{ 'tab-active': activeTab === 'auto' }" @click="activeTab = 'auto'">Auto</button>
      </div>
      <section v-if="activeTab === 'auto'" class="card bg-base-200 mb-5">
        <div class="card-body">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div><h2 class="card-title font-semibold">Automated optimization</h2><p class="text-sm text-base-content/70">Each trial runs after the prior one finishes. It stops after the budget or when selected targets improve without materially weakening quality guardrails.</p></div>
            <button v-if="autoWorkflow && ['queued', 'running'].includes(autoWorkflow.status)" class="btn btn-error" :disabled="autoBusy" @click="stopAutoWorkflow">Stop after current prompt</button>
          </div>
          <div class="grid gap-3 md:grid-cols-2">
            <fieldset class="fieldset"><legend class="fieldset-legend">Starting snapshot</legend><div class="join w-full"><input v-model="autoStartPath" class="input join-item w-full" :placeholder="currentSavePath || 'Choose a strategy save with results'" /><button class="btn join-item" :disabled="autoBusy" @click="chooseAutoStartFile">Browse</button><button class="btn join-item" :disabled="autoBusy || !autoStartPath" @click="loadAutoStartFile">Load targets</button></div><p class="label">Loads metrics here only; it does not add anything to Manual history.</p></fieldset>
            <fieldset class="fieldset"><legend class="fieldset-legend">Optimization budget</legend><input v-model.number="autoPromptLimit" type="number" min="1" max="50" class="input w-full" /><p class="label">{{ autoEngine === 'vibe' ? 'Maximum completed Vibe prompts.' : 'Maximum Backtesting.py parameter evaluations.' }}</p></fieldset>
          </div>
          <fieldset class="fieldset mt-2"><legend class="fieldset-legend">Early-win targets</legend><p class="mb-2 text-sm text-base-content/70">Selected metrics must improve. Return, P/L, win rate, profit factor, Sharpe, Sortino, and drawdown remain guardrails and can only deviate slightly from the starting snapshot.</p><div v-if="goalMetricChoices.length" class="mb-3 flex flex-wrap items-center gap-2"><span class="text-sm text-base-content/60">Presets</span><button v-for="preset in autoTargetPresets" :key="preset.name" type="button" class="btn btn-sm" :class="autoTargetPresetActive(preset.metrics) ? 'btn-primary' : 'btn-ghost'" @click="applyAutoTargetPreset(preset.metrics)">{{ preset.name }}</button></div><div v-if="goalMetricChoices.length" class="grid gap-3 md:grid-cols-5"><div class="card card-border bg-base-100 md:col-span-2"><div class="card-body gap-2 p-3"><input v-model="autoTargetSearch" class="input input-sm w-full" placeholder="Search metrics" aria-label="Search early-win metrics" /><ul class="list max-h-56 overflow-y-auto"><li v-for="metric in filteredGoalMetricChoices" :key="metric" class="list-row cursor-pointer px-2 py-2 hover:bg-base-200" :class="autoTargetMetrics.includes(metric) ? 'bg-primary/10' : ''" @click="toggleAutoTarget(metric)"><div class="list-col-grow text-sm">{{ displayMetricName(metric) }}</div><span class="badge badge-sm" :class="autoTargetMetrics.includes(metric) ? 'badge-primary' : 'badge-ghost'">{{ autoTargetMetrics.includes(metric) ? 'Selected' : 'Add' }}</span></li><li v-if="!filteredGoalMetricChoices.length" class="px-2 py-3 text-sm text-base-content/60">No matching metrics.</li></ul></div></div><div class="card card-border bg-base-100 md:col-span-3"><div class="card-body p-3"><p class="mb-2 text-sm font-medium text-base-content/70">Selected targets</p><div v-if="autoTargetMetrics.length" class="flex flex-wrap content-start items-start justify-start gap-2"><button v-for="metric in autoTargetMetrics" :key="metric" type="button" class="badge badge-lg badge-soft cursor-pointer gap-1" :class="metricPillTone(metric)" :aria-label="`Remove ${displayMetricName(metric)}`" @click="toggleAutoTarget(metric)"><span>{{ displayMetricName(metric) }}</span><span aria-hidden="true">×</span></button></div><p v-else class="text-sm text-base-content/60">Choose one or more metrics from the list.</p></div></div></div><p v-else class="text-sm text-base-content/60">Choose a starting snapshot above to load its measurable targets.</p></fieldset>
          <div class="card-actions mt-3 items-end justify-start gap-3"><fieldset class="fieldset w-full max-w-xs"><legend class="fieldset-legend">Optimization engine</legend><select v-model="autoEngine" class="select w-full" aria-label="Optimization engine"><option value="vibe">VibeTrading</option><option value="backtesting">Backtesting.py</option></select></fieldset><fieldset v-if="autoEngine === 'backtesting'" class="fieldset w-full max-w-md"><legend class="fieldset-legend">OHLCV reference data</legend><div class="join w-full"><select v-model="autoOhlcvPath" class="select join-item w-full" aria-label="OHLCV reference data"><option value="">Use snapshot-configured cached data</option><option v-for="path in referenceOhlcvFiles" :key="path" :value="path">{{ referenceOhlcvLabel(path) }}</option></select><button class="btn join-item" :disabled="autoBusy" @click="chooseAutoOhlcvFile">Browse</button></div><p class="label">CSV files under data/references; select a filename for a different timeframe.</p></fieldset><button class="btn btn-primary" :disabled="autoBusy || (!selected && !autoStartPath && !currentSavePath)" @click="startAutoWorkflow"><span>{{ autoEngine === 'vibe' ? 'Start auto workflow' : 'Run Backtesting.py optimizer' }}</span><span v-if="autoBusy" class="loading loading-spinner loading-sm" role="status"></span></button></div>
          <div v-if="autoWorkflow" class="mt-4 border-t border-base-300 pt-4">
            <div class="mb-3 flex flex-wrap items-center justify-between gap-2"><div><h3 class="font-medium">{{ autoWorkflow.name }}</h3><p class="text-sm text-base-content/60">{{ autoWorkflow.completed_trials }} / {{ autoWorkflow.prompt_limit }} trials · {{ autoWorkflow.status.replace('_', ' ') }}</p></div><span class="badge" :class="autoWorkflow.status === 'goal_met' ? 'badge-success' : autoWorkflow.status === 'failed' ? 'badge-error' : 'badge-neutral'">{{ autoWorkflow.status }}</span></div>
            <OptimizationChart :trials="autoWorkflow.trials" />
            <div class="mt-4">
              <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
                <p class="text-sm text-base-content/60">{{ sortedAutoTrials.length }} evaluated configurations</p>
                <div class="join">
                  <button class="btn btn-sm join-item" :disabled="autoTrialPage === 1" @click="autoTrialPage--">Previous</button>
                  <span class="btn btn-sm join-item pointer-events-none">{{ autoTrialPage }} / {{ totalAutoTrialPages }}</span>
                  <button class="btn btn-sm join-item" :disabled="autoTrialPage === totalAutoTrialPages" @click="autoTrialPage++">Next</button>
                </div>
              </div>
              <div class="max-h-[30rem] overflow-auto rounded-box border border-base-300">
                <table class="table table-pin-rows table-zebra">
                  <thead><tr><th v-for="column in autoTrialColumns" :key="column"><button class="btn btn-ghost btn-xs whitespace-nowrap font-medium normal-case" @click="toggleAutoTrialSort(column)">{{ column }}<span v-if="autoTrialSortColumn === column" aria-hidden="true">{{ autoTrialSortDirection === 'asc' ? '▲' : '▼' }}</span></button></th></tr></thead>
                  <tbody><tr v-for="trial in pagedAutoTrials" :key="trial.number"><td>{{ trial.number }}</td><td>{{ trial.status }}</td><td :class="metricTone('score', trial.score)">{{ trial.score === null ? '—' : formatMetric(trial.score) }}</td><td class="max-w-md truncate"><button class="btn btn-ghost btn-xs w-full justify-start font-normal normal-case" @click="openParameterModal(trial)">{{ autoTrialValue(trial, 'Parameters') }}</button></td></tr></tbody>
                </table>
              </div>
            </div>
          </div>
          <div v-if="autoWorkflows.length" class="mt-4"><h3 class="mb-2 font-medium">Workflow history</h3><div class="flex flex-wrap gap-2"><button v-for="workflow in autoWorkflows" :key="workflow.path" class="btn btn-sm" :class="autoWorkflow?.path === workflow.path ? 'btn-neutral' : ''" :disabled="autoBusy" @click="loadAutoWorkflow(workflow.path)">{{ workflow.name }} · {{ workflow.status }}</button></div></div>
        </div>
      </section>
      <section v-if="activeTab === 'auto' && autoError" class="alert alert-error mb-5" role="alert">
        <span>{{ autoError }}</span>
      </section>
      <section class="card bg-base-200">
        <div class="card-body">
          <h2 class="card-title font-semibold">{{ activeTab === 'auto' ? 'Best automated result' : 'Data visualization' }}</h2>
          <div
            v-if="!visibleBacktest"
            class="flex min-h-64 items-center justify-center border border-base-300 text-center text-base-content/60"
          >
            {{ activeTab === 'auto' ? 'Start an auto workflow to view its current best result.' : 'Run a strategy to view its metrics, equity curve, and trades.' }}
          </div>
          <template v-else
            ><section
              v-for="group in metricGroups"
              :key="group.title"
              class="mt-4 first:mt-0"
            >
              <h3 class="mb-3 text-sm font-medium text-base-content/70">
                {{ group.title }}
              </h3>
              <div
                class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
              >
                <article
                  v-for="[key, value] in group.metrics"
                  :key="key"
                  class="card card-border bg-base-100"
                >
                  <div class="card-body gap-1 p-4">
                    <p class="text-sm font-normal text-base-content/60">
                      {{ displayMetricName(key) }}
                    </p>
                    <p
                      class="text-xl font-semibold"
                      :class="metricTone(key, value)"
                    >
                      {{ formatMetric(value) }}
                    </p>
                  </div>
                </article>
              </div>
            </section>
            <div class="mt-5">
              <EquityChart
                :equity="visibleBacktest.equity_curve"
                :timestamps="visibleBacktest.equity_timestamps"
              />
            </div>
            <div class="mt-5">
              <div
                class="mb-3 flex flex-wrap items-center justify-between gap-2"
              >
                <div>
                  <h3 class="font-medium">Positions</h3>
                  <p class="text-sm text-base-content/60">
                    {{ sortedTrades.length }} records
                  </p>
                </div>
                <div class="join">
                  <button
                    class="btn btn-sm join-item"
                    :disabled="tradePage === 1"
                    @click="tradePage--"
                  >
                    Previous</button
                  ><span class="btn btn-sm join-item pointer-events-none"
                    >{{ tradePage }} / {{ totalTradePages }}</span
                  ><button
                    class="btn btn-sm join-item"
                    :disabled="tradePage === totalTradePages"
                    @click="tradePage++"
                  >
                    Next
                  </button>
                </div>
              </div>
              <div
                class="max-h-[30rem] overflow-auto rounded-box border border-base-300"
              >
                <table class="table table-pin-rows table-zebra">
                  <thead>
                    <tr>
                      <th v-for="column in tradeColumns" :key="column">
                        <button
                          class="btn btn-ghost btn-xs whitespace-nowrap font-medium normal-case"
                          @click="toggleSort(column)"
                        >
                          {{ column
                          }}<span
                            v-if="sortColumn === column"
                            aria-hidden="true"
                            >{{ sortDirection === "asc" ? "▲" : "▼" }}</span
                          >
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(trade, index) in pagedTrades" :key="index">
                      <td v-for="column in tradeColumns" :key="column">
                        <span :class="tradeValueTone(column, trade[column])">{{
                          trade[column]
                        }}</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div></template
          >
        </div>
      </section>
      <section v-if="activeTab === 'manual'" class="card bg-base-200 mt-5">
        <div class="card-body">
          <h2 class="card-title font-semibold">Import and history</h2>
          <div class="grid gap-5 lg:grid-cols-2">
            <div>
              <p class="mb-2 text-sm text-base-content/70">
                Import an existing JSON backtest.
              </p>
              <input
                type="file"
                accept="application/json,.json"
                class="file-input w-full"
                :disabled="busy"
                @change="importResult"
              />
            </div>
            <div>
              <div class="mb-2 flex items-center justify-between gap-2">
                <h3 class="font-medium">Run history</h3>
                <button
                  class="btn btn-error btn-soft btn-xs"
                  :disabled="busy || !history.length"
                  @click="clearHistory"
                >
                  Clear all
                </button>
              </div>
              <div v-if="history.length" class="divide-y divide-base-300">
                <div
                  v-for="item in history"
                  :key="item.id"
                  class="flex items-center gap-2 py-3"
                >
                  <button
                    class="min-w-0 flex-1 text-left hover:underline"
                    :disabled="busy"
                    @click="selectBacktest(item.id)"
                  >
                    <span class="block font-medium">{{ item.name }}</span>
                    <span class="text-xs text-base-content/60">{{ item.imported_at }}</span>
                  </button>
                  <button
                    class="btn btn-ghost btn-square btn-xs text-error"
                    :disabled="busy"
                    :aria-label="`Delete ${item.name} from history`"
                    @click="deleteHistory(item.id)"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-4"><path d="M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14M10 11v6m4-6v6" /></svg>
                  </button>
                </div>
              </div>
              <p v-else class="text-sm text-base-content/60">
                No saved runs yet.
              </p>
            </div>
          </div>
        </div>
      </section>
      <div v-if="activeTab === 'manual'" class="card bg-base-200 mt-5">
        <div class="card-body">
          <h2 class="card-title font-semibold">Prompt result</h2>
          <textarea
            class="textarea h-52 w-full font-mono text-xs"
            readonly
            :value="output"
            placeholder="The raw Vibe-Trading response will appear here."
          />
        </div>
      </div>
    </section>
  </main>
  <div v-if="globalProgress" class="fixed inset-x-0 bottom-0 z-[55] bg-base-300 px-4 py-2 sm:px-8">
    <div class="mb-1 flex items-center justify-between gap-4 text-xs text-base-content/80"><span>{{ globalProgress.label }}</span><span>{{ globalProgress.percent }}%</span></div>
    <progress class="progress progress-primary block h-1 w-full" :value="globalProgress.percent" max="100"></progress>
  </div>
  <div
    v-if="currentSavePath && saveControlsOpen"
    class="pointer-events-none fixed inset-x-0 bottom-0 z-40 h-32 bg-gradient-to-t from-base-100 via-base-100/90 to-transparent shadow-[inset_0_-2rem_2rem_-2rem_rgb(0_0_0_/_0.7)]"
  ></div>
  <div v-if="currentSavePath" class="fixed left-1/2 z-50 flex -translate-x-1/2 items-center gap-3" :class="globalProgress ? 'bottom-20' : 'bottom-6'">
    <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="translate-y-3 opacity-0" enter-to-class="translate-y-0 opacity-100" leave-active-class="transition duration-150 ease-in" leave-from-class="translate-y-0 opacity-100" leave-to-class="translate-y-3 opacity-0">
      <div v-if="saveControlsOpen" class="tooltip tooltip-top" data-tip="Save a copy to data/good">
        <button class="btn btn-success btn-circle" :disabled="busy" aria-label="Save current strategy as good" @click="copyCurrentSaveToGood">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-5"><path d="M7 10v10H4.5A1.5 1.5 0 0 1 3 18.5v-7A1.5 1.5 0 0 1 4.5 10H7Zm0 10h9.2a2 2 0 0 0 1.9-1.38l2-6A2 2 0 0 0 18.2 10H15l.35-3.1A3 3 0 0 0 12.37 3.5L7 10" /></svg>
        </button>
      </div>
    </Transition>
    <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="translate-y-3 opacity-0" enter-to-class="translate-y-0 opacity-100" leave-active-class="transition duration-150 ease-in" leave-from-class="translate-y-0 opacity-100" leave-to-class="translate-y-3 opacity-0">
      <div v-if="saveControlsOpen" class="tooltip tooltip-top" data-tip="Redo the last strategy prompt">
        <button class="btn btn-neutral btn-circle" :disabled="busy" aria-label="Redo current strategy prompt" @click="redoCurrentPrompt">
          <span v-if="runningPrompt === 'redo'" role="status" aria-label="Redoing strategy" class="loading loading-spinner loading-sm"></span>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-5"><path d="M21 12a9 9 0 1 1-3.1-6.8M21 4v6h-6" /></svg>
        </button>
      </div>
    </Transition>
    <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="translate-y-3 opacity-0" enter-to-class="translate-y-0 opacity-100" leave-active-class="transition duration-150 ease-in" leave-from-class="translate-y-0 opacity-100" leave-to-class="translate-y-3 opacity-0">
      <div v-if="saveControlsOpen" class="tooltip tooltip-top" data-tip="Move this strategy save to the recycle bin">
        <button class="btn btn-error btn-circle" :disabled="busy" aria-label="Delete current strategy save" @click="recycleCurrentSave">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" class="size-5"><path d="M10 3h4l1 3h4v2h-2l-1 12a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 8H3V6h4l1-3Zm2 5a5 5 0 0 0-5 5c0 2.76 2.24 5 5 5s5-2.24 5-5a5 5 0 0 0-5-5Zm-1 2h2v2h-2v-2Zm0 4h2v2h-2v-2Z" /></svg>
        </button>
      </div>
    </Transition>
  </div>
  <button v-if="currentSavePath" class="btn btn-neutral btn-circle fixed right-6 z-50" :class="globalProgress ? 'bottom-20' : 'bottom-6'" :aria-label="saveControlsOpen ? 'Hide save controls' : 'Show save controls'" @click="saveControlsOpen = !saveControlsOpen">
    <svg v-if="saveControlsOpen" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-5"><path d="m6 9 6 6 6-6" /></svg>
    <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-5"><path d="m6 15 6-6 6 6" /></svg>
  </button>
  <div v-if="recentDeletion" class="toast toast-top toast-end z-[60]">
    <div class="alert bg-base-300 text-base-content shadow-lg">
      <span>Strategy save moved to recycle bin.</span>
      <button class="btn btn-ghost btn-sm text-base-content" :disabled="busy" @click="undoRecycle">Undo</button>
    </div>
  </div>
  <dialog v-if="parameterTrial" open class="modal modal-open" aria-modal="true" aria-label="Trial parameters">
    <div class="modal-box max-w-5xl">
      <button class="btn btn-ghost btn-sm btn-circle absolute right-3 top-3" aria-label="Close parameter details" @click="closeParameterModal"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-5"><path d="M6 6l12 12M18 6 6 18" /></svg></button>
      <div class="mb-4 flex items-center justify-between gap-3 pr-10"><div><h3 class="text-lg font-semibold">Trial parameters</h3><p class="text-sm text-base-content/60">Inspect a configuration or compare it with another trial.</p></div><button class="btn btn-sm" :disabled="(autoWorkflow?.trials.length ?? 0) < 2" @click="openComparePicker">Compare</button></div>
      <div class="flex flex-col items-stretch gap-4 lg:flex-row lg:items-center">
        <section class="min-w-0 flex-1"><h4 class="mb-2 text-center font-medium">Trial {{ parameterTrial.number }}</h4><div class="max-h-96 overflow-auto rounded-box border border-base-300"><table class="table table-sm"><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody><tr v-for="name in comparisonParameterNames" :key="name"><td>{{ name }}</td><td>{{ parameterValue(parameterTrial, name) }}</td></tr></tbody></table></div></section>
        <svg v-if="comparedTrial" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="mx-auto size-8 shrink-0 rotate-90 lg:rotate-0"><path d="M5 12h14m-5-5 5 5-5 5" /></svg>
        <section v-if="comparedTrial" class="min-w-0 flex-1"><h4 class="mb-2 text-center font-medium">Trial {{ comparedTrial.number }}</h4><div class="max-h-96 overflow-auto rounded-box border border-base-300"><table class="table table-sm"><thead><tr><th>Parameter</th><th>Value</th><th>Diff</th></tr></thead><tbody><tr v-for="name in comparisonParameterNames" :key="name"><td>{{ name }}</td><td>{{ parameterValue(comparedTrial, name) }}</td><td :class="parameterDiffTone(parameterDiff(name))">{{ formatParameterDiff(parameterDiff(name)) }}</td></tr></tbody></table></div></section>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop"><button aria-label="Close parameter details" @click.prevent="closeParameterModal">close</button></form>
    <div v-if="comparePickerOpen" class="modal modal-open z-[70]" role="dialog" aria-modal="true" aria-label="Choose trial to compare">
    <div class="modal-box max-w-lg"><h3 class="text-lg font-semibold">Compare with another trial</h3><input v-model="compareSearch" class="input mt-4 w-full" placeholder="Search trial number, status, or parameters" aria-label="Search trials" /><div class="mt-3 max-h-64 overflow-y-auto rounded-box border border-base-300"><button v-for="trial in filteredComparisonTrials" :key="trial.number" class="btn btn-ghost block h-auto w-full rounded-none px-4 py-3 text-left normal-case" :class="compareTrialNumber === trial.number ? 'bg-primary/10' : ''" @click="compareTrialNumber = trial.number"><span class="font-medium">Trial {{ trial.number }}</span><span class="ml-2 text-sm text-base-content/60">{{ trial.status }} · {{ trial.score === null ? '—' : formatMetric(trial.score) }}</span><span class="mt-1 block truncate text-xs text-base-content/60">{{ autoTrialValue(trial, 'Parameters') }}</span></button><p v-if="!filteredComparisonTrials.length" class="p-4 text-sm text-base-content/60">No other trials match this search.</p></div><div class="modal-action"><button class="btn" @click="comparePickerOpen = false">Cancel</button><button class="btn btn-primary" :disabled="compareTrialNumber === null" @click="confirmComparison">Compare</button></div></div>
      <div class="modal-backdrop"><button aria-label="Cancel comparison" @click="comparePickerOpen = false">close</button></div>
    </div>
  </dialog>
</template>
