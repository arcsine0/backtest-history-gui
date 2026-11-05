<script setup lang="ts">
defineProps<{
  label: string;
  modelValue: string;
  placeholder?: string;
  help?: string;
  browseLabel: string;
}>();

defineEmits<{
  "update:modelValue": [value: string];
  browse: [];
}>();
</script>

<template>
  <fieldset class="fieldset">
    <legend class="fieldset-legend">{{ label }}</legend>
    <div class="group relative">
      <input
        class="input w-full pr-10"
        :value="modelValue"
        :placeholder="placeholder"
        @input="
          $emit('update:modelValue', ($event.target as HTMLInputElement).value)
        "
      />
      <button
        class="btn btn-ghost btn-sm btn-square absolute top-1/2 right-1 -translate-y-1/2 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
        type="button"
        :aria-label="browseLabel"
        :title="browseLabel"
        @click="$emit('browse')"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
          class="size-4"
        >
          <path
            d="M4 19.5V6.75A1.75 1.75 0 0 1 5.75 5h4l1.5 2h7A1.75 1.75 0 0 1 20 8.75V19.5"
          />
          <path d="M12 10v7m0-7-3 3m3-3 3 3" />
        </svg>
      </button>
    </div>
    <p v-if="help" class="label">{{ help }}</p>
  </fieldset>
</template>
