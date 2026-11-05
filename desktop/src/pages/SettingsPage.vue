<script setup lang="ts">
import { computed, ref, watch } from "vue";

type ApiKeyStatus = {
  configured: boolean;
  source: string;
  cache_configured: boolean;
  environment_configured: boolean;
};

type Dataset = { path: string; bytes: number };
type ClearKind = "backtests" | "hyperopts" | "validations";

const props = defineProps<{
  apiKeyStatus: ApiKeyStatus;
  savingApiKey: boolean;
  clearingKind: string;
  datasets: Dataset[];
}>();

const emit = defineEmits<{
  saveApiKey: [apiKey: string];
  clearApiKey: [];
  requestClear: [kind: ClearKind];
  refreshDatasets: [];
}>();

const apiKey = ref("");
const apiKeyInputDisabled = computed(
  () => props.savingApiKey || props.apiKeyStatus.cache_configured,
);
const apiKeyInputValue = computed(() =>
  props.apiKeyStatus.cache_configured ? "••••••••••••" : apiKey.value,
);

watch(
  () => props.apiKeyStatus.cache_configured,
  (cached) => {
    if (!cached) apiKey.value = "";
  },
);

function saveApiKey() {
  const value = apiKey.value.trim();
  if (!value) return;
  emit("saveApiKey", value);
  apiKey.value = "";
}
</script>

<template>
  <section class="card bg-base-200">
    <div class="card-body">
      <h2 class="card-title">Settings</h2>
      <div class="mt-3 rounded-box border border-base-300 bg-base-100 p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 class="font-medium">OpenAI API key</h3>
            <p class="mt-1 text-sm text-base-content/70">
              Used only for AI strategy generation. The key is kept in
              Stratara’s local app cache and is never included in strategy
              snapshots.
            </p>
          </div>
          <span v-if="apiKeyStatus.configured" class="badge badge-success"
            >Configured{{
              apiKeyStatus.source ? ` · ${apiKeyStatus.source}` : ""
            }}</span
          >
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
              :placeholder="
                apiKeyStatus.cache_configured
                  ? ''
                  : 'Paste a new key to save or replace it'
              "
              @input="apiKey = ($event.target as HTMLInputElement).value"
              @keyup.enter="saveApiKey"
            />
          </fieldset>
          <button
            class="btn btn-primary"
            type="button"
            :disabled="apiKeyInputDisabled || !apiKey.trim()"
            @click="saveApiKey"
          >
            Save
          </button>
          <button
            class="btn"
            type="button"
            :disabled="savingApiKey || !apiKeyStatus.cache_configured"
            @click="$emit('clearApiKey')"
          >
            Clear saved key
          </button>
        </div>
        <p
          v-if="apiKeyStatus.environment_configured"
          class="mt-2 text-xs text-base-content/60"
        >
          OPENAI_API_KEY from the environment or .env takes precedence over the
          saved key.
        </p>
      </div>
      <div class="mt-3 rounded-box border border-error/50 bg-error/5 p-4">
        <h3 class="font-medium text-error">Danger zone</h3>
        <p class="mt-1 text-sm text-base-content/70">
          Clear run records and matching Freqtrade artifacts for the active
          workspace.
        </p>
        <div role="alert" class="alert alert-error alert-soft mt-3 text-sm">
          <span
            >Clearing moves matching local snapshots and Freqtrade artifacts to
            the Recycle Bin. Downloaded datasets and strategy templates are
            kept.</span
          >
        </div>
        <div class="mt-3 grid gap-3 md:grid-cols-3">
          <div class="rounded-box border border-error/35 bg-base-100 p-4">
            <h4 class="font-medium">Backtests</h4>
            <p class="mt-1 text-sm text-base-content/70">
              Clears saved backtest history and Freqtrade backtest exports.
            </p>
            <button
              class="btn btn-error btn-sm mt-3"
              :disabled="clearingKind !== ''"
              @click="$emit('requestClear', 'backtests')"
            >
              Clear backtests
            </button>
          </div>
          <div class="rounded-box border border-error/35 bg-base-100 p-4">
            <h4 class="font-medium">Hyperopts</h4>
            <p class="mt-1 text-sm text-base-content/70">
              Clears saved Hyperopt history and Freqtrade search artifacts.
            </p>
            <button
              class="btn btn-error btn-sm mt-3"
              :disabled="clearingKind !== ''"
              @click="$emit('requestClear', 'hyperopts')"
            >
              Clear hyperopts
            </button>
          </div>
          <div class="rounded-box border border-error/35 bg-base-100 p-4">
            <h4 class="font-medium">Validations</h4>
            <p class="mt-1 text-sm text-base-content/70">
              Clears validation snapshots and split-result artifacts.
            </p>
            <button
              class="btn btn-error btn-sm mt-3"
              :disabled="clearingKind !== ''"
              @click="$emit('requestClear', 'validations')"
            >
              Clear validations
            </button>
          </div>
        </div>
      </div>
      <div class="mt-6">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 class="font-medium">Downloaded datasets</h3>
            <p class="text-sm text-base-content/70">
              Cached Freqtrade candles are listed only; clearing them is not
              available yet.
            </p>
          </div>
          <button class="btn btn-sm" @click="$emit('refreshDatasets')">
            Refresh
          </button>
        </div>
        <ul
          v-if="datasets.length"
          class="list mt-2 rounded-box border border-base-300"
        >
          <li v-for="dataset in datasets" :key="dataset.path" class="list-row">
            <span class="list-col-grow break-all">{{ dataset.path }}</span
            ><span class="text-sm text-base-content/60"
              >{{ (dataset.bytes / 1024 / 1024).toFixed(2) }} MB</span
            >
          </li>
        </ul>
        <p v-else class="mt-3 text-sm text-base-content/60">
          No downloaded Freqtrade datasets in this workspace.
        </p>
      </div>
    </div>
  </section>
</template>
