/**
 * Small builders that write OpenUI Lang for charts the app draws from its own
 * data (performance, cost, evaluation). They go through the same <Visual>
 * renderer as the charts the model writes, so there is one charting path.
 */

const str = (value: string) => JSON.stringify(value);
const list = (values: (string | number)[]) => `[${values.map((v) => (typeof v === "number" ? String(Number.isFinite(v) ? v : 0) : str(v))).join(", ")}]`;

export interface ChartSeries {
  name: string;
  values: number[];
}

function seriesList(series: ChartSeries[]) {
  return `[${series.map((s) => `Series(${str(s.name)}, ${list(s.values)})`).join(", ")}]`;
}

interface AxisOptions {
  variant?: "grouped" | "stacked";
  xLabel?: string;
  yLabel?: string;
  height?: number;
}

export function barChart(labels: string[], series: ChartSeries[], o: AxisOptions = {}) {
  const args = [list(labels), seriesList(series), str(o.variant ?? "grouped"), str(o.xLabel ?? ""), str(o.yLabel ?? "")];
  if (o.height) args.push(String(o.height));
  return `BarChart(${args.join(", ")})`;
}

export function horizontalBarChart(labels: string[], series: ChartSeries[], o: AxisOptions = {}) {
  return `HorizontalBarChart(${[list(labels), seriesList(series), str(o.variant ?? "grouped"), str(o.xLabel ?? ""), str(o.yLabel ?? "")].join(", ")})`;
}

export function lineChart(labels: string[], series: ChartSeries[], o: Omit<AxisOptions, "variant"> = {}) {
  const args = [list(labels), seriesList(series), str("linear"), str(o.xLabel ?? ""), str(o.yLabel ?? "")];
  if (o.height) args.push(String(o.height));
  return `LineChart(${args.join(", ")})`;
}

export function pieChart(labels: string[], values: number[], variant: "pie" | "donut" = "donut") {
  return `PieChart(${list(labels)}, ${list(values)}, ${str(variant)})`;
}

export function table(columns: { label: string; data: (string | number)[]; type?: "string" | "number" }[]) {
  return `Table([${columns.map((c) => `Col(${str(c.label)}, ${list(c.data)}, ${str(c.type ?? "string")})`).join(", ")}])`;
}

/** A complete program with one root Stack holding the given components. */
export function program(...components: string[]) {
  const names = components.map((_, i) => `c${i}`);
  return [`root = Stack([${names.join(", ")}])`, ...components.map((c, i) => `${names[i]} = ${c}`)].join("\n");
}
