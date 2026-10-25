"use client";

import { Fragment, ReactNode } from "react";

/**
 * Small markdown renderer for LLM answers: paragraphs, headings, lists,
 * tables, code blocks, bold/italic/inline code, and [n] citations rendered
 * as superscript footnote links.
 */

type CiteHandler = (ref: number) => void;

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[\d+(?:\s*[,–-]\s*\d+)*\]|【\d+[^】]*】|(?<![*\w])\*[^*\s][^*]*\*(?!\w))/g;

function renderInline(text: string, onCite: CiteHandler, maxRef: number, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(INLINE)) {
    const tok = m[0];
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const key = `${keyPrefix}-${i++}`;
    if (tok.startsWith("**")) out.push(<strong key={key} className="font-semibold">{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={key} className="rounded-[4px] bg-subtle px-1 py-0.5 text-[0.88em] ring-1 ring-line-soft">{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("[") || tok.startsWith("【")) {
      const refs = [...new Set((tok.match(/\d+/g) ?? []).map(Number))].filter((n) => n >= 1 && n <= maxRef);
      if (!refs.length) out.push(tok);
      else
        out.push(
          <sup key={key} className="ml-[1px] whitespace-nowrap">
            {refs.map((ref, j) => (
              <Fragment key={ref}>
                {j > 0 && <span className="text-faint">,</span>}
                <button
                  onClick={() => onCite(ref)}
                  className="tabular px-[1px] text-[0.78em] font-semibold text-muted underline-offset-2 hover:text-ink hover:underline"
                  aria-label={`Source ${ref}`}
                >
                  {ref}
                </button>
              </Fragment>
            ))}
          </sup>,
        );
    } else out.push(<em key={key}>{tok.slice(1, -1)}</em>);
    last = at + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const LIST = /^\s*([-*•]|\d+[.)])\s+/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|[\s:|-]+\|\s*$/;
const HEADING = /^(#{1,4})\s+(.*)/;
const CITES_ONLY = /^(\s*(\[\d+(?:\s*[,–-]\s*\d+)*\]|【\d+[^】]*】)[\s.,]*)+$/;

export function Markdown({ text, onCite, maxRef }: { text: string; onCite: CiteHandler; maxRef: number }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  const inline = (s: string, k: string) => renderInline(s, onCite, maxRef, k);
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }

    if (line.startsWith("```")) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i++;
      blocks.push(
        <pre key={i} className="overflow-x-auto rounded-[10px] bg-subtle p-4 text-[13px] leading-relaxed ring-1 ring-line-soft">
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    const heading = line.match(HEADING);
    if (heading) {
      blocks.push(
        <h3 key={i} className="pt-2 font-display text-[16px] font-medium text-ink">
          {inline(heading[2], `h${i}`)}
        </h3>,
      );
      i++;
      continue;
    }

    if (TABLE_ROW.test(line)) {
      const rows: string[][] = [];
      while (i < lines.length && TABLE_ROW.test(lines[i])) {
        if (!TABLE_RULE.test(lines[i])) rows.push(lines[i].trim().slice(1, -1).split("|").map((c) => c.trim()));
        i++;
      }
      blocks.push(
        <div key={i} className="overflow-x-auto">
          <table className="w-full border-collapse text-[14px]">
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri} className="border-b border-line-soft">
                  {r.map((c, ci) => {
                    const Cell = ri === 0 ? "th" : "td";
                    return (
                      <Cell key={ci} className={`py-2 pr-4 text-left align-top ${ri === 0 ? "font-medium text-muted" : ""}`}>
                        {inline(c, `t${i}-${ri}-${ci}`)}
                      </Cell>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (LIST.test(line)) {
      const ordered = /^\s*\d/.test(line);
      const items: string[] = [];
      while (i < lines.length && LIST.test(lines[i])) items.push(lines[i++].replace(LIST, ""));
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={i} className={`space-y-2 pl-5 marker:text-faint ${ordered ? "list-decimal" : "list-disc"}`}>
          {items.map((it, ii) => (
            <li key={ii} className="pl-1">
              {inline(it, `l${i}-${ii}`)}
            </li>
          ))}
        </List>,
      );
      continue;
    }

    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !LIST.test(lines[i]) && !lines[i].startsWith("```") && !HEADING.test(lines[i]) && !TABLE_ROW.test(lines[i])) {
      // Citations on their own line belong to the sentence above them
      if (para.length && CITES_ONLY.test(lines[i])) para[para.length - 1] += ` ${lines[i++].trim()}`;
      else para.push(lines[i++]);
    }

    // A paragraph made only of citations reads as a footnote line, not stray digits
    const joined = para.join(" ");
    if (CITES_ONLY.test(joined)) {
      const refs = [...new Set((joined.match(/\d+/g) ?? []).map(Number))].filter((n) => n >= 1 && n <= maxRef);
      if (refs.length) {
        blocks.push(
          <p key={i} className="text-[13px] text-faint">
            Drawn from{" "}
            {refs.map((ref, j) => (
              <Fragment key={ref}>
                {j > 0 && ", "}
                <button onClick={() => onCite(ref)} className="tabular text-muted underline underline-offset-4 hover:text-ink">
                  {ref}
                </button>
              </Fragment>
            ))}
          </p>,
        );
        continue;
      }
    }

    blocks.push(
      <p key={i}>
        {para.map((p, pi) => (
          <Fragment key={pi}>
            {pi > 0 && <br />}
            {inline(p, `p${i}-${pi}`)}
          </Fragment>
        ))}
      </p>,
    );
  }

  return <div className="space-y-4">{blocks}</div>;
}
