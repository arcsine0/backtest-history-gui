<script setup lang="ts">
import { computed, ref } from "vue";
import {
  Handle,
  Position,
  VueFlow,
  type Connection,
  type Edge,
  type Node,
} from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/controls/dist/style.css";

type GraphNode = {
  id: string;
  type: string;
  parameters?: Record<string, unknown>;
};
type GraphEdge = {
  source_node: string;
  source_port: string;
  target_node: string;
  target_port: string;
};
type StrategyGraph = {
  version: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
};
type Port = {
  key: string;
  value_type: string;
  required?: boolean;
  description?: string;
  variadic?: boolean;
  minimum_connections?: number;
};
type Parameter = {
  key: string;
  value_type: "integer" | "decimal" | "boolean" | "choice";
  default: string | number | boolean;
  description: string;
  minimum?: number | null;
  maximum?: number | null;
  decimals?: number | null;
  choices?: string[];
  optimizable?: boolean;
};
type NodeDefinition = {
  id: string;
  group: string;
  label: string;
  description: string;
  inputs: Port[];
  outputs: Port[];
  parameters: Parameter[];
};
type ResolvedParameter = Parameter & { value: string | number | boolean };
type FlowNodeData = {
  label: string;
  type: string;
  description: string;
  inputs: Port[];
  outputs: Port[];
  parameters: ResolvedParameter[];
  variadicInputs: Port[];
};

const props = defineProps<{
  graph: StrategyGraph;
  catalog: NodeDefinition[];
  editable?: boolean;
}>();
const emit = defineEmits<{
  "update:graph": [graph: StrategyGraph];
}>();

const pendingInputSlots = ref<Record<string, string[]>>({});

const definitions = computed(
  () => new Map(props.catalog.map((definition) => [definition.id, definition])),
);

function fallbackPort(key: string): Port {
  return { key, value_type: "connection" };
}

function uniquePorts(ports: Port[]) {
  return ports.filter(
    (port, index) =>
      ports.findIndex((candidate) => candidate.key === port.key) === index,
  );
}

function portSort(left: Port, right: Port) {
  const sequence = (key: string) => {
    const match = key.match(/_(\d+)$/);
    return match ? Number(match[1]) : 1;
  };
  return (
    left.key.localeCompare(right.key) ||
    sequence(left.key) - sequence(right.key)
  );
}

function portsFor(node: GraphNode, direction: "input" | "output") {
  const definition = definitions.value.get(node.type);
  const declared =
    direction === "input"
      ? (definition?.inputs ?? [])
      : (definition?.outputs ?? []);
  const connected = props.graph.edges
    .filter((edge) =>
      direction === "input"
        ? edge.target_node === node.id
        : edge.source_node === node.id,
    )
    .map((edge) =>
      fallbackPort(direction === "input" ? edge.target_port : edge.source_port),
    );
  const pending =
    direction === "input"
      ? (pendingInputSlots.value[node.id] ?? []).map(fallbackPort)
      : [];
  return uniquePorts([...declared, ...connected, ...pending]).sort(portSort);
}

function variadicInputsFor(node: GraphNode) {
  return (definitions.value.get(node.type)?.inputs ?? []).filter(
    (port) => port.variadic,
  );
}

function nextInputPort(node: GraphNode, port: Port) {
  const used = new Set(portsFor(node, "input").map((input) => input.key));
  let number = 2;
  while (used.has(`${port.key}_${number}`)) number += 1;
  return `${port.key}_${number}`;
}

function addVariadicInput(node: GraphNode, port: Port) {
  if (!props.editable) return;
  const key = nextInputPort(node, port);
  pendingInputSlots.value = {
    ...pendingInputSlots.value,
    [node.id]: [...(pendingInputSlots.value[node.id] ?? []), key],
  };
}

function graphNode(nodeId: string) {
  return props.graph.nodes.find((node) => node.id === nodeId);
}

function addVariadicInputById(nodeId: string, port: Port) {
  const node = graphNode(nodeId);
  if (node) addVariadicInput(node, port);
}

function inputDefinitionFor(node: GraphNode, key: string) {
  return (definitions.value.get(node.type)?.inputs ?? []).find(
    (port) =>
      port.key === key ||
      (port.variadic && new RegExp(`^${port.key}_[1-9][0-9]*$`).test(key)),
  );
}

function outputDefinitionFor(node: GraphNode, key: string) {
  return (definitions.value.get(node.type)?.outputs ?? []).find(
    (port) => port.key === key,
  );
}

function isValidConnection(connection: Connection) {
  const { source, sourceHandle, target, targetHandle } = connection;
  if (
    !source ||
    !sourceHandle ||
    !target ||
    !targetHandle ||
    source === target
  ) {
    return false;
  }
  const sourceNode = graphNode(source);
  const targetNode = graphNode(target);
  if (!sourceNode || !targetNode) return false;
  const sourcePort = outputDefinitionFor(
    sourceNode,
    sourceHandle.replace(/^out:/, ""),
  );
  const targetPort = inputDefinitionFor(
    targetNode,
    targetHandle.replace(/^in:/, ""),
  );
  if (
    !sourcePort ||
    !targetPort ||
    sourcePort.value_type !== targetPort.value_type
  ) {
    return false;
  }
  return !props.graph.edges.some(
    (edge) =>
      edge.target_node === target &&
      edge.target_port === targetHandle.replace(/^in:/, ""),
  );
}

function onConnect(connection: Connection) {
  if (!props.editable || !isValidConnection(connection)) {
    return;
  }
  const { source, sourceHandle, target, targetHandle } = connection;
  if (!source || !sourceHandle || !target || !targetHandle) return;
  const sourcePort = sourceHandle.replace(/^out:/, "");
  const targetPort = targetHandle.replace(/^in:/, "");
  const alreadyConnected = props.graph.edges.some(
    (edge) => edge.target_node === target && edge.target_port === targetPort,
  );
  if (alreadyConnected) return;
  const graph = {
    ...props.graph,
    edges: [
      ...props.graph.edges,
      {
        source_node: source,
        source_port: sourcePort,
        target_node: target,
        target_port: targetPort,
      },
    ],
  };
  pendingInputSlots.value = {
    ...pendingInputSlots.value,
    [target]: (pendingInputSlots.value[target] ?? []).filter(
      (key) => key !== targetPort,
    ),
  };
  emit("update:graph", graph);
}

function removeEdges(edges: Edge[]) {
  if (!props.editable) return;
  const removed = new Set(edges.map((edge) => edge.id));
  emit("update:graph", {
    ...props.graph,
    edges: props.graph.edges.filter(
      (edge, index) =>
        !removed.has(
          `${edge.source_node}-${edge.source_port}-${edge.target_node}-${edge.target_port}-${index}`,
        ),
    ),
  });
}

function parameterValue(value: unknown, fallback: string | number | boolean) {
  return typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
    ? value
    : fallback;
}

function parametersFor(node: GraphNode): ResolvedParameter[] {
  const definition = definitions.value.get(node.type);
  const declared = definition?.parameters ?? [];
  const declaredKeys = new Set(declared.map((parameter) => parameter.key));
  const undeclared = Object.entries(node.parameters ?? {})
    .filter(([key]) => !declaredKeys.has(key))
    .map(
      ([key, value]) =>
        ({
          key,
          value_type:
            typeof value === "boolean"
              ? "boolean"
              : typeof value === "number"
                ? "decimal"
                : "choice",
          default: String(value),
          description: "Stored graph value.",
          value,
        }) as ResolvedParameter,
    );
  return [
    ...declared.map(
      (parameter): ResolvedParameter => ({
        ...parameter,
        value: parameterValue(
          node.parameters?.[parameter.key],
          parameter.default,
        ),
      }),
    ),
    ...undeclared,
  ];
}

function nodeHeight(node: GraphNode) {
  return (
    58 +
    Math.max(portsFor(node, "input").length, portsFor(node, "output").length) *
      24 +
    parametersFor(node).length * 54
  );
}

const nodeDepths = computed(() => {
  const incoming = new Map<string, string[]>();
  for (const edge of props.graph.edges) {
    incoming.set(edge.target_node, [
      ...(incoming.get(edge.target_node) ?? []),
      edge.source_node,
    ]);
  }
  const resolve = (id: string, visited = new Set<string>()): number => {
    if (visited.has(id)) return 0;
    const parents = incoming.get(id) ?? [];
    return parents.length
      ? Math.max(
          ...parents.map((parent) =>
            resolve(parent, new Set([...visited, id])),
          ),
        ) + 1
      : 0;
  };
  return new Map(props.graph.nodes.map((node) => [node.id, resolve(node.id)]));
});

const flowNodes = computed<Node<FlowNodeData>[]>(() => {
  const lanes = new Map<number, number>();
  return props.graph.nodes.map((node) => {
    const depth = nodeDepths.value.get(node.id) ?? 0;
    const y = lanes.get(depth) ?? 0;
    lanes.set(depth, y + nodeHeight(node) + 36);
    const definition = definitions.value.get(node.type);
    return {
      id: node.id,
      position: { x: depth * 340, y },
      data: {
        label: definition?.label ?? node.id,
        type: node.type,
        description: definition?.description ?? "Strategy graph node.",
        inputs: portsFor(node, "input"),
        outputs: portsFor(node, "output"),
        parameters: parametersFor(node),
        variadicInputs: variadicInputsFor(node),
      },
      draggable: false,
      connectable: Boolean(props.editable),
      selectable: Boolean(props.editable),
      focusable: false,
      class: `strategy-node strategy-node--${definition?.group ?? node.type.split(".", 1)[0]}`,
    };
  });
});

const flowEdges = computed<Edge[]>(() =>
  props.graph.edges.map((edge, index) => ({
    id: `${edge.source_node}-${edge.source_port}-${edge.target_node}-${edge.target_port}-${index}`,
    source: edge.source_node,
    sourceHandle: `out:${edge.source_port}`,
    target: edge.target_node,
    targetHandle: `in:${edge.target_port}`,
    type: "smoothstep",
    selectable: Boolean(props.editable),
    focusable: Boolean(props.editable),
  })),
);

const graphKey = computed(() =>
  JSON.stringify({ nodes: props.graph.nodes, edges: props.graph.edges }),
);

function readableKey(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatValue(parameter: ResolvedParameter) {
  if (
    typeof parameter.value === "number" &&
    parameter.decimals !== undefined &&
    parameter.decimals !== null
  ) {
    return parameter.value.toFixed(parameter.decimals);
  }
  return String(parameter.value);
}

function rangeStep(parameter: ResolvedParameter) {
  if (parameter.value_type === "integer") return 1;
  return 10 ** -(parameter.decimals ?? 2);
}

function isRanged(parameter: ResolvedParameter) {
  return (
    typeof parameter.value === "number" &&
    parameter.minimum !== null &&
    parameter.minimum !== undefined &&
    parameter.maximum !== null &&
    parameter.maximum !== undefined
  );
}
</script>

<template>
  <div class="strategy-flow rounded-box border border-base-300 bg-base-100">
    <VueFlow
      :key="graphKey"
      :nodes="flowNodes"
      :edges="flowEdges"
      fit-view-on-init
      :nodes-draggable="false"
      :nodes-connectable="editable"
      :elements-selectable="editable"
      :nodes-focusable="false"
      :edges-focusable="editable"
      :edges-updatable="false"
      :delete-key-code="editable ? ['Backspace', 'Delete'] : undefined"
      :pan-on-drag="true"
      :zoom-on-double-click="false"
      :min-zoom="0.35"
      :max-zoom="2"
      :is-valid-connection="isValidConnection"
      @connect="onConnect"
      @edges-delete="removeEdges"
    >
      <Background variant="dots" :gap="18" :size="1" />
      <Controls :show-interactive="false" />
      <template #node-default="node">
        <article class="strategy-flow-node" :title="node.data.description">
          <header class="strategy-flow-node__header">
            <span class="strategy-flow-node__label">{{ node.data.label }}</span>
            <span class="strategy-flow-node__id">{{ node.id }}</span>
          </header>

          <div
            v-if="node.data.inputs.length || node.data.outputs.length"
            class="strategy-flow-node__ports"
          >
            <div
              v-for="port in node.data.variadicInputs"
              :key="`add:${port.key}`"
              class="strategy-flow-node__variadic-control"
            >
              <span class="badge badge-xs badge-ghost">unlimited</span>
              <div
                class="tooltip tooltip-right"
                data-tip="Add another input handle"
              >
                <button
                  class="btn btn-ghost btn-xs"
                  type="button"
                  :disabled="!editable"
                  :aria-label="`Add input to ${node.data.label}`"
                  @click.stop="addVariadicInputById(node.id, port)"
                >
                  + input
                </button>
              </div>
            </div>
            <div
              v-for="port in node.data.inputs"
              :key="`in:${port.key}`"
              class="strategy-flow-node__port strategy-flow-node__port--input"
            >
              <Handle
                :id="`in:${port.key}`"
                type="target"
                :position="Position.Left"
                class="strategy-flow-node__handle"
                :connectable="editable"
              />
              <span>{{ port.key }}</span>
              <span class="strategy-flow-node__port-type">{{
                port.value_type
              }}</span>
            </div>
            <div
              v-for="port in node.data.outputs"
              :key="`out:${port.key}`"
              class="strategy-flow-node__port strategy-flow-node__port--output"
            >
              <span class="strategy-flow-node__port-type">{{
                port.value_type
              }}</span>
              <span>{{ port.key }}</span>
              <Handle
                :id="`out:${port.key}`"
                type="source"
                :position="Position.Right"
                class="strategy-flow-node__handle"
                :connectable="editable"
              />
            </div>
          </div>

          <div
            v-if="node.data.parameters.length"
            class="strategy-flow-node__parameters"
          >
            <div
              v-for="parameter in node.data.parameters"
              :key="parameter.key"
              class="strategy-flow-node__parameter"
            >
              <div class="strategy-flow-node__parameter-title">
                <span>{{ readableKey(parameter.key) }}</span>
                <span class="badge badge-xs badge-ghost">{{
                  formatValue(parameter)
                }}</span>
              </div>
              <input
                v-if="isRanged(parameter)"
                class="range range-xs range-primary pointer-events-none"
                type="range"
                :min="parameter.minimum"
                :max="parameter.maximum"
                :step="rangeStep(parameter)"
                :value="parameter.value"
                :aria-label="`${readableKey(parameter.key)} default value`"
                aria-readonly="true"
                tabindex="-1"
              />
              <input
                v-else-if="parameter.value_type === 'boolean'"
                class="checkbox checkbox-xs checkbox-primary pointer-events-none"
                type="checkbox"
                :checked="Boolean(parameter.value)"
                :aria-label="`${readableKey(parameter.key)} default value`"
                aria-readonly="true"
                tabindex="-1"
              />
              <div
                v-else-if="parameter.value_type === 'choice'"
                class="badge badge-sm badge-outline"
              >
                {{ formatValue(parameter) }}
              </div>
              <div
                v-if="isRanged(parameter)"
                class="strategy-flow-node__range-boundaries"
              >
                <span>{{ parameter.minimum }}</span
                ><span>{{ parameter.maximum }}</span>
              </div>
            </div>
          </div>
        </article>
      </template>
    </VueFlow>
  </div>
</template>

<style>
.strategy-flow {
  height: 36rem;
}

.strategy-flow .vue-flow__node {
  border: 0;
  background: transparent;
  box-shadow: none;
}

.strategy-flow-node {
  width: 17rem;
  overflow: visible;
  border: 1px solid
    color-mix(in oklab, var(--color-base-content) 20%, transparent);
  border-radius: var(--radius-box);
  background: var(--color-base-200);
  color: var(--color-base-content);
  text-align: left;
}

.strategy-flow-node__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  border-bottom: 1px solid
    color-mix(in oklab, var(--color-base-content) 14%, transparent);
  padding: 0.55rem 0.7rem;
}

.strategy-flow-node__label {
  font-size: 0.8rem;
  font-weight: 700;
}

.strategy-flow-node__id,
.strategy-flow-node__port-type,
.strategy-flow-node__range-boundaries {
  color: color-mix(in oklab, var(--color-base-content) 55%, transparent);
  font-size: 0.62rem;
  line-height: 0.8rem;
}

.strategy-flow-node__ports {
  display: grid;
  gap: 0.1rem;
  border-bottom: 1px solid
    color-mix(in oklab, var(--color-base-content) 14%, transparent);
  padding: 0.35rem 0;
}

.strategy-flow-node__variadic-control {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.35rem;
  padding: 0.1rem 0.45rem 0.2rem 0.7rem;
}

.strategy-flow-node__port {
  position: relative;
  display: flex;
  min-height: 1.35rem;
  align-items: center;
  gap: 0.35rem;
  padding: 0 0.7rem;
  font-size: 0.7rem;
}

.strategy-flow-node__port--output {
  justify-content: flex-end;
  text-align: right;
}

.strategy-flow-node__handle {
  width: 0.55rem;
  height: 0.55rem;
  border: 2px solid var(--color-base-100);
  background: var(--color-primary);
}

.strategy-flow-node__port--input .strategy-flow-node__handle {
  left: -0.35rem;
}

.strategy-flow-node__port--output .strategy-flow-node__handle {
  right: -0.35rem;
}

.strategy-flow-node__parameters {
  display: grid;
  gap: 0.45rem;
  padding: 0.55rem 0.7rem 0.7rem;
}

.strategy-flow-node__parameter {
  display: grid;
  gap: 0.28rem;
}

.strategy-flow-node__parameter-title,
.strategy-flow-node__range-boundaries {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}

.strategy-flow-node__parameter-title {
  align-items: center;
  font-size: 0.68rem;
  font-weight: 600;
}

.strategy-node--inputs .strategy-flow-node {
  border-color: color-mix(in oklab, var(--color-info) 65%, transparent);
}

.strategy-node--indicators .strategy-flow-node,
.strategy-node--processing .strategy-flow-node,
.strategy-node--filters .strategy-flow-node {
  border-color: color-mix(in oklab, var(--color-primary) 65%, transparent);
}

.strategy-node--risk .strategy-flow-node {
  border-color: color-mix(in oklab, var(--color-warning) 65%, transparent);
}

.strategy-node--signals .strategy-flow-node {
  border-color: color-mix(in oklab, var(--color-success) 65%, transparent);
}

.strategy-flow .vue-flow__controls {
  box-shadow: none;
}

.strategy-flow .vue-flow__controls-button {
  border-color: color-mix(in oklab, var(--color-base-content) 20%, transparent);
  background: var(--color-base-200);
  fill: var(--color-base-content);
}

.strategy-flow .vue-flow__edge-path {
  stroke: color-mix(in oklab, var(--color-base-content) 45%, transparent);
  stroke-width: 1.5;
}
</style>
