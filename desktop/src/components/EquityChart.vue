<script setup lang="ts">
import { Chart, CategoryScale, Filler, Legend, LineController, LineElement, LinearScale, PointElement, Tooltip } from "chart.js";
import zoomPlugin from "chartjs-plugin-zoom";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

Chart.register(CategoryScale, Filler, Legend, LineController, LineElement, LinearScale, PointElement, Tooltip, zoomPlugin);

const props = defineProps<{ equity: number[]; timestamps: string[] }>();
const canvas = ref<HTMLCanvasElement | null>(null);
let chart: Chart<"line"> | null = null;

function labelAt(index: number) {
  return props.timestamps[index] || `Point ${index + 1}`;
}

function drawChart() {
  if (!canvas.value) return;
  chart?.destroy();
  chart = new Chart(canvas.value, {
    type: "line",
    data: {
      labels: props.equity.map((_, index) => labelAt(index)),
      datasets: [{
        label: "Equity",
        data: props.equity,
        borderColor: "#60a5fa",
        backgroundColor: "rgba(96, 165, 250, 0.14)",
        fill: true,
        pointRadius: 0,
        pointHoverRadius: 4,
        borderWidth: 2,
        tension: 0.2,
      }],
    },
    options: {
      animation: false,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: {
            title: (items) => labelAt(items[0]?.dataIndex ?? 0),
            label: (item) => `Equity: ${Number(item.parsed.y).toLocaleString(undefined, { maximumFractionDigits: 2 })}`,
          },
        },
        zoom: {
          pan: { enabled: true, mode: "x" },
          zoom: { wheel: { enabled: true }, pinch: { enabled: true }, drag: { enabled: true }, mode: "x" },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 6, maxRotation: 0 }, grid: { display: false } },
        y: { ticks: { callback: (value) => Number(value).toLocaleString(undefined, { notation: "compact" }) } },
      },
    },
  });
}

function zoom(factor: number) {
  chart?.zoom(factor);
}

function resetZoom() {
  chart?.resetZoom();
}

watch(() => [props.equity, props.timestamps], async () => {
  await nextTick();
  drawChart();
}, { deep: true });
onMounted(drawChart);
onBeforeUnmount(() => chart?.destroy());
</script>

<template>
  <div class="card card-border bg-base-100">
    <div class="card-body gap-3 p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div><h3 class="font-medium">Equity curve</h3><p class="text-sm text-base-content/60">Scroll to zoom, drag to pan, and hover for values.</p></div>
        <div class="join"><button class="btn btn-sm join-item" aria-label="Zoom in" @click="zoom(1.2)">+</button><button class="btn btn-sm join-item" aria-label="Zoom out" @click="zoom(0.8)">−</button><button class="btn btn-sm join-item" @click="resetZoom">Reset</button></div>
      </div>
      <div class="h-80"><canvas ref="canvas"></canvas></div>
    </div>
  </div>
</template>
