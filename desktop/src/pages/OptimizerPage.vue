<script setup lang="ts">
import { useStudioPageContext } from "./studio-page-context";

const studio = useStudioPageContext();
</script>

<template>
  <section class="card bg-base-200">
    <div class="card-body">
      <h2 class="card-title">Hyperopt optimizer</h2>
      <p class="text-sm text-base-content/70">
        Hyperopt refreshes the Builder market data first, then evaluates the
        deterministic template parameter ranges.
      </p>
      <div class="mt-3 grid gap-3 md:grid-cols-2">
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Hyperopt epochs</legend>
          <input
            v-model.number="studio.epochs"
            type="number"
            min="1"
            max="10000"
            class="input w-full"
          />
          <p class="label">
            Higher values explore more parameter combinations.
          </p>
        </fieldset>
        <div class="rounded-box border border-base-300 p-4">
          <div class="text-sm text-base-content/60">Current run context</div>
          <div class="mt-1 font-medium">
            {{ studio.strategy.name || "Create a template in Builder" }}
          </div>
          <div class="mt-1 text-sm text-base-content/70">
            {{ studio.exchange }} · {{ studio.tradingMode }} ·
            {{ studio.pairs }} · {{ studio.timeframes
            }}<span v-if="studio.timerange"> · {{ studio.timerange }}</span>
          </div>
        </div>
      </div>
      <div class="mt-4 grid gap-3 md:grid-cols-2">
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Optimization goal</legend>
          <select
            v-model="studio.optimizationGoal.profile"
            class="select w-full"
          >
            <option value="balanced">Balanced</option>
            <option value="higher_frequency">Higher frequency</option>
            <option value="return_focused">Return focused</option>
            <option value="capital_preservation">Capital preservation</option>
          </select>
          <p class="label">
            Generates the Freqtrade loss objective; it does not invent new
            logic.
          </p>
        </fieldset>
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Target trades / year</legend>
          <input
            v-model.number="studio.optimizationGoal.target_trades_per_year"
            type="number"
            min="1"
            max="100000"
            class="input w-full"
          />
          <p class="label">A target, not a reason to accept losing churn.</p>
        </fieldset>
        <fieldset class="fieldset">
          <legend class="fieldset-legend">
            Minimum trades / validation test
          </legend>
          <input
            v-model.number="studio.optimizationGoal.min_trades_per_test"
            type="number"
            min="1"
            max="10000"
            class="input w-full"
          />
          <p class="label">Low-sample tests reduce the stability score.</p>
        </fieldset>
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Maximum drawdown [%]</legend>
          <input
            v-model.number="studio.optimizationGoal.max_drawdown_pct"
            type="number"
            min="0.1"
            max="100"
            step="0.1"
            class="input w-full"
          />
        </fieldset>
        <fieldset class="fieldset">
          <legend class="fieldset-legend">Minimum profit factor</legend>
          <input
            v-model.number="studio.optimizationGoal.min_profit_factor"
            type="number"
            min="0"
            max="100"
            step="0.1"
            class="input w-full"
          />
        </fieldset>
      </div>
      <div class="mt-3">
        <button
          class="btn btn-primary"
          :disabled="studio.busy || !studio.strategy.parameters.length"
          @click="studio.run(true)"
        >
          <span>Optimize</span
          ><span
            v-if="studio.busy"
            class="loading loading-spinner loading-sm"
          ></span>
        </button>
      </div>
      <div
        v-if="studio.optimizationReport"
        class="mt-4 rounded-box border border-base-300 bg-base-100 p-4"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="font-medium">Optimization feasibility</h3>
          <span
            class="badge"
            :class="
              studio.optimizationReport.goal_met
                ? 'badge-success'
                : 'badge-warning'
            "
            >{{
              studio.optimizationReport.goal_met
                ? "Goal met"
                : "Infeasible fallback"
            }}</span
          >
        </div>
        <div
          v-if="!studio.optimizationReport.goal_met"
          role="alert"
          class="alert alert-warning alert-soft mt-3 text-sm"
        >
          <span
            >This snapshot uses the best available fallback, not a strategy that
            met every goal.</span
          >
        </div>
        <p class="mt-2 text-sm text-base-content/70">
          {{ studio.optimizationReport.summary }}
        </p>
        <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <div class="text-xs text-base-content/60">Target trades / year</div>
            <div class="font-medium">
              {{
                studio.metricValue(
                  studio.optimizationReport.target_trades_per_year,
                )
              }}
            </div>
          </div>
          <div>
            <div class="text-xs text-base-content/60">
              Selected trades / year
            </div>
            <div class="font-medium">
              {{
                studio.metricValue(
                  studio.optimizationReport.best_annualized_trades,
                )
              }}
            </div>
          </div>
          <div>
            <div class="text-xs text-base-content/60">
              Search maximum / year
            </div>
            <div class="font-medium">
              {{
                studio.metricValue(
                  studio.optimizationReport.max_observed_annualized_trades,
                )
              }}
            </div>
          </div>
          <div>
            <div class="text-xs text-base-content/60">Compliant candidates</div>
            <div class="font-medium">
              {{
                studio.metricValue(
                  studio.optimizationReport.feasible_candidate_count,
                )
              }}
            </div>
          </div>
        </div>
      </div>
      <div v-if="studio.strategy.parameters.length" class="mt-5">
        <h3 class="font-medium">Optimizable parameters</h3>
        <div class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
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
      </div>
    </div>
  </section>
</template>
