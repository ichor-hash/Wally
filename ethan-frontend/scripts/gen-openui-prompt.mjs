// Writes ../prompts/openui.txt: the instructions the backend appends to the system
// prompt when a question is asked with "visuals" on.
//
// The component signatures come straight from the OpenUI library the frontend
// renders with (lib/visuals-library.ts), so the model can only be told about
// components that <Visual> can actually draw. Run after changing that file or
// upgrading @openuidev/*:  npm run gen:prompt
//
// OpenUI's stock prompt is about 5,000 characters. This one keeps only the
// signatures and the rules that matter for a display-only chart, because every
// character here is paid for on every question asked with visuals on.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { visualsLibrary } from "../lib/visuals-library.ts";

const full = visualsLibrary.prompt();
const section = full.split("## Component Signatures")[1]?.split("\n## ")[0] ?? "";
const signatures = section
  .split("\n")
  .filter((line) => /^[A-Z][A-Za-z]+\(/.test(line))
  // Stack's long flex options are irrelevant for a single chart
  .map((line) => (line.startsWith("Stack(") ? "Stack(children: any[]) — Vertical container; always the root" : line))
  .join("\n");

if (!signatures.includes("BarChart(") || !signatures.includes("Table(")) {
  throw new Error("Could not extract component signatures from the OpenUI prompt; its format may have changed.");
}

const prompt = `VISUALS: when, and only when, the answer compares three or more numbers that all come from the context chunks (amounts by segment, values across years, shares of a total), add ONE visual after the written answer. Never add one for a single figure, a yes/no answer or a refusal.

Write the visual as a fenced code block tagged openui, in OpenUI Lang:
- One statement per line: identifier = Expression. The first line must be root = Stack([...]).
- Arguments are positional, in the order shown below. Strings use double quotes. Numbers are plain (178353, not "178,353" or $178B).
- Every identifier you define must be reachable from root.
- Use only these components:
${signatures}
- Use only numbers that appear in the context chunks. Do not estimate, extrapolate or fill gaps. Put the unit in the series name or axis label.
- Never plot a total next to the parts it sums; chart the parts and mention the total in the text.
- Keep the written answer complete and cited on its own; the visual repeats it, it does not replace it.

Example of the format (the values are placeholders, never reuse them):
\`\`\`openui
root = Stack([chart])
chart = BarChart(["North", "South", "West"], [Series("Units sold", [1200, 950, 610])], "grouped", "Region", "Units")
\`\`\`
`;

const out = resolve(dirname(fileURLToPath(import.meta.url)), "../../prompts/openui.txt");
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, prompt, "utf8");
console.log(`Wrote ${out} (${prompt.length} characters, about ${Math.round(prompt.length / 4)} tokens)`);
