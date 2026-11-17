"use client";

import { Component, ReactNode } from "react";
import { Renderer } from "@openuidev/react-lang";
import { visualsLibrary } from "@/lib/visuals-library";

/** A malformed program from the model must never take the answer down with it. */
class VisualBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function Source({ code }: { code: string }) {
  return (
    <pre className="overflow-x-auto rounded-[10px] bg-subtle p-4 text-[13px] leading-relaxed ring-1 ring-line-soft">
      <code>{code}</code>
    </pre>
  );
}

/**
 * Renders an OpenUI Lang program: a chart or table the model wrote next to its
 * answer, or one a view built from live data (lib/openui.ts). Display only; the
 * library it renders with has no forms, buttons or actions.
 */
export function Visual({ code, streaming = false, framed = true }: { code: string; streaming?: boolean; framed?: boolean }) {
  if (!code.trim()) return null;
  return (
    <VisualBoundary fallback={<Source code={code} />}>
      <div className={`ethan-visual text-[14px] leading-normal ${framed ? "rounded-[14px] bg-surface p-5 ring-1 ring-line-soft" : ""}`}>
        {/* Charts use OpenUI's own blue ramp. genui-lib bundles its own theme context,
            so a ThemeProvider from the package root cannot recolour them. */}
        <Renderer library={visualsLibrary} response={code} isStreaming={streaming} />
      </div>
    </VisualBoundary>
  );
}
