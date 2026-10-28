<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { open, save } from "@tauri-apps/plugin-dialog";
import { pyInvoke } from "tauri-plugin-pytauri-api";
import EquityChart from "./components/EquityChart.vue";

type Parameter = { name: string; value: string; notes: string; enabled: boolean; locked: boolean };
type Strategy = { id?: number; name: string; source: string; workspace_path: string; template_id: string; parameters: Parameter[]; freqtrade_payload?: Record<string, unknown>; strategy_file?: string | null };
type Backtest = { id: number; name: string; imported_at: string; metrics: Record<string, unknown>; trades: Record<string, unknown>[]; equity_curve: number[]; equity_timestamps: string[] };
type StrategyRun = { strategy: Strategy; backtest: Backtest | null; output: string; error?: string | null };
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
const timerange = ref("");
const epochs = ref(100);
const exchange = ref("binance");
const tradingMode = ref("futures");
const pairs = ref("BTC/USDT:USDT");
const timeframes = ref("5m");
const output = ref("");
const error = ref("");
const busy = ref(false);
const activeTab = ref<"builder" | "optimizer">("builder");
const progress = ref<{ label: string; percent: number } | null>(null);
const sortColumn = ref<string | null>(null);
const sortDirection = ref<SortDirection>(null);
const page = ref(1);
const perPage = 25;

async function call<T>(command: string, body?: unknown) {
  error.value = "";
  return pyInvoke<T>(command, body);
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

async function run(hyperopt = false) {
  busy.value = true;
  progress.value = { label: "Downloading or updating market data", percent: 20 };
  try {
    const run = await call<StrategyRun>("run_freqtrade_backtest", { strategy: structuredClone(strategy.value), config_path: configPath.value, exchange: exchange.value, trading_mode: tradingMode.value, pairs: pairs.value, timeframes: timeframes.value, timerange: timerange.value, hyperopt_epochs: hyperopt ? epochs.value : 0 });
    progress.value = { label: "Saving local SQLite snapshot", percent: 85 };
    strategy.value = run.strategy;
    entryId.value = String(run.strategy.freqtrade_payload?.entry_id || entryId.value);
    exitId.value = String(run.strategy.freqtrade_payload?.exit_id || exitId.value);
    output.value = run.output;
    if (run.error) error.value = run.error;
    if (run.backtest) selected.value = run.backtest;
    await refresh();
  } catch (cause) { error.value = String(cause); } finally { busy.value = false; progress.value = null; }
}

async function chooseSnapshot() {
  const path = await open({ defaultPath: strategy.value.workspace_path, filters: [{ name: "Freqtrade snapshot", extensions: ["sqlite", "sqlite3"] }], multiple: false });
  if (typeof path !== "string") return;
  try {
    const run = await call<StrategyRun>("load_strategy_save_file", { path });
    strategy.value = run.strategy;
    entryId.value = String(run.strategy.freqtrade_payload?.entry_id || entryId.value);
    exitId.value = String(run.strategy.freqtrade_payload?.exit_id || exitId.value);
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
onMounted(() => refresh().catch((cause) => error.value = String(cause)));
</script>

<template>
  <main class="min-h-screen bg-base-300 px-4 py-8 sm:px-8">
    <section class="mx-auto max-w-6xl space-y-5">
      <header><p class="text-sm text-base-content/60">Local Freqtrade strategy studio</p><h1 class="text-3xl font-semibold">Backtest Studio</h1><p class="mt-1 text-base-content/70">Create deterministic strategies, run native Freqtrade backtests and hyperopt, then export portable snapshots.</p></header>
      <div v-if="error" role="alert" class="alert alert-error"><span>{{ error }}</span></div>
      <div role="tablist" class="tabs tabs-box w-fit" aria-label="Studio workflow">
        <button role="tab" class="tab gap-2" :class="activeTab === 'builder' ? 'tab-active' : ''" :aria-selected="activeTab === 'builder'" @click="activeTab = 'builder'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-4"><path d="M4 20h16M6 16l4-4 3 3 5-7" /></svg>Builder</button>
        <button role="tab" class="tab gap-2" :class="activeTab === 'optimizer' ? 'tab-active' : ''" :aria-selected="activeTab === 'optimizer'" @click="activeTab = 'optimizer'"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="size-4"><path d="M4 6h16M4 12h10M4 18h6" /><circle cx="17" cy="12" r="2" /><circle cx="13" cy="18" r="2" /></svg>Optimizer</button>
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
      <section v-else class="card bg-base-200"><div class="card-body"><h2 class="card-title">Hyperopt optimizer</h2><p class="text-sm text-base-content/70">Hyperopt refreshes the Builder market data first, then evaluates the deterministic template parameter ranges.</p>
        <div class="mt-3 grid gap-3 md:grid-cols-2"><fieldset class="fieldset"><legend class="fieldset-legend">Hyperopt epochs</legend><input v-model.number="epochs" type="number" min="1" max="10000" class="input w-full" /><p class="label">Higher values explore more parameter combinations.</p></fieldset><div class="rounded-box border border-base-300 p-4"><div class="text-sm text-base-content/60">Current run context</div><div class="mt-1 font-medium">{{ strategy.name || 'Create a template in Builder' }}</div><div class="mt-1 text-sm text-base-content/70">{{ exchange }} · {{ tradingMode }} · {{ pairs }} · {{ timeframes }}<span v-if="timerange"> · {{ timerange }}</span></div></div></div>
        <div class="mt-3"><button class="btn btn-primary" :disabled="busy || !strategy.parameters.length" @click="run(true)"><span>Optimize</span><span v-if="busy" class="loading loading-spinner loading-sm"></span></button></div>
        <div v-if="strategy.parameters.length" class="mt-5"><h3 class="font-medium">Optimizable parameters</h3><div class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3"><div v-for="parameter in strategy.parameters" :key="parameter.name" class="rounded-box border border-base-300 p-3"><div class="font-medium">{{ parameter.name }}</div><div class="text-sm text-base-content/70">{{ parameter.value }} · {{ parameter.notes }}</div></div></div></div>
      </div></section>
      <section class="card bg-base-200"><div class="card-body"><h2 class="card-title">Data visualization</h2><template v-if="selected"><div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><div v-for="(value, name) in selected.metrics" :key="String(name)" class="rounded-box bg-base-100 p-4"><div class="text-sm text-base-content/60">{{ name }}</div><div class="mt-1 text-xl font-medium">{{ metricValue(value) }}</div></div></div><div class="mt-4"><EquityChart :equity="selected.equity_curve" :timestamps="selected.equity_timestamps" /></div>
        <div class="mt-4"><h3 class="mb-2 font-medium">Positions</h3><div class="max-h-96 overflow-auto rounded-box border border-base-300"><table class="table table-pin-rows table-sm"><thead><tr><th v-for="column in tradeColumns" :key="column"><button class="btn btn-ghost btn-xs" @click="toggleSort(column)">{{ column }} <span v-if="sortColumn === column">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span></button></th></tr></thead><tbody><tr v-for="(trade, index) in visibleTrades" :key="index"><td v-for="column in tradeColumns" :key="column">{{ metricValue(trade[column]) }}</td></tr></tbody></table></div><div class="mt-3 flex items-center justify-end gap-2"><button class="btn btn-sm" :disabled="page === 1" @click="page--">Previous</button><span class="text-sm">{{ page }} / {{ pageCount }}</span><button class="btn btn-sm" :disabled="page === pageCount" @click="page++">Next</button></div></div></template><p v-else class="text-base-content/60">Run or load a Freqtrade strategy to view metrics, charts, and positions.</p></div></section>
      <section class="card bg-base-200"><div class="card-body"><h2 class="card-title">Local history</h2><div class="flex flex-wrap gap-2"><button v-for="item in history" :key="item.id" class="btn btn-sm" :class="selected?.id === item.id ? 'btn-neutral' : ''" @click="selectHistory(item)">{{ item.name }}</button><span v-if="!history.length" class="text-sm text-base-content/60">No Freqtrade runs saved yet.</span></div></div></section>
      <section class="card bg-base-200"><div class="card-body"><h2 class="card-title">Run output</h2><textarea :value="output" readonly class="textarea h-48 w-full" placeholder="Freqtrade CLI output and parser diagnostics appear here." /></div></section>
    </section>
  </main>
  <div v-if="progress" class="fixed inset-x-0 bottom-0 z-50 bg-base-100 px-5 py-2 shadow-2xl"><div class="mb-1 flex justify-between text-xs"><span>{{ progress.label }}</span><span>{{ progress.percent }}%</span></div><progress class="progress progress-primary block w-full" :value="progress.percent" max="100"></progress></div>
</template>
