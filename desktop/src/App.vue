<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { open, save } from "@tauri-apps/plugin-dialog";
import { pyInvoke } from "tauri-plugin-pytauri-api";
import EquityChart from "./components/EquityChart.vue";

type Parameter = { name: string; value: string; notes: string; enabled: boolean; locked: boolean };
type Strategy = { id?: number; name: string; source: string; workspace_path: string; template_id: string; parameters: Parameter[]; freqtrade_payload?: Record<string, unknown>; strategy_file?: string | null };
type Backtest = { id: number; name: string; imported_at: string; metrics: Record<string, unknown>; trades: Record<string, unknown>[]; equity_curve: number[]; equity_timestamps: string[] };
type StrategyRun = { strategy: Strategy; backtest: Backtest | null; output: string; error?: string | null };
type ValidationSlice = { label: string; timerange: string; backtest: Backtest };
type OptimizationGoal = { profile: "balanced" | "higher_frequency" | "return_focused" | "capital_preservation"; target_trades_per_year: number; min_trades_per_test: number; max_drawdown_pct: number; min_profit_factor: number };
type ValidationRun = { training: ValidationSlice; tests: ValidationSlice[]; stability_score: number; mean_return: number; return_stddev: number; total_test_trades: number; minimum_test_trades: number; coverage: string; output: string; snapshot_path?: string | null };
type Template = { id: string; label: string; entry_id: string; exit_id: string };
type StrategyComponent = { id: string; label: string; description: string };
type SortDirection = "asc" | "desc" | null;

const strategy = ref<Strategy>({ name: "", source: "", workspace_path: "", template_id: "fvg_atr", parameters: [] });
const templates = ref<Template[]>([]);
const entries = ref<StrategyComponent[]>([]);
const exits = ref<StrategyComponent[]>([]);
const entryId = ref("fvg");
const exitId = ref("atr_trailing");
const history = ref<Backtest[]>([]);
const selected = ref<Backtest | null>(null);
const configPath = ref("");
function calendarTimerange(years: number) {
  const end = new Date();
  const start = new Date(end);
  start.setFullYear(end.getFullYear() - years);
  const format = (value: Date) => `${value.getFullYear()}${String(value.getMonth() + 1).padStart(2, "0")}${String(value.getDate()).padStart(2, "0")}`;
  return `${format(start)}-${format(end)}`;
}
function calendarTimerangeMonths(months: number) {
  const end = new Date();
  const start = new Date(end);
  start.setMonth(start.getMonth() - months);
  const format = (value: Date) => `${value.getFullYear()}${String(value.getMonth() + 1).padStart(2, "0")}${String(value.getDate()).padStart(2, "0")}`;
  return `${format(start)}-${format(end)}`;
}
const timerange = ref(calendarTimerange(1));
const validationTimerange = ref(calendarTimerange(5));
const quickValidationTimerange = ref(calendarTimerangeMonths(30));
const epochs = ref(100);
const optimizationGoal = ref<OptimizationGoal>({ profile: "balanced", target_trades_per_year: 100, min_trades_per_test: 10, max_drawdown_pct: 25, min_profit_factor: 1.1 });
const exchange = ref("binance");
const tradingMode = ref("futures");
const pairs = ref("BTC/USDT:USDT");
const timeframes = ref("5m");
const output = ref("");
const error = ref("");
const busy = ref(false);
const activeTab = ref<"builder" | "optimizer" | "validation">("builder");
const validation = ref<ValidationRun | null>(null);
type Progress = { active: boolean; label: string; percent: number; sub_label: string; sub_percent: number; steps: string[] };
const progress = ref<Progress | null>(null);
let progressPoller: number | undefined;
const sortColumn = ref<string | null>(null);
const sortDirection = ref<SortDirection>(null);
const page = ref(1);
const perPage = 25;

async function call<T>(command: string, body?: unknown) {
  error.value = "";
  return pyInvoke<T>(command, body);
}

async function refreshProgress() {
  try {
    const current = await pyInvoke<Progress>("get_freqtrade_progress");
    if (current.active || busy.value) progress.value = current;
  } catch {
    // Browser previews do not have the PyTauri command bridge.
  }
}

function startProgress(label: string) {
  progress.value = { active: true, label, percent: 0, sub_label: "Preparing", sub_percent: 0, steps: [label] };
  if (progressPoller === undefined) progressPoller = window.setInterval(() => void refreshProgress(), 350);
}

function stopProgress() {
  if (progressPoller !== undefined) window.clearInterval(progressPoller);
  progressPoller = undefined;
  progress.value = null;
}

async function cancelRun() {
  try {
    await pyInvoke<boolean>("cancel_freqtrade_run");
    if (progress.value) progress.value = { ...progress.value, label: "Stopping Freqtrade process", sub_label: "Terminating the active Freqtrade process tree", steps: [...progress.value.steps, "Stopping Freqtrade process"] };
  } catch (cause) { error.value = String(cause); }
}

async function refresh() {
  const [workspace, savedTemplates, savedEntries, savedExits, savedHistory] = await Promise.all([
    call<string>("default_workspace"), call<Template[]>("list_freqtrade_templates"), call<StrategyComponent[]>("list_freqtrade_entries"), call<StrategyComponent[]>("list_freqtrade_exits"), call<Backtest[]>("list_imported_backtests"),
  ]);
  if (!strategy.value.workspace_path) strategy.value.workspace_path = workspace;
  templates.value = savedTemplates;
  entries.value = savedEntries;
  exits.value = savedExits;
  history.value = savedHistory;
}

function applyPreset() {
  const preset = templates.value.find((item) => item.id === strategy.value.template_id);
  if (!preset) return;
  entryId.value = preset.entry_id;
  exitId.value = preset.exit_id;
}

function syncPreset() {
  strategy.value.template_id = templates.value.find((item) => item.entry_id === entryId.value && item.exit_id === exitId.value)?.id || "custom";
}

async function createTemplate() {
  busy.value = true;
  try {
    strategy.value = await call<Strategy>("create_freqtrade_template", { name: strategy.value.name || templates.value.find((item) => item.id === strategy.value.template_id)?.label || "Freqtrade strategy", template_id: strategy.value.template_id, entry_id: entryId.value, exit_id: exitId.value, workspace_path: strategy.value.workspace_path });
    output.value = "Template created. Its parameter schema is deterministic and ready for Freqtrade hyperopt.";
  } catch (cause) { error.value = String(cause); } finally { busy.value = false; }
}

async function chooseConfig() {
  const path = await open({ filters: [{ name: "Freqtrade config", extensions: ["json"] }], multiple: false });
  if (typeof path === "string") configPath.value = path;
}

function serializableStrategy() {
  return JSON.parse(JSON.stringify(strategy.value)) as Strategy;
}

function hydrateGoal(next: unknown) {
  if (!next || typeof next !== "object") return;
  const value = next as Partial<OptimizationGoal>;
  if (["balanced", "higher_frequency", "return_focused", "capital_preservation"].includes(String(value.profile))) optimizationGoal.value.profile = value.profile as OptimizationGoal["profile"];
  for (const key of ["target_trades_per_year", "min_trades_per_test", "max_drawdown_pct", "min_profit_factor"] as const) {
    if (typeof value[key] === "number" && Number.isFinite(value[key])) optimizationGoal.value[key] = value[key];
  }
}

async function run(hyperopt = false) {
  busy.value = true;
  startProgress(hyperopt ? "Starting optimization" : "Starting backtest");
  try {
    const run = await call<StrategyRun>("run_freqtrade_backtest", { strategy: serializableStrategy(), config_path: configPath.value, exchange: exchange.value, trading_mode: tradingMode.value, pairs: pairs.value, timeframes: timeframes.value, timerange: timerange.value, hyperopt_epochs: hyperopt ? epochs.value : 0, optimization_goal: optimizationGoal.value });
    strategy.value = run.strategy;
    entryId.value = String(run.strategy.freqtrade_payload?.entry_id || entryId.value);
    exitId.value = String(run.strategy.freqtrade_payload?.exit_id || exitId.value);
    hydrateGoal(run.strategy.freqtrade_payload?.optimization_goal);
    output.value = run.output;
    if (run.error) error.value = run.error;
    if (run.backtest) selected.value = run.backtest;
    await refresh();
  } catch (cause) { error.value = String(cause); } finally { busy.value = false; stopProgress(); }
}

async function runValidation(quick = false) {
  busy.value = true;
  startProgress(quick ? "Starting quick validation" : "Starting walk-forward validation");
  try {
    validation.value = await call<ValidationRun>("run_freqtrade_validation", { strategy: serializableStrategy(), config_path: configPath.value, exchange: exchange.value, trading_mode: tradingMode.value, pairs: pairs.value, timeframes: timeframes.value, timerange: quick ? quickValidationTimerange.value : validationTimerange.value, validation_test_count: quick ? 5 : 10, optimization_goal: optimizationGoal.value });
    selected.value = validation.value.training.backtest;
    output.value = validation.value.output;
  } catch (cause) { error.value = String(cause); } finally { busy.value = false; stopProgress(); }
}

async function chooseSnapshot() {
  const path = await open({ defaultPath: strategy.value.workspace_path, filters: [{ name: "Freqtrade snapshot", extensions: ["sqlite", "sqlite3"] }], multiple: false });
  if (typeof path !== "string") return;
  try {
    const run = await call<StrategyRun>("load_strategy_save_file", { path });
    strategy.value = run.strategy;
    entryId.value = String(run.strategy.freqtrade_payload?.entry_id || entryId.value);
    exitId.value = String(run.strategy.freqtrade_payload?.exit_id || exitId.value);
    hydrateGoal(run.strategy.freqtrade_payload?.optimization_goal);
    selected.value = run.backtest;
    output.value = run.output;
  } catch (cause) { error.value = String(cause); }
}

async function exportStrategy() {
  if (!strategy.value.strategy_file) return;
  const path = await save({ defaultPath: `${strategy.value.name || "FreqtradeStrategy"}.py`, filters: [{ name: "Python strategy", extensions: ["py"] }] });
  if (typeof path !== "string") return;
  try { output.value = `Exported ${await call<string>("export_freqtrade_strategy", { path: strategy.value.strategy_file, destination: path })}`; } catch (cause) { error.value = String(cause); }
}

function selectHistory(item: Backtest) { selected.value = item; page.value = 1; sortColumn.value = null; sortDirection.value = null; }
function toggleSort(column: string) { sortDirection.value = sortColumn.value === column ? (sortDirection.value === "asc" ? "desc" : sortDirection.value === "desc" ? null : "asc") : "asc"; sortColumn.value = sortDirection.value ? column : null; page.value = 1; }
const tradeColumns = computed(() => Array.from(new Set((selected.value?.trades ?? []).flatMap((item) => Object.keys(item)))));
const sortedTrades = computed(() => {
  const items = [...(selected.value?.trades ?? [])];
  if (!sortColumn.value || !sortDirection.value) return items;
  return items.sort((left, right) => String(left[sortColumn.value!]).localeCompare(String(right[sortColumn.value!]), undefined, { numeric: true }) * (sortDirection.value === "asc" ? 1 : -1));
});
const visibleTrades = computed(() => sortedTrades.value.slice((page.value - 1) * perPage, page.value * perPage));
const pageCount = computed(() => Math.max(1, Math.ceil(sortedTrades.value.length / perPage)));
function metricValue(value: unknown) { return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 4 }) : String(value ?? "—"); }
function numericValue(value: unknown) { return typeof value === "number" ? value : typeof value === "string" && value.trim() !== "" ? Number(value) : Number.NaN; }
function valueTone(label: string, value: unknown) {
  const key = label.toLowerCase();
  if (key === "side" || key === "is_short") {
    const side = String(value).toLowerCase();
    return side === "short" || side === "sell" || value === true ? "text-error" : side === "long" || side === "buy" || value === false ? "text-success" : "text-base-content";
  }
  if (!/(profit|p\/l|pnl|return|win.?rate|sharpe|sortino|drawdown|loss|factor)/.test(key)) return "text-base-content";
  const numeric = numericValue(value);
  if (Number.isNaN(numeric)) return "text-base-content";
  if (key.includes("win")) return numeric >= 40 ? "text-success" : numeric >= 30 ? "text-warning" : "text-error";
  if (key.includes("factor")) return numeric >= 1.2 ? "text-success" : numeric >= 1 ? "text-warning" : "text-error";
  if (key.includes("sharpe") || key.includes("sortino")) return numeric >= 1 ? "text-success" : numeric >= 0 ? "text-warning" : "text-error";
  if (key.includes("drawdown")) return Math.abs(numeric) <= 15 ? "text-success" : Math.abs(numeric) <= 30 ? "text-warning" : "text-error";
  return numeric > 0 ? "text-success" : numeric < 0 ? "text-error" : "text-warning";
}
function tableValue(column: string, value: unknown) {
  if (column.toLowerCase() === "is_short" && typeof value === "boolean") return value ? "Short" : "Long";
  return metricValue(value);
}
onMounted(() => refresh().catch((cause) => error.value = String(cause)));
onBeforeUnmount(stopProgress);
</script>

<template>
  <main class="min-h-screen bg-base-300 px-4 py-8 sm:px-8">
    <section class="mx-auto max-w-6xl space-y-5">
      <header><p class="text-sm text-base-content/60">Local Freqtrade strategy studio</p><h1 class="text-3xl font-semibold">Backtest Studio</h1><p class="mt-1 text-base-content/70">Create deterministic strategies, run native Freqtrade backtests and hyperopt, then export portable snapshots.</p></header>
      <div v-if="error" role="alert" class="alert alert-error"><span>{{ error }}</span></div>
      <div role="tablist" class="tabs tabs-box w-fit" aria-label="Studio workflow">
        <button role="tab" class="tab gap-2" :class="activeTab === 'builder' ? 'tab-active' : ''" :aria-selected="activeTab === 'builder'" @click="activeTab = 'builder'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-4"><path d="M4 20h16M6 16l4-4 3 3 5-7" /></svg>Builder</button>
        <button role="tab" class="tab gap-2" :class="activeTab === 'optimizer' ? 'tab-active' : ''" :aria-selected="activeTab === 'optimizer'" @click="activeTab = 'optimizer'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-4"><path d="M4 6h16M4 12h10M4 18h6" /><circle cx="17" cy="12" r="2" /><circle cx="13" cy="18" r="2" /></svg>Optimizer</button>
        <button role="tab" class="tab gap-2" :class="activeTab === 'validation' ? 'tab-active' : ''" :aria-selected="activeTab === 'validation'" @click="activeTab = 'validation'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-4"><path d="M12 3v18M3 12h18" /><path d="m7 16 3-3 2 2 5-6" /></svg>Validation</button>
      </div>
      <section v-if="activeTab === 'builder'" class="card bg-base-200"><div class="card-body"><h2 class="card-title">Strategy builder</h2>
        <div class="grid gap-3 md:grid-cols-2">
          <fieldset class="fieldset"><legend class="fieldset-legend">Name</legend><input v-model="strategy.name" class="input w-full" placeholder="FVG ATR BTC 5m" /></fieldset>
          <fieldset class="fieldset"><legend class="fieldset-legend">Workspace</legend><input v-model="strategy.workspace_path" class="input w-full" /><p class="label">SQLite snapshots and generated strategy files stay here.</p></fieldset>
          <fieldset class="fieldset"><legend class="fieldset-legend">Preset pairing</legend><select v-model="strategy.template_id" class="select w-full" @change="applyPreset"><option value="custom">Custom selection</option><option v-for="item in templates" :key="item.id" :value="item.id">{{ item.label }}</option></select></fieldset>
          <fieldset class="fieldset"><legend class="fieldset-legend">Freqtrade config (optional)</legend><div class="join w-full"><input v-model="configPath" class="input join-item w-full" placeholder="config.json" /><button class="btn join-item" @click="chooseConfig">Choose</button></div><p class="label">An empty field creates a safe local dry-run config.</p></fieldset>
          <fieldset class="fieldset"><legend class="fieldset-legend">Entry</legend><select v-model="entryId" class="select w-full" @change="syncPreset"><option v-for="item in entries" :key="item.id" :value="item.id">{{ item.label }}</option></select><p class="label">{{ entries.find((item) => item.id === entryId)?.description }}</p></fieldset>
          <fieldset class="fieldset"><legend class="fieldset-legend">Exit</legend><select v-model="exitId" class="select w-full" @change="syncPreset"><option v-for="item in exits" :key="item.id" :value="item.id">{{ item.label }}</option></select><p class="label">{{ exits.find((item) => item.id === exitId)?.description }}</p></fieldset>
          <fieldset class="fieldset md:col-span-2"><legend class="fieldset-legend">Logic brief — retained for a future AI layer</legend><textarea v-model="strategy.source" class="textarea h-24 w-full" placeholder="This does not alter the deterministic template or its parameters yet." /></fieldset>
        </div>
        <div class="mt-3 grid gap-3 md:grid-cols-2 lg:grid-cols-5"><fieldset class="fieldset"><legend class="fieldset-legend">Exchange</legend><input v-model="exchange" class="input w-full" placeholder="binance" /></fieldset><fieldset class="fieldset"><legend class="fieldset-legend">Market type</legend><select v-model="tradingMode" class="select w-full"><option value="futures">Futures</option><option value="spot">Spot</option><option value="margin">Margin</option></select></fieldset><fieldset class="fieldset"><legend class="fieldset-legend">Pairs</legend><input v-model="pairs" class="input w-full" placeholder="BTC/USDT:USDT" /><p class="label">Comma-separated.</p></fieldset><fieldset class="fieldset"><legend class="fieldset-legend">Timeframes</legend><input v-model="timeframes" class="input w-full" placeholder="5m,1h" /><p class="label">Comma-separated.</p></fieldset><fieldset class="fieldset"><legend class="fieldset-legend">Timerange</legend><input v-model="timerange" class="input w-full" placeholder="20260101-20261231" /></fieldset></div>
        <div class="mt-3 flex flex-wrap items-end gap-3"><button class="btn btn-secondary" :disabled="busy || !strategy.name" @click="createTemplate">Create</button><button class="btn btn-primary" :disabled="busy || !strategy.parameters.length" @click="run()"><span>Run Backtest</span><span v-if="busy" class="loading loading-spinner loading-sm"></span></button></div>
        <div v-if="strategy.parameters.length" class="mt-4"><h3 class="font-medium">Template parameters</h3><div class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3"><div v-for="parameter in strategy.parameters" :key="parameter.name" class="rounded-box border border-base-300 p-3"><div class="font-medium">{{ parameter.name }}</div><div class="text-sm text-base-content/70">{{ parameter.value }} · {{ parameter.notes }}</div></div></div></div>
        <div class="mt-4 flex flex-wrap gap-2"><button class="btn btn-sm" @click="chooseSnapshot">Load</button><button class="btn btn-sm" :disabled="!strategy.strategy_file" @click="exportStrategy">Export</button></div>
      </div></section>
      <section v-else-if="activeTab === 'optimizer'" class="card bg-base-200"><div class="card-body"><h2 class="card-title">Hyperopt optimizer</h2><p class="text-sm text-base-content/70">Hyperopt refreshes the Builder market data first, then evaluates the deterministic template parameter ranges.</p>
        <div class="mt-3 grid gap-3 md:grid-cols-2"><fieldset class="fieldset"><legend class="fieldset-legend">Hyperopt epochs</legend><input v-model.number="epochs" type="number" min="1" max="10000" class="input w-full" /><p class="label">Higher values explore more parameter combinations.</p></fieldset><div class="rounded-box border border-base-300 p-4"><div class="text-sm text-base-content/60">Current run context</div><div class="mt-1 font-medium">{{ strategy.name || 'Create a template in Builder' }}</div><div class="mt-1 text-sm text-base-content/70">{{ exchange }} · {{ tradingMode }} · {{ pairs }} · {{ timeframes }}<span v-if="timerange"> · {{ timerange }}</span></div></div></div>
        <div class="mt-4 grid gap-3 md:grid-cols-2"><fieldset class="fieldset"><legend class="fieldset-legend">Optimization goal</legend><select v-model="optimizationGoal.profile" class="select w-full"><option value="balanced">Balanced</option><option value="higher_frequency">Higher frequency</option><option value="return_focused">Return focused</option><option value="capital_preservation">Capital preservation</option></select><p class="label">Generates the Freqtrade loss objective; it does not invent new logic.</p></fieldset><fieldset class="fieldset"><legend class="fieldset-legend">Target trades / year</legend><input v-model.number="optimizationGoal.target_trades_per_year" type="number" min="1" max="100000" class="input w-full" /><p class="label">A target, not a reason to accept losing churn.</p></fieldset><fieldset class="fieldset"><legend class="fieldset-legend">Minimum trades / validation test</legend><input v-model.number="optimizationGoal.min_trades_per_test" type="number" min="1" max="10000" class="input w-full" /><p class="label">Low-sample tests reduce the stability score.</p></fieldset><fieldset class="fieldset"><legend class="fieldset-legend">Maximum drawdown [%]</legend><input v-model.number="optimizationGoal.max_drawdown_pct" type="number" min="0.1" max="100" step="0.1" class="input w-full" /></fieldset><fieldset class="fieldset"><legend class="fieldset-legend">Minimum profit factor</legend><input v-model.number="optimizationGoal.min_profit_factor" type="number" min="0" max="100" step="0.1" class="input w-full" /></fieldset></div>
        <div class="mt-3"><button class="btn btn-primary" :disabled="busy || !strategy.parameters.length" @click="run(true)"><span>Optimize</span><span v-if="busy" class="loading loading-spinner loading-sm"></span></button></div>
        <div v-if="strategy.parameters.length" class="mt-5"><h3 class="font-medium">Optimizable parameters</h3><div class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3"><div v-for="parameter in strategy.parameters" :key="parameter.name" class="rounded-box border border-base-300 p-3"><div class="font-medium">{{ parameter.name }}</div><div class="text-sm text-base-content/70">{{ parameter.value }} · {{ parameter.notes }}</div></div></div></div>
      </div></section>
      <section v-else class="card bg-base-200"><div class="card-body"><h2 class="card-title">Walk-forward validation</h2><p class="text-sm text-base-content/70">Standard validation uses 70% chronological training and 10 equal out-of-sample test windows. Quick validation uses 2.5 years and 5 test windows. The score is <span class="font-medium">100 ÷ (1 + σ test return)</span>, and becomes zero when mean test return is not positive.</p>
        <div class="mt-3 flex flex-wrap gap-3"><fieldset class="fieldset min-w-0 w-full md:w-72"><legend class="fieldset-legend">Validation range</legend><input v-model="validationTimerange" class="input min-w-0 w-full" placeholder="20210101-20260101" /><p class="label">Standard: five years and 10 test windows.</p></fieldset><fieldset class="fieldset min-w-0 w-full md:w-80"><legend class="fieldset-legend">Quick validation</legend><input :value="quickValidationTimerange" readonly class="input min-w-0 w-full" /><p class="label">2.5 years and 5 test windows. Reuses local candles when coverage is available.</p></fieldset></div><div class="mt-3 flex flex-wrap gap-3"><button class="btn" :disabled="busy || !strategy.parameters.length" @click="runValidation(true)"><span>Quick Validate</span><span v-if="busy" class="loading loading-spinner loading-sm"></span></button><button class="btn btn-primary" :disabled="busy || !strategy.parameters.length" @click="runValidation()"><span>Validate</span><span v-if="busy" class="loading loading-spinner loading-sm"></span></button></div>
        <template v-if="validation"><div class="mt-5 grid gap-3 sm:grid-cols-3"><div class="rounded-box bg-base-100 p-4"><div class="text-sm text-base-content/60">Stability score</div><div class="mt-1 text-2xl font-medium" :class="valueTone('Return [%]', validation.mean_return)">{{ metricValue(validation.stability_score) }}</div><div class="text-xs text-base-content/60">Higher is more stable.</div></div><div class="rounded-box bg-base-100 p-4"><div class="text-sm text-base-content/60">Mean test return [%]</div><div class="mt-1 text-xl font-medium" :class="valueTone('Return [%]', validation.mean_return)">{{ metricValue(validation.mean_return) }}</div></div><div class="rounded-box bg-base-100 p-4"><div class="text-sm text-base-content/60">Test return σ</div><div class="mt-1 text-xl font-medium" :class="valueTone('Drawdown [%]', -validation.return_stddev)">{{ metricValue(validation.return_stddev) }}</div><div class="text-xs text-base-content/60">{{ validation.coverage }}</div></div></div>
          <div class="mt-5 max-h-96 overflow-auto rounded-box border border-base-300"><table class="table table-pin-rows table-sm"><thead><tr><th>Split</th><th>Timerange</th><th>Return [%]</th><th>Win Rate [%]</th><th>Profit Factor</th><th></th></tr></thead><tbody><tr v-for="slice in [validation.training, ...validation.tests]" :key="slice.label"><td>{{ slice.label }}</td><td>{{ slice.timerange }}</td><td :class="valueTone('Return [%]', slice.backtest.metrics['Return [%]'])">{{ metricValue(slice.backtest.metrics['Return [%]']) }}</td><td :class="valueTone('Win Rate [%]', slice.backtest.metrics['Win Rate [%]'])">{{ metricValue(slice.backtest.metrics['Win Rate [%]']) }}</td><td :class="valueTone('Profit Factor', slice.backtest.metrics['Profit Factor'])">{{ metricValue(slice.backtest.metrics['Profit Factor']) }}</td><td><button class="btn btn-ghost btn-xs" @click="selectHistory(slice.backtest)">View</button></td></tr></tbody></table></div></template>
        <div v-if="validation" class="mt-5 rounded-box border border-base-300 p-4"><h3 class="font-medium">Validation confidence</h3><div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><div class="rounded-box bg-base-100 p-3"><div class="text-sm text-base-content/60">Sample-adjusted stability</div><div class="mt-1 text-xl font-medium" :class="valueTone('Return [%]', validation.mean_return)">{{ metricValue(validation.stability_score) }}</div></div><div class="rounded-box bg-base-100 p-3"><div class="text-sm text-base-content/60">Out-of-sample trades</div><div class="mt-1 text-xl font-medium">{{ validation.total_test_trades }}</div><div class="text-xs text-base-content/60">Minimum {{ validation.minimum_test_trades }} per test.</div></div><div class="rounded-box bg-base-100 p-3"><div class="text-sm text-base-content/60">Mean test return [%]</div><div class="mt-1 text-xl font-medium" :class="valueTone('Return [%]', validation.mean_return)">{{ metricValue(validation.mean_return) }}</div></div><div class="rounded-box bg-base-100 p-3"><div class="text-sm text-base-content/60">Test return deviation</div><div class="mt-1 text-xl font-medium">{{ metricValue(validation.return_stddev) }}</div></div></div><p v-if="validation.snapshot_path" class="mt-3 text-sm text-base-content/70">Saved validation snapshot: {{ validation.snapshot_path }}</p><div class="mt-3 max-h-80 overflow-auto rounded-box border border-base-300"><table class="table table-pin-rows table-sm"><thead><tr><th>Split</th><th>Trades</th><th>Return [%]</th><th>Profit Factor</th></tr></thead><tbody><tr v-for="slice in [validation.training, ...validation.tests]" :key="`confidence-${slice.label}`"><td>{{ slice.label }}</td><td>{{ metricValue(slice.backtest.metrics['Total Trades']) }}</td><td :class="valueTone('Return [%]', slice.backtest.metrics['Return [%]'])">{{ metricValue(slice.backtest.metrics['Return [%]']) }}</td><td :class="valueTone('Profit Factor', slice.backtest.metrics['Profit Factor'])">{{ metricValue(slice.backtest.metrics['Profit Factor']) }}</td></tr></tbody></table></div></div>
      </div></section>
      <section class="card bg-base-200"><div class="card-body"><h2 class="card-title">Data visualization</h2><template v-if="selected"><div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><div v-for="(value, name) in selected.metrics" :key="String(name)" class="rounded-box bg-base-100 p-4"><div class="text-sm text-base-content/60">{{ name }}</div><div class="mt-1 text-xl font-medium" :class="valueTone(String(name), value)">{{ metricValue(value) }}</div></div></div><div class="mt-4"><EquityChart :equity="selected.equity_curve" :timestamps="selected.equity_timestamps" /></div>
        <div class="mt-4"><h3 class="mb-2 font-medium">Positions</h3><div class="max-h-96 overflow-auto rounded-box border border-base-300"><table class="table table-pin-rows table-sm"><thead><tr><th v-for="column in tradeColumns" :key="column"><button class="btn btn-ghost btn-xs" @click="toggleSort(column)">{{ column }} <span v-if="sortColumn === column">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span></button></th></tr></thead><tbody><tr v-for="(trade, index) in visibleTrades" :key="index"><td v-for="column in tradeColumns" :key="column"><span :class="valueTone(column, trade[column])">{{ tableValue(column, trade[column]) }}</span></td></tr></tbody></table></div><div class="mt-3 flex items-center justify-end gap-2"><button class="btn btn-sm" :disabled="page === 1" @click="page--">Previous</button><span class="text-sm">{{ page }} / {{ pageCount }}</span><button class="btn btn-sm" :disabled="page === pageCount" @click="page++">Next</button></div></div></template><p v-else class="text-base-content/60">Run or load a Freqtrade strategy to view metrics, charts, and positions.</p></div></section>
      <section class="card bg-base-200"><div class="card-body"><h2 class="card-title">Local history</h2><div class="flex flex-wrap gap-2"><button v-for="item in history" :key="item.id" class="btn btn-sm" :class="selected?.id === item.id ? 'btn-neutral' : ''" @click="selectHistory(item)">{{ item.name }}</button><span v-if="!history.length" class="text-sm text-base-content/60">No Freqtrade runs saved yet.</span></div></div></section>
      <section class="card bg-base-200"><div class="card-body"><h2 class="card-title">Run output</h2><textarea :value="output" readonly class="textarea h-48 w-full" placeholder="Freqtrade CLI output and parser diagnostics appear here." /></div></section>
    </section>
  </main>
  <div v-if="progress" class="fixed inset-x-0 bottom-0 z-50 bg-base-100 px-5 py-3 shadow-2xl">
    <div class="pointer-events-none absolute -top-20 right-0 h-36 w-64 rounded-tl-[4rem] bg-gradient-to-tl from-base-300/55 via-base-300/25 to-transparent blur-xl shadow-[inset_-2rem_-1.5rem_3rem_-1rem_rgba(0,0,0,0.35)]"></div>
    <button class="btn btn-circle btn-error btn-md absolute -top-16 right-5 z-10 shadow-xl" type="button" aria-label="Emergency stop current run" title="Emergency stop" @click="cancelRun"><svg viewBox="0 0 24 24" aria-hidden="true" class="size-5 fill-current"><rect x="6" y="6" width="12" height="12" rx="1" /></svg></button>
    <div class="flex justify-between gap-4 text-sm font-medium"><span class="truncate">{{ progress.label }}</span><span class="shrink-0">{{ progress.percent }}%</span></div>
    <progress class="progress progress-primary mt-1 block w-full" :value="progress.percent" max="100"></progress>
    <div class="mt-2 flex justify-between gap-4 text-xs text-base-content/70"><span class="truncate">{{ progress.sub_label }}</span><span class="shrink-0">{{ progress.sub_percent }}%</span></div>
    <progress class="progress progress-accent mt-1 block w-full" :value="progress.sub_percent" max="100"></progress>
    <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-base-content/60"><span v-for="(step, index) in progress.steps" :key="`${index}-${step}`">{{ step }}</span></div>
  </div>
</template>
