<script setup lang="ts">
import { Chart, CategoryScale, Filler, LineController, LineElement, LinearScale, PointElement, Tooltip } from "chart.js";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

Chart.register(CategoryScale, Filler, LineController, LineElement, LinearScale, PointElement, Tooltip);
const props = defineProps<{ trials: { number: number; score: number | null; status: string }[] }>();
const canvas = ref<HTMLCanvasElement | null>(null);
let chart: Chart<"line"> | null = null;

function drawChart() {
  if (!canvas.value) return;
  chart?.destroy();
  chart = new Chart(canvas.value, {
    type: "line",
    data: { labels: props.trials.map((trial) => `Trial ${trial.number}`), datasets: [{ label: "Goal score", data: props.trials.map((trial) => trial.score), borderColor: "#22c55e", backgroundColor: "rgba(34, 197, 94, .12)", fill: true, tension: .2, pointRadius: 4 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (item) => `Score: ${Number(item.parsed.y).toFixed(3)}` } } }, scales: { x: { grid: { display: false } }, y: { ticks: { callback: (value) => Number(value).toFixed(2) } } } },
  });
}
watch(() => props.trials, async () => { await nextTick(); drawChart(); }, { deep: true });
onMounted(drawChart);
onBeforeUnmount(() => chart?.destroy());
</script>

<template>
  <div class="card card-border bg-base-100">
    <div class="card-body p-4">
      <h3 class="font-medium">Optimization progress</h3>
      <p class="text-sm text-base-content/60">Higher is better; the score measures change from the starting snapshot.</p>
      <div class="h-56"><canvas ref="canvas"></canvas></div>
    </div>
  </div>
</template>
