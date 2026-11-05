<script setup lang="ts">
import { useStudioPageContext } from "./studio-page-context";

const studio = useStudioPageContext();
</script>

<template>
  <section class="card bg-base-200">
    <div class="card-body">
      <h2 class="card-title">Walk-forward validation</h2>
      <p class="text-sm text-base-content/70">
        Standard validation uses 70% chronological training and 10 equal
        out-of-sample test windows. Quick validation uses 2.5 years and 5 test
        windows. The score is
        <span class="font-medium">100 ÷ (1 + σ test return)</span>, and becomes
        zero when mean test return is not positive.
      </p>
      <div class="mt-3 flex flex-wrap gap-3">
        <fieldset class="fieldset min-w-0 w-full md:w-72">
          <legend class="fieldset-legend">Validation range</legend>
          <input
            v-model="studio.validationTimerange"
            class="input min-w-0 w-full"
            placeholder="20210101-20260101"
          />
          <p class="label">Standard: five years and 10 test windows.</p>
        </fieldset>
        <fieldset class="fieldset min-w-0 w-full md:w-80">
          <legend class="fieldset-legend">Quick validation</legend>
          <input
            :value="studio.quickValidationTimerange"
            readonly
            class="input min-w-0 w-full"
          />
          <p class="label">
            2.5 years and 5 test windows. Reuses local candles when coverage is
            available.
          </p>
        </fieldset>
      </div>
      <div class="mt-3 flex flex-wrap gap-3">
        <button
          class="btn"
          :disabled="studio.busy || !studio.strategy.parameters.length"
          @click="studio.runValidation(true)"
        >
          <span>Quick Validate</span
          ><span
            v-if="studio.busy"
            class="loading loading-spinner loading-sm"
          ></span></button
        ><button
          class="btn btn-primary"
          :disabled="studio.busy || !studio.strategy.parameters.length"
          @click="studio.runValidation()"
        >
          <span>Validate</span
          ><span
            v-if="studio.busy"
            class="loading loading-spinner loading-sm"
          ></span>
        </button>
      </div>
      <template v-if="studio.validation"
        ><div class="mt-5 grid gap-3 sm:grid-cols-3">
          <div class="rounded-box bg-base-100 p-4">
            <div class="text-sm text-base-content/60">Stability score</div>
            <div
              class="mt-1 text-2xl font-medium"
              :class="
                studio.valueTone('Return [%]', studio.validation.mean_return)
              "
            >
              {{ studio.metricValue(studio.validation.stability_score) }}
            </div>
            <div class="text-xs text-base-content/60">
              Higher is more stable.
            </div>
          </div>
          <div class="rounded-box bg-base-100 p-4">
            <div class="text-sm text-base-content/60">Mean test return [%]</div>
            <div
              class="mt-1 text-xl font-medium"
              :class="
                studio.valueTone('Return [%]', studio.validation.mean_return)
              "
            >
              {{ studio.metricValue(studio.validation.mean_return) }}
            </div>
          </div>
          <div class="rounded-box bg-base-100 p-4">
            <div class="text-sm text-base-content/60">Test return σ</div>
            <div
              class="mt-1 text-xl font-medium"
              :class="
                studio.valueTone(
                  'Drawdown [%]',
                  -studio.validation.return_stddev,
                )
              "
            >
              {{ studio.metricValue(studio.validation.return_stddev) }}
            </div>
            <div class="text-xs text-base-content/60">
              {{ studio.validation.coverage }}
            </div>
          </div>
        </div>
        <div
          class="mt-5 max-h-96 overflow-auto rounded-box border border-base-300"
        >
          <table class="table table-pin-rows table-sm">
            <thead>
              <tr>
                <th>Split</th>
                <th>Timerange</th>
                <th>Return [%]</th>
                <th>Win Rate [%]</th>
                <th>Profit Factor</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="slice in [
                  studio.validation.training,
                  ...studio.validation.tests,
                ]"
                :key="slice.label"
              >
                <td>{{ slice.label }}</td>
                <td>{{ slice.timerange }}</td>
                <td
                  :class="
                    studio.valueTone(
                      'Return [%]',
                      slice.backtest.metrics['Return [%]'],
                    )
                  "
                >
                  {{ studio.metricValue(slice.backtest.metrics["Return [%]"]) }}
                </td>
                <td
                  :class="
                    studio.valueTone(
                      'Win Rate [%]',
                      slice.backtest.metrics['Win Rate [%]'],
                    )
                  "
                >
                  {{
                    studio.metricValue(slice.backtest.metrics["Win Rate [%]"])
                  }}
                </td>
                <td
                  :class="
                    studio.valueTone(
                      'Profit Factor',
                      slice.backtest.metrics['Profit Factor'],
                    )
                  "
                >
                  {{
                    studio.metricValue(slice.backtest.metrics["Profit Factor"])
                  }}
                </td>
                <td>
                  <button
                    class="btn btn-ghost btn-xs"
                    @click="studio.selectHistory(slice.backtest)"
                  >
                    View
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div></template
      >
      <div
        v-if="studio.validation"
        class="mt-5 rounded-box border border-base-300 p-4"
      >
        <h3 class="font-medium">Validation confidence</h3>
        <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div class="rounded-box bg-base-100 p-3">
            <div class="text-sm text-base-content/60">
              Sample-adjusted stability
            </div>
            <div
              class="mt-1 text-xl font-medium"
              :class="
                studio.valueTone('Return [%]', studio.validation.mean_return)
              "
            >
              {{ studio.metricValue(studio.validation.stability_score) }}
            </div>
          </div>
          <div class="rounded-box bg-base-100 p-3">
            <div class="text-sm text-base-content/60">Out-of-sample trades</div>
            <div class="mt-1 text-xl font-medium">
              {{ studio.validation.total_test_trades }}
            </div>
            <div class="text-xs text-base-content/60">
              Minimum {{ studio.validation.minimum_test_trades }} per test.
            </div>
          </div>
          <div class="rounded-box bg-base-100 p-3">
            <div class="text-sm text-base-content/60">Mean test return [%]</div>
            <div
              class="mt-1 text-xl font-medium"
              :class="
                studio.valueTone('Return [%]', studio.validation.mean_return)
              "
            >
              {{ studio.metricValue(studio.validation.mean_return) }}
            </div>
          </div>
          <div class="rounded-box bg-base-100 p-3">
            <div class="text-sm text-base-content/60">
              Test return deviation
            </div>
            <div class="mt-1 text-xl font-medium">
              {{ studio.metricValue(studio.validation.return_stddev) }}
            </div>
          </div>
        </div>
        <p
          v-if="studio.validation.snapshot_path"
          class="mt-3 text-sm text-base-content/70"
        >
          Saved validation snapshot: {{ studio.validation.snapshot_path }}
        </p>
        <div
          class="mt-3 max-h-80 overflow-auto rounded-box border border-base-300"
        >
          <table class="table table-pin-rows table-sm">
            <thead>
              <tr>
                <th>Split</th>
                <th>Trades</th>
                <th>Return [%]</th>
                <th>Profit Factor</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="slice in [
                  studio.validation.training,
                  ...studio.validation.tests,
                ]"
                :key="`confidence-${slice.label}`"
              >
                <td>{{ slice.label }}</td>
                <td>
                  {{
                    studio.metricValue(slice.backtest.metrics["Total Trades"])
                  }}
                </td>
                <td
                  :class="
                    studio.valueTone(
                      'Return [%]',
                      slice.backtest.metrics['Return [%]'],
                    )
                  "
                >
                  {{ studio.metricValue(slice.backtest.metrics["Return [%]"]) }}
                </td>
                <td
                  :class="
                    studio.valueTone(
                      'Profit Factor',
                      slice.backtest.metrics['Profit Factor'],
                    )
                  "
                >
                  {{
                    studio.metricValue(slice.backtest.metrics["Profit Factor"])
                  }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </section>
</template>
