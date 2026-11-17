import { createLibrary } from "@openuidev/react-lang";
import { openuiLibrary } from "@openuidev/react-ui/genui-lib";

/**
 * The slice of OpenUI's component library that Ethan lets the model use:
 * charts, a table and plain text. No forms, buttons or actions, so a generated
 * visual can display data and nothing else.
 *
 * This file is the single source of truth for two things:
 *  - what <Visual> can render (components/Visual.tsx)
 *  - what the backend tells the model it may write (`npm run gen:prompt`
 *    turns these signatures into ../prompts/openui.txt)
 */
export const VISUAL_COMPONENTS = [
  "Stack",
  "TextContent",
  "BarChart",
  "HorizontalBarChart",
  "LineChart",
  "AreaChart",
  "PieChart",
  "Series",
  "Table",
  "Col",
] as const;

export const visualsLibrary = createLibrary({
  root: "Stack",
  components: VISUAL_COMPONENTS.map((name) => openuiLibrary.components[name]),
});
