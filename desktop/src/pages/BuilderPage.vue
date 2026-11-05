<script setup lang="ts">
import { Bot, ChartNoAxesCombined, Download, FolderOpen } from "@lucide/vue";
import PathInput from "../components/PathInput.vue";
import StrategyGraph from "../components/StrategyGraph.vue";
import { useStudioPageContext } from "./studio-page-context";

const studio = useStudioPageContext();
</script>

<template>
  <section class="card bg-base-200">
    <div class="card-body">
      <h2 class="card-title">Strategy builder</h2>
      <div class="mt-4 flex items-center justify-between gap-3">
        <div
          role="tablist"
          class="tabs tabs-box w-fit"
          aria-label="Strategy creation mode"
        >
          <button
            role="tab"
            class="tab gap-3 py-3 text-base"
            :class="studio.creationMode === 'manual' ? 'tab-active' : ''"
            :aria-selected="studio.creationMode === 'manual'"
            @click="studio.creationMode = 'manual'"
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
            :class="studio.creationMode === 'ai' ? 'tab-active' : ''"
            :aria-selected="studio.creationMode === 'ai'"
            @click="studio.creationMode = 'ai'"
          >
            <Bot class="size-5" :stroke-width="2" aria-hidden="true" />
            AI
          </button>
        </div>
        <div class="flex shrink-0 gap-2">
          <button
            class="btn btn-square btn-md"
            type="button"
            aria-label="Load strategy snapshot"
            title="Load strategy snapshot"
            @click="studio.chooseSnapshot"
          >
            <FolderOpen class="size-5" :stroke-width="2" aria-hidden="true" />
          </button>
          <button
            class="btn btn-square btn-md"
            type="button"
            :disabled="!studio.strategy.strategy_file"
            aria-label="Export strategy"
            title="Export strategy"
            @click="studio.exportStrategy"
          >
            <Download class="size-5" :stroke-width="2" aria-hidden="true" />
          </button>
        </div>
      </div>
      <div class="mt-4 grid gap-3 lg:grid-cols-3">
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Name</legend>
          <input
            v-model="studio.strategy.name"
            class="input w-full"
            :placeholder="studio.generatedNamePreview"
          />
        </fieldset>
        <PathInput
          v-model="studio.strategy.workspace_path"
          label="Workspace"
          help="SQLite snapshots and generated strategy files stay here."
          browse-label="Choose workspace folder"
          @browse="studio.chooseWorkspace"
        />
        <PathInput
          v-model="studio.configPath"
          label="Freqtrade config (optional)"
          placeholder="config.json"
          help="An empty field creates a safe local dry-run config."
          browse-label="Choose Freqtrade config"
          @browse="studio.chooseConfig"
        />
        <fieldset
          v-if="studio.creationMode === 'manual'"
          class="fieldset lg:col-start-1 lg:row-start-2"
        >
          <legend class="fieldset-legend">Preset pairing</legend>
          <select
            v-model="studio.strategy.template_id"
            class="select w-full"
            @change="studio.applyPreset"
          >
            <option value="custom">Custom selection</option>
            <option
              v-for="item in studio.templates"
              :key="item.id"
              :value="item.id"
            >
              {{ item.label }}
            </option>
          </select>
        </fieldset>
        <fieldset
          v-if="studio.creationMode === 'manual'"
          class="fieldset lg:col-start-2 lg:row-start-2"
        >
          <legend class="fieldset-legend">Entry</legend>
          <select
            v-model="studio.entryId"
            class="select w-full"
            @change="studio.syncPreset"
          >
            <option
              v-for="item in studio.entries"
              :key="item.id"
              :value="item.id"
            >
              {{ item.label }}
            </option>
          </select>
          <p class="label">
            {{
              studio.entries.find((item: any) => item.id === studio.entryId)
                ?.description
            }}
          </p>
        </fieldset>
        <fieldset
          v-if="studio.creationMode === 'manual'"
          class="fieldset lg:col-start-3 lg:row-start-2"
        >
          <legend class="fieldset-legend">Exit</legend>
          <select
            v-model="studio.exitId"
            class="select w-full"
            @change="studio.syncPreset"
          >
            <option
              v-for="item in studio.exits"
              :key="item.id"
              :value="item.id"
            >
              {{ item.label }}
            </option>
          </select>
          <p class="label">
            {{
              studio.exits.find((item: any) => item.id === studio.exitId)
                ?.description
            }}
          </p>
        </fieldset>
        <fieldset v-else class="fieldset lg:col-span-3 lg:row-start-2">
          <legend class="fieldset-legend">Strategy brief</legend>
          <textarea
            v-model="studio.strategy.source"
            class="textarea h-28 w-full"
            placeholder="Describe the strategy logic the AI should compose from the node catalog."
          />
          <p class="label">
            The AI receives the selected market data plus the complete validated
            node catalog.
          </p>
        </fieldset>
      </div>
      <div class="mt-3 grid gap-3 md:grid-cols-2 lg:grid-cols-5">
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Exchange</legend>
          <input
            v-model="studio.exchange"
            class="input w-full"
            placeholder="binance"
          />
        </fieldset>
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Market type</legend>
          <select v-model="studio.tradingMode" class="select w-full">
            <option value="futures">Futures</option>
            <option value="spot">Spot</option>
            <option value="margin">Margin</option>
          </select>
        </fieldset>
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Pairs</legend>
          <input
            v-model="studio.pairs"
            class="input w-full"
            placeholder="BTC/USDT:USDT"
          />
          <p class="label">Comma-separated.</p>
        </fieldset>
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Timeframes</legend>
          <input
            v-model="studio.timeframes"
            class="input w-full"
            placeholder="5m,1h"
          />
          <p class="label">Comma-separated.</p>
        </fieldset>
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Timerange</legend>
          <input
            v-model="studio.timerange"
            class="input w-full"
            placeholder="20260101-20261231"
          />
        </fieldset>
      </div>
      <div class="mt-3 flex flex-wrap items-end gap-3">
        <button
          class="btn btn-secondary"
          :disabled="
            studio.busy ||
            (studio.creationMode === 'ai' && !studio.strategy.source.trim())
          "
          @click="
            studio.creationMode === 'manual'
              ? studio.createTemplate()
              : studio.createAiStrategy()
          "
        >
          <span>{{
            studio.creationMode === "manual" ? "Create" : "Generate"
          }}</span
          ><span
            v-if="studio.busy"
            class="loading loading-spinner loading-sm"
          ></span></button
        ><button
          class="btn btn-primary"
          :disabled="studio.busy || !studio.strategy.parameters.length"
          @click="studio.run()"
        >
          <span>Run Backtest</span
          ><span
            v-if="studio.busy"
            class="loading loading-spinner loading-sm"
          ></span>
        </button>
      </div>
      <div v-if="studio.strategy.parameters.length" class="mt-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="font-medium">Template parameters</h3>
          <label class="sr-only" for="template-parameter-view"
            >Template parameter view</label
          ><select
            id="template-parameter-view"
            v-model="studio.parameterView"
            class="select select-sm"
          >
            <option value="parameters">Parameters</option>
            <option value="nodes">Nodes</option>
            <option value="json">JSON</option>
          </select>
        </div>
        <div
          v-if="studio.parameterView === 'parameters'"
          class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3"
        >
          <div
            v-for="parameter in studio.strategy.parameters"
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
          v-else-if="studio.parameterView === 'nodes' && studio.strategyGraph"
          class="mt-2"
          :graph="studio.strategyGraph"
          :catalog="studio.nodeCatalog.nodes"
        />
        <div v-else class="group relative mt-2">
          <pre
            class="max-h-[32rem] overflow-auto rounded-box border border-base-300 bg-base-100 p-4 pr-12 text-xs text-base-content/80"
            >{{ studio.strategyGraphJson }}</pre
          >
          <button
            class="btn btn-ghost btn-square btn-sm absolute top-2 right-2 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
            type="button"
            aria-label="Copy node graph JSON"
            title="Copy node graph JSON"
            @click="studio.copyGraphJson"
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
</template>
