<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { open } from "@tauri-apps/plugin-dialog";
import { pyInvoke } from "tauri-plugin-pytauri-api";
import EquityChart from "./components/EquityChart.vue";

type Parameter = { name: string; value: string; notes: string; enabled: boolean; locked: boolean };
type Strategy = { id?: number; name: string; source: string; workspace_path: string; parameters: Parameter[]; strategy_file?: string | null };
type Trade = Record<string, unknown>;
type Backtest = { id: number; name: string; imported_at: string; metrics: Record<string, unknown>; trades: Trade[]; equity_curve: number[]; equity_timestamps: string[] };
type StrategyRun = { strategy: Strategy; backtest: Backtest | null; output: string; error?: string | null };
type SortDirection = "asc" | "desc" | null;
type Metric = [string, unknown];

const strategy = ref<Strategy>({ name: "", source: "", workspace_path: "", parameters: [] });
const strategies = ref<Strategy[]>([]);
const history = ref<Backtest[]>([]);
const selected = ref<Backtest | null>(null);
const output = ref("");
const error = ref("");
const busy = ref(false);
const runningPrompt = ref<"raw" | "optimized" | "auto" | null>(null);
const saveFilePath = ref("");
const resultsPanel = ref<HTMLElement | null>(null);
const sortColumn = ref<string | null>(null);
const sortDirection = ref<SortDirection>(null);
const tradePage = ref(1);
const tradesPerPage = 25;

async function call<T>(command: string, body?: unknown) {
  error.value = "";
  return pyInvoke<T>(command, body);
}

function showResults() {
  resultsPanel.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function refresh() {
  try {
    const [projectRoot, savedStrategies, savedHistory] = await Promise.all([
      call<string>("default_workspace"), call<Strategy[]>("list_strategy_setups"), call<Backtest[]>("list_imported_backtests"),
    ]);
    if (!strategy.value.workspace_path) strategy.value.workspace_path = projectRoot;
    strategies.value = savedStrategies;
    history.value = savedHistory;
  } catch (cause) { error.value = String(cause); }
}

async function applyRun(run: StrategyRun) {
  strategy.value = run.strategy;
  selected.value = run.backtest;
  output.value = run.output;
  saveFilePath.value = run.strategy.strategy_file ?? "";
  if (run.error) { error.value = run.error; return; }
  await refresh();
}

async function runRaw() {
  busy.value = true;
  runningPrompt.value = "raw";
  try { await applyRun(await call<StrategyRun>("run_strategy_backtest", strategy.value)); showResults(); }
  catch (cause) { error.value = String(cause); } finally { busy.value = false; runningPrompt.value = null; }
}

async function optimize() {
  busy.value = true;
  runningPrompt.value = "optimized";
  try { await applyRun(await call<StrategyRun>("optimize_strategy_backtest", strategy.value)); showResults(); }
  catch (cause) { error.value = String(cause); } finally { busy.value = false; runningPrompt.value = null; }
}

async function autoOptimize() {
  if (!selected.value) return;
  busy.value = true;
  runningPrompt.value = "auto";
  try { await applyRun(await call<StrategyRun>("auto_optimize_strategy_backtest", { strategy: strategy.value, metrics: selected.value.metrics })); showResults(); }
  catch (cause) { error.value = String(cause); } finally { busy.value = false; runningPrompt.value = null; }
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
  try { await applyRun(await call<StrategyRun>("load_strategy_save_file", { path: saveFilePath.value })); }
  catch (cause) { error.value = String(cause); } finally { busy.value = false; }
}

async function importResult(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  busy.value = true;
  try { selected.value = await call<Backtest>("import_backtest_result", { name: file.name, payload: JSON.parse(await file.text()) }); await refresh(); }
  catch (cause) { error.value = String(cause); } finally { busy.value = false; }
}

async function selectBacktest(id: number) {
  busy.value = true;
  try { selected.value = await call<Backtest>("load_imported_backtest", id); }
  catch (cause) { error.value = String(cause); } finally { busy.value = false; }
}

function loadStrategy(value: Strategy) {
  strategy.value = structuredClone(value);
  saveFilePath.value = value.strategy_file ?? "";
}

function parameterState(parameter: Parameter) {
  if (parameter.locked) return "border-warning bg-warning/10";
  return parameter.enabled ? "border-primary bg-primary/10" : "border-base-300 bg-base-100 opacity-70";
}

function toggleParameterLock(parameter: Parameter) {
  parameter.locked = !parameter.locked;
  if (parameter.locked) parameter.enabled = false;
}

function isNumber(value: unknown) {
  return (typeof value === "number" && Number.isFinite(value)) || (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value)));
}

function formatMetric(value: unknown) {
  return isNumber(value) ? Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value ?? "—");
}

function metricTone(name: string, value: unknown) {
  if (!isNumber(value) || /trade count|holding|turnover|adjustment/i.test(name)) return "text-base-content";
  const numeric = Number(value);
  if (/drawdown/i.test(name)) return numeric < 0 ? "text-error" : numeric === 0 ? "text-warning" : "text-success";
  if (/win rate/i.test(name)) return numeric >= 50 ? "text-success" : numeric > 0 ? "text-warning" : "text-error";
  if (/profit factor/i.test(name)) return numeric > 1 ? "text-success" : numeric === 1 ? "text-warning" : "text-error";
  return numeric > 0 ? "text-success" : numeric < 0 ? "text-error" : "text-warning";
}

function tradeValueTone(column: string, value: unknown) {
  if (/^side$/i.test(column)) {
    if (/^(buy|long)$/i.test(String(value))) return "text-success";
    if (/^(sell|short)$/i.test(String(value))) return "text-error";
    return "text-warning";
  }
  return /pnl|profit|return|drawdown|fee|commission/i.test(column) ? metricTone(column, value) : "";
}

function displayMetricName(name: string) {
  return name.replace(/^Vibe:\s*/, "");
}

function canonicalMetricName(name: string) {
  const title = displayMetricName(name).toLowerCase();
  return {
    "total return": "return [%]",
    "p/l [%]": "return [%]",
    "win rate": "win rate [%]",
    "avg drawdown": "avg. drawdown [%]",
    "max drawdown": "max. drawdown [%]",
    "trade count": "total trades",
    "sharpe": "sharpe ratio",
    "sortino": "sortino ratio",
  }[title] ?? title;
}

function metricGroup(name: string) {
  const title = displayMetricName(name).toLowerCase();
  if (["p/l", "p/l [%]", "return [%]", "win rate [%]", "avg. drawdown [%]", "max. drawdown [%]", "total trades", "profit factor", "sharpe ratio", "sortino ratio"].includes(title)) return "Core metrics";
  if (/drawdown|risk|volatility/.test(title)) return "Risk";
  if (/trade|win rate|exposure|turnover|holding/.test(title)) return "Trading activity";
  if (/return|profit|p\/l|sharpe|sortino|sqn/.test(title)) return "Performance";
  return "Additional metrics";
}

function toggleSort(column: string) {
  if (sortColumn.value !== column) { sortColumn.value = column; sortDirection.value = "asc"; }
  else if (sortDirection.value === "asc") sortDirection.value = "desc";
  else if (sortDirection.value === "desc") { sortColumn.value = null; sortDirection.value = null; }
  else sortDirection.value = "asc";
  tradePage.value = 1;
}

const metricGroups = computed(() => {
  const order = ["Core metrics", "Performance", "Risk", "Trading activity", "Additional metrics"];
  const groups = new Map(order.map((title) => [title, [] as Metric[]]));
  const entries = Object.entries(selected.value?.metrics ?? {});
  for (const metric of entries) {
    const canonical = canonicalMetricName(metric[0]);
    const hasCanonicalMetric = entries.some(([name]) => name !== metric[0] && canonicalMetricName(name) === canonical && canonicalMetricName(name) === displayMetricName(name).toLowerCase());
    if (!hasCanonicalMetric) groups.get(metricGroup(metric[0]))?.push(metric);
  }
  return order.map((title) => ({ title, metrics: groups.get(title) ?? [] })).filter((group) => group.metrics.length);
});
const tradeColumns = computed(() => [...new Set(selected.value?.trades.flatMap((trade) => Object.keys(trade)) ?? [])]);
const sortedTrades = computed(() => {
  const trades = [...(selected.value?.trades ?? [])];
  if (!sortColumn.value || !sortDirection.value) return trades;
  const column = sortColumn.value;
  const direction = sortDirection.value === "asc" ? 1 : -1;
  return trades.sort((left, right) => {
    const a = left[column]; const b = right[column];
    if (isNumber(a) && isNumber(b)) return (Number(a) - Number(b)) * direction;
    return String(a ?? "").localeCompare(String(b ?? ""), undefined, { numeric: true }) * direction;
  });
});
const totalTradePages = computed(() => Math.max(1, Math.ceil(sortedTrades.value.length / tradesPerPage)));
const pagedTrades = computed(() => sortedTrades.value.slice((tradePage.value - 1) * tradesPerPage, tradePage.value * tradesPerPage));

watch(selected, () => { tradePage.value = 1; sortColumn.value = null; sortDirection.value = null; });
onMounted(refresh);
</script>

<template>
  <main class="h-screen snap-y snap-mandatory overflow-y-auto">
    <section class="mx-auto flex min-h-screen max-w-5xl snap-start flex-col justify-center gap-5 px-4 py-8 sm:px-8">
      <header><p class="text-sm text-base-content/60">Local companion for Vibe-Trading</p><h1 class="text-3xl font-semibold">Backtest Studio</h1><p class="mt-1 text-base-content/70">Describe a strategy here, then run its complete backtest below.</p></header>
      <div class="card bg-base-200"><div class="card-body"><h2 class="card-title font-semibold">Strategy controls</h2><div class="grid gap-3 md:grid-cols-2"><fieldset class="fieldset"><legend class="fieldset-legend">Name</legend><input v-model="strategy.name" class="input w-full" placeholder="VWAP ATR trail" /></fieldset><fieldset class="fieldset"><legend class="fieldset-legend">Workspace</legend><input v-model="strategy.workspace_path" class="input w-full" placeholder="Project data directory" /><p class="label">Each completed run exports a named SQLite save file here.</p></fieldset><fieldset class="fieldset md:col-span-2"><legend class="fieldset-legend">Prompt</legend><textarea v-model="strategy.source" class="textarea h-48 w-full" placeholder="Describe the indicators, entries, exits, risk controls, market, and timeframe." /></fieldset></div><div class="card-actions mt-4 justify-start"><button class="btn btn-primary" :disabled="busy || !strategy.name || !strategy.source" @click="runRaw"><span>Run strategy</span><span v-if="runningPrompt === 'raw'" role="status" aria-label="Running strategy" class="loading loading-spinner loading-sm"></span></button><button class="btn" :disabled="busy || !strategy.parameters.length" @click="optimize"><span>Optimize selected parameters</span><span v-if="runningPrompt === 'optimized'" role="status" aria-label="Optimizing strategy" class="loading loading-spinner loading-sm"></span></button><button class="btn" :disabled="busy || !selected" @click="autoOptimize"><span>Auto optimize from results</span><span v-if="runningPrompt === 'auto'" role="status" aria-label="Auto optimizing strategy" class="loading loading-spinner loading-sm"></span></button></div><div v-if="strategy.parameters.length" class="mt-4"><h3 class="font-medium">Strategy parameters</h3><p class="mt-1 text-sm text-base-content/70">Checked parameters can be optimized. Locked parameters stay fixed.</p><ul class="list mt-2 rounded-box border border-base-300"><li v-for="parameter in strategy.parameters" :key="parameter.name" class="list-row border-b border-base-300 last:border-b-0" :class="parameterState(parameter)"><input v-model="parameter.enabled" type="checkbox" class="checkbox checkbox-primary" :disabled="parameter.locked" :aria-label="`Optimize ${parameter.name}`" /><div class="list-col-grow"><div class="font-medium">{{ parameter.name }}</div><div class="text-sm text-base-content/70">{{ parameter.value }}<span v-if="parameter.notes"> · {{ parameter.notes }}</span><span v-if="parameter.locked"> · Do not edit</span></div></div><button type="button" class="btn btn-sm" :class="parameter.locked ? 'btn-warning' : 'btn-ghost'" :aria-pressed="parameter.locked" @click="toggleParameterLock(parameter)">{{ parameter.locked ? 'Unlock' : 'Lock' }}</button></li></ul></div><fieldset class="fieldset mt-4"><legend class="fieldset-legend">Load strategy save file</legend><div class="join w-full"><input v-model="saveFilePath" class="input join-item w-full" placeholder="C:\path\to\strategy-raw-1-10262026.sqlite3" /><button class="btn join-item" :disabled="busy" @click="chooseStrategyFile">Browse</button><button class="btn join-item" :disabled="busy || !saveFilePath" @click="loadStrategyFile">Load</button></div></fieldset><div v-if="strategies.length" class="mt-3 border-t border-base-300 pt-3"><p class="mb-2 text-sm font-medium">Saved strategies</p><div class="flex flex-wrap gap-2"><button v-for="item in strategies" :key="item.id" class="btn btn-sm" :disabled="busy" @click="loadStrategy(item)">{{ item.name }}</button></div></div></div></div>
    </section>

    <section ref="resultsPanel" class="mx-auto min-h-screen max-w-5xl snap-start px-4 py-8 sm:px-8">
      <div v-if="error" role="alert" class="alert alert-error mb-5"><span>{{ error }}</span></div>
      <div class="card bg-base-200 mb-5"><div class="card-body"><h2 class="card-title font-semibold">Prompt result</h2><textarea class="textarea h-52 w-full font-mono text-xs" readonly :value="output" placeholder="The raw Vibe-Trading response will appear here." /></div></div>
      <section class="card bg-base-200"><div class="card-body"><h2 class="card-title font-semibold">Data visualization</h2><div v-if="!selected" class="flex min-h-64 items-center justify-center border border-base-300 text-center text-base-content/60">Run a strategy to view its metrics, equity curve, and trades.</div><template v-else><section v-for="group in metricGroups" :key="group.title" class="mt-4 first:mt-0"><h3 class="mb-3 text-sm font-medium text-base-content/70">{{ group.title }}</h3><div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"><article v-for="([key, value]) in group.metrics" :key="key" class="card card-border bg-base-100"><div class="card-body gap-1 p-4"><p class="text-sm font-normal text-base-content/60">{{ displayMetricName(key) }}</p><p class="text-xl font-semibold" :class="metricTone(key, value)">{{ formatMetric(value) }}</p></div></article></div></section><div class="mt-5"><EquityChart :equity="selected.equity_curve" :timestamps="selected.equity_timestamps" /></div><div class="mt-5"><div class="mb-3 flex flex-wrap items-center justify-between gap-2"><div><h3 class="font-medium">Positions</h3><p class="text-sm text-base-content/60">{{ sortedTrades.length }} records</p></div><div class="join"><button class="btn btn-sm join-item" :disabled="tradePage === 1" @click="tradePage--">Previous</button><span class="btn btn-sm join-item pointer-events-none">{{ tradePage }} / {{ totalTradePages }}</span><button class="btn btn-sm join-item" :disabled="tradePage === totalTradePages" @click="tradePage++">Next</button></div></div><div class="max-h-[30rem] overflow-auto rounded-box border border-base-300"><table class="table table-pin-rows table-zebra"><thead><tr><th v-for="column in tradeColumns" :key="column"><button class="btn btn-ghost btn-xs whitespace-nowrap font-medium normal-case" @click="toggleSort(column)">{{ column }}<span v-if="sortColumn === column" aria-hidden="true">{{ sortDirection === 'asc' ? '▲' : '▼' }}</span></button></th></tr></thead><tbody><tr v-for="(trade, index) in pagedTrades" :key="index"><td v-for="column in tradeColumns" :key="column"><span :class="tradeValueTone(column, trade[column])">{{ trade[column] }}</span></td></tr></tbody></table></div></div></template></div></section>
      <section class="card bg-base-200 mt-5"><div class="card-body"><h2 class="card-title font-semibold">Import and history</h2><div class="grid gap-5 lg:grid-cols-2"><div><p class="mb-2 text-sm text-base-content/70">Import an existing JSON backtest.</p><input type="file" accept="application/json,.json" class="file-input w-full" :disabled="busy" @change="importResult" /></div><div><h3 class="mb-2 font-medium">Run history</h3><div v-if="history.length" class="divide-y divide-base-300"><button v-for="item in history" :key="item.id" class="block w-full py-3 text-left hover:underline" @click="selectBacktest(item.id)"><span class="block font-medium">{{ item.name }}</span><span class="text-xs text-base-content/60">{{ item.imported_at }}</span></button></div><p v-else class="text-sm text-base-content/60">No saved runs yet.</p></div></div></div></section>
    </section>
  </main>
</template>
