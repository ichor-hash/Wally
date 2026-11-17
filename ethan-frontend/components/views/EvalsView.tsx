"use client";

import { Fragment, useState } from "react";
import { EvalAnswerCase, EvalAnswerConfig, EvalReport } from "@/lib/api";
import { barChart, program } from "@/lib/openui";
import { Visual } from "../Visual";
import { Figure, SectionTitle, TextButton, ViewHeader } from "../ui";

const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

function Result({ passed, label, title }: { passed: boolean; label?: string; title?: string }) {
  return (
    <span className={`tabular inline-flex items-center gap-1.5 ${passed ? "text-ink" : "text-bad"}`} title={title}>
      <span className={`h-1.5 w-1.5 rounded-full ${passed ? "bg-ok" : "bg-bad"}`} />
      {label ?? (passed ? "Pass" : "Fail")}
    </span>
  );
}

function pipelineNotes(c: EvalAnswerCase) {
  const notes: string[] = [];
  if (c.corrected_query) notes.push(`re-searched as “${c.corrected_query}”`);
  for (const t of c.tools ?? []) notes.push(t);
  if (c.revised) notes.push("revised after verification");
  if (c.verification?.total) notes.push(`${c.verification.supported}/${c.verification.total} claims verified`);
  return notes;
}

function AnswerGrading({ answers }: { answers: Record<string, EvalAnswerConfig> }) {
  const [open, setOpen] = useState<string | null>(null);
  const [onlyFailures, setOnlyFailures] = useState(false);
  const levels = Object.keys(answers);
  const first = answers[levels[0]];
  const best = answers[levels.find((l) => l === "v3") ?? levels[levels.length - 1]];
  const categories = first.by_category ? Object.keys(first.by_category) : [];

  const byType = program(
    barChart(
      categories,
      levels.map((l) => ({
        name: l,
        values: categories.map((c) => Math.round(((answers[l].by_category?.[c]?.passed ?? 0) / (answers[l].by_category?.[c]?.total || 1)) * 100)),
      })),
      { xLabel: "Question type", yLabel: "Answers correct (%)", height: 280 },
    ),
  );

  const rows = first.cases
    .map((c, i) => ({ ...c, results: levels.map((l) => answers[l].cases[i]) }))
    .filter((r) => !onlyFailures || r.results.some((x) => !x.passed));

  return (
    <section className="mt-16">
      <SectionTitle aside={<span className="text-[12.5px] text-faint">{best.model} via {best.provider}</span>}>Answer grading</SectionTitle>
      <p className="mb-8 max-w-2xl text-[13.5px] leading-relaxed text-muted">
        Every question with an answer key, run through the full pipeline (the same code that answers in the app) and graded automatically. The required facts
        must appear, answerable questions must carry a citation, and unanswerable ones must be declined. Claims verified is Ethan&apos;s own checker,
        comparing each cited claim with the chunks it cites.
      </p>

      <div className="grid gap-x-10 gap-y-8 border-y border-line-soft py-8 sm:grid-cols-3">
        {levels.map((l) => {
          const a = answers[l];
          return (
            <div key={l} className="min-w-0">
              <p className="text-[13px] text-muted">{a.label}</p>
              <p className="tabular mt-2 font-display text-[40px] font-light leading-none tracking-[-0.03em] text-ink">
                {a.passed}/{a.total}
              </p>
              <p className="tabular mt-2 text-[12.5px] leading-relaxed text-faint">
                {a.claims_checked ? `${a.claims_supported}/${a.claims_checked} claims verified` : "no claim checks"}
                {a.tool_calls ? ` · ${a.tool_calls} tool calls` : ""}
                {a.revised ? ` · ${a.revised} revised` : ""}
                {a.corrected ? ` · ${a.corrected} re-searched` : ""}
                <br />
                {(a.avg_prompt_tokens + a.avg_completion_tokens).toLocaleString()} tokens, {a.avg_llm_calls} model calls, {a.avg_seconds} s per question
              </p>
            </div>
          );
        })}
      </div>

      {categories.length > 0 && (
        <div className="mt-10">
          <Visual code={byType} framed={false} />
        </div>
      )}

      <div className="mt-12">
        <SectionTitle aside={<TextButton onClick={() => setOnlyFailures((v) => !v)}>{onlyFailures ? "Show all" : "Show failures only"}</TextButton>}>
          Every graded answer
        </SectionTitle>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-[13px]">
            <thead>
              <tr className="text-left text-[12px] text-faint">
                <th className="py-2 pr-4 font-normal">Question</th>
                <th className="py-2 pr-4 font-normal">Type</th>
                {levels.map((l) => (
                  <th key={l} className="py-2 pr-4 font-normal whitespace-nowrap">
                    {l}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <Fragment key={r.id}>
                  <tr className="cursor-pointer border-t border-line-soft align-top hover:bg-subtle" onClick={() => setOpen(open === r.id ? null : r.id)}>
                    <td className="max-w-[22rem] py-2.5 pr-4 text-ink">{r.question}</td>
                    <td className="py-2.5 pr-4 text-muted">{r.category}</td>
                    {r.results.map((x, i) => (
                      <td key={levels[i]} className="py-2.5 pr-4">
                        <Result passed={x.passed} title={x.reason || pipelineNotes(x).join(" · ") || undefined} />
                      </td>
                    ))}
                  </tr>
                  {open === r.id && (
                    <tr className="bg-subtle">
                      <td colSpan={2 + levels.length} className="px-4 py-4">
                        <div className="grid gap-5 md:grid-cols-3">
                          {r.results.map((x, i) => (
                            <div key={levels[i]} className="min-w-0 text-[12.5px]">
                              <p className="font-medium text-ink">{levels[i]}</p>
                              {x.reason && <p className="mt-1 text-bad">{x.reason}</p>}
                              {pipelineNotes(x).length > 0 && <p className="mt-1 text-muted">{pipelineNotes(x).join(" · ")}</p>}
                              <p className="mt-2 line-clamp-6 whitespace-pre-wrap leading-relaxed text-muted">{x.answer}</p>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-[12px] text-faint">Click a row to read each pipeline&apos;s answer and what it did.</p>
      </div>
    </section>
  );
}

export function EvalsView({ report, error }: { report: EvalReport | null; error: string | null }) {
  const [onlyFailures, setOnlyFailures] = useState(false);

  if (!report) {
    return (
      <div className="mx-auto w-full max-w-[960px] px-6 py-12 sm:px-12 sm:py-16">
        <ViewHeader title="Evaluation" description="How well Ethan finds the right chunk and answers correctly, measured on questions with known answers." />
        <p className="py-10 text-[14px] leading-relaxed text-muted">
          {error ?? "Loading the latest report."}
          {error && (
            <>
              {" "}
              Run <code className="rounded-[4px] bg-subtle px-1 py-0.5 text-[13px] ring-1 ring-line-soft">python evals/run_evals.py --answers</code> in
              the project folder.
            </>
          )}
        </p>
      </div>
    );
  }

  const names = Object.keys(report.retrieval);
  const configs = names.map((n) => report.retrieval[n]);
  const best = report.retrieval[report.default_config] ?? configs[configs.length - 1];
  const baseline = configs[0];
  const categories = Object.keys(report.golden.by_category);
  const answers = report.answers ?? null;
  const v3 = answers?.["v3"];
  const v2 = answers ? answers[Object.keys(answers)[0]] : undefined;

  const quality = program(
    barChart(
      names,
      [
        { name: "Right chunk first (%)", values: configs.map((c) => Math.round(c.hit_at_1 * 100)) },
        { name: "Right chunk in top 5 (%)", values: configs.map((c) => Math.round(c.hit_at_5 * 100)) },
        { name: "Unanswerable caught (%)", values: configs.map((c) => Math.round((c.rejection_rate ?? 0) * 100)) },
      ],
      { xLabel: "Retrieval setup", yLabel: "Percent of questions", height: 300 },
    ),
  );

  const byCategory = program(
    barChart(
      categories,
      names.map((n) => ({
        name: n,
        values: categories.map((cat) => Math.round(((report.retrieval[n].by_category[cat]?.passed ?? 0) / (report.retrieval[n].by_category[cat]?.total || 1)) * 100)),
      })),
      { xLabel: "Question type", yLabel: "Passed (%)", height: 300 },
    ),
  );

  const rows = baseline.cases
    .map((c, i) => ({ ...c, results: names.map((n) => report.retrieval[n].cases[i]) }))
    .filter((r) => !onlyFailures || r.results.some((x) => !x.passed));

  return (
    <div className="mx-auto w-full max-w-[1040px] px-6 py-12 sm:px-12 sm:py-16">
      <ViewHeader
        title="Evaluation"
        description={
          <>
            {report.golden.total} questions with known answers: {categories.map((c) => `${report.golden.by_category[c]} ${c}`).join(", ")}. Run through every
            retrieval setup and, for answers, the full pipeline. Last run {report.generated_at}.
          </>
        }
      />

      <div className="grid grid-cols-2 gap-x-10 gap-y-10 border-y border-line-soft py-10 md:grid-cols-4">
        <Figure label="Answers correct" value={v3 ? `${v3.passed}/${v3.total}` : "–"} note={v2 && v3 ? `${v2.passed}/${v2.total} with the v2 pipeline` : "run with --answers"} />
        <Figure label="Claims verified" value={v3?.claims_checked ? `${v3.claims_supported}/${v3.claims_checked}` : "–"} note="each cited claim checked against its chunks" />
        <Figure label="Right chunk in top 5" value={pct(best.hit_at_5)} note={`${pct(baseline.hit_at_5)} before`} />
        <Figure label="Unanswerable caught" value={pct(best.rejection_rate)} note={`${pct(baseline.rejection_rate)} before`} />
      </div>

      {answers && <AnswerGrading answers={answers} />}

      <section className="mt-16">
        <SectionTitle>Retrieval quality by setup</SectionTitle>
        <Visual code={quality} framed={false} />
        <p className="mt-4 max-w-2xl text-[13px] leading-relaxed text-faint">
          {names.map((n, i) => (
            <span key={n}>
              <span className="text-muted">{n}</span>: {report.retrieval[n].label.toLowerCase()}
              {i < names.length - 1 ? ". " : "."}
            </span>
          ))}
        </p>
      </section>

      <section className="mt-16">
        <SectionTitle>Retrieval passed by question type</SectionTitle>
        <Visual code={byCategory} framed={false} />
      </section>

      <section className="mt-16">
        <SectionTitle aside={<TextButton onClick={() => setOnlyFailures((v) => !v)}>{onlyFailures ? "Show all" : "Show failures only"}</TextButton>}>
          Every retrieval question
        </SectionTitle>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-[13px]">
            <thead>
              <tr className="text-left text-[12px] text-faint">
                <th className="py-2 pr-4 font-normal">Question</th>
                <th className="py-2 pr-4 font-normal">Type</th>
                {names.map((n) => (
                  <th key={n} className="py-2 pr-3 font-normal">
                    {n}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-line-soft align-top">
                  <td className="max-w-[18rem] py-2.5 pr-4 text-ink">{r.question}</td>
                  <td className="py-2.5 pr-4 text-muted">{r.category}</td>
                  {r.results.map((x, i) => (
                    <td key={names[i]} className="py-2.5 pr-3" title={x.reason || undefined}>
                      <Result passed={x.passed} label={x.passed ? (x.rank ? `#${x.rank}` : "Pass") : "Fail"} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-[12px] text-faint">#n is the position of the first chunk that contains the answer. Hover a failure for the reason.</p>
      </section>
    </div>
  );
}
