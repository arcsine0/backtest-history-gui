<script setup lang="ts">
defineProps<{ output: string }>();

defineEmits<{
  copy: [];
  export: [];
}>();
</script>

<template>
  <section class="card min-h-[calc(100vh-12rem)] bg-base-200">
    <div class="card-body min-h-0">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 class="card-title">Logs</h2>
          <p class="mt-1 text-sm text-base-content/70">Freqtrade CLI output and parser diagnostics.</p>
        </div>
        <div class="flex shrink-0 gap-2">
          <button class="btn btn-ghost btn-square btn-sm" type="button" :disabled="!output" aria-label="Copy logs" title="Copy logs" @click="$emit('copy')">
            Copy
          </button>
          <button class="btn btn-ghost btn-square btn-sm" type="button" :disabled="!output" aria-label="Export logs" title="Export logs" @click="$emit('export')">
            Export
          </button>
        </div>
      </div>
      <textarea
        :value="output"
        readonly
        class="textarea mt-4 h-[calc(100vh-17rem)] min-h-96 w-full resize-none font-mono text-xs"
        placeholder="Run a backtest, optimizer, or validation to view its output here."
      ></textarea>
    </div>
  </section>
</template>
