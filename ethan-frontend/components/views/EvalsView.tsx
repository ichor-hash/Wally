"use client";

import { useState } from "react";
import { EvalReport } from "@/lib/api";
import { barChart, program } from "@/lib/openui";
import { Visual } from "../Visual";
import { Figure, SectionTitle, TextButton, ViewHeader } from "../ui";

const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

function Result({ passed, rank }: { passed: boolean; rank?: number | null }) {
  return (
    <span className={`tabular inline-flex items-center gap-1.5 ${passed ? "text-ink" : "text-bad"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${passed ? "bg-ok" : "bg-bad"}`} />
      {passed ? (rank ? `#${rank}` : "Pass") : "Fail"}
    </span>
  );
}

export function EvalsView({ report, error }: { report: EvalReport | null; error: string | null }) {
  const [onlyFailures, setOnlyFailures] = useState(false);

  if (!report) {
    return (
      <div className="mx-auto w-full max-w-[960px] px-6 py-12 sm:px-12 sm:py-16">
        <ViewHeader title="Evaluation" description="How well Ethan finds the right chunk, measured on a fixed set of questions with known answers." />
        <p className="py-10 text-[14px] leading-relaxed text-muted">
          {error ?? "Loading the latest report."}
          {error && (
            <>
              {" "}
              Run <code className="rounded-[4px] bg-subtle px-1 py-0.5 text-[13px] ring-1 ring-line-soft">python evals/run_evals.py</code> in the project folder.
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
  const answers = report.answers ? Object.entries(report.answers) : [];

  const quality = program(
    barChart(
      names,
      [
        { name: "Hit@1 (%)", values: configs.map((c) => Math.round(c.hit_at_1 * 100)) },
        { name: "Hit@5 (%)", values: configs.map((c) => Math.round(c.hit_at_5 * 100)) },
        { name: "Unanswerable rejected (%)", values: configs.map((c) => Math.round((c.rejection_rate ?? 0) * 100)) },
      ],
      { xLabel: "Configuration", yLabel: "Percent of questions", height: 300 },
    ),
  );

  const byCategory = program(
    barChart(
      categories,
      names.map((n) => ({
        name: n,
        values: categories.map((cat) => Math.round((report.retrieval[n].by_category[cat].passed / report.retrieval[n].by_category[cat].total) * 100)),
      })),
      { xLabel: "Question type", yLabel: "Passed (%)", height: 300 },
    ),
  );

  const rows = baseline.cases
    .map((c, i) => ({ ...c, results: names.map((n) => report.retrieval[n].cases[i]) }))
    .filter((r) => !onlyFailures || r.results.some((x) => !x.passed));

  return (
    <div className="mx-auto w-full max-w-[960px] px-6 py-12 sm:px-12 sm:py-16">
      <ViewHeader
        title="Evaluation"
        description={
          <>
            {report.golden.total} questions with known answers, run through every retrieval configuration. A question passes when a chunk containing the
            answer is in the top {report.top_k}, or, if the documents cannot answer it, when Ethan reports weak grounding. Last run {report.generated_at}.
          </>
        }
        aside={
          <span className="flex items-center gap-2 text-[13px] text-ink">
            <span className={`h-1.5 w-1.5 rounded-full ${report.gate.passed ? "bg-ok" : "bg-bad"}`} />
            Quality gate {report.gate.passed ? "passing" : "failing"}
          </span>
        }
      />

      <div className="grid grid-cols-2 gap-x-10 gap-y-10 border-y border-line-soft py-10 md:grid-cols-4">
        <Figure label="Passed, default setup" value={`${best.passed}/${best.total}`} note={`${baseline.passed}/${baseline.total} before hybrid search`} />
        <Figure label="Right chunk first" value={pct(best.hit_at_1)} note={`${pct(baseline.hit_at_1)} before`} />
        <Figure label="Right chunk in top 5" value={pct(best.hit_at_5)} note={`${pct(baseline.hit_at_5)} before`} />
        <Figure label="Unanswerable caught" value={pct(best.rejection_rate)} note={`${pct(baseline.rejection_rate)} before`} />
      </div>

      <section className="mt-14">
        <SectionTitle>Retrieval quality by configuration</SectionTitle>
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
        <SectionTitle>Passed by question type</SectionTitle>
        <Visual code={byCategory} framed={false} />
      </section>

      {answers.length > 0 && (
        <section className="mt-16">
          <SectionTitle>Generated answers</SectionTitle>
          <p className="mb-6 max-w-2xl text-[13.5px] leading-relaxed text-muted">
            The full pipeline, graded automatically: required facts must appear, answerable questions must carry a citation, and unanswerable ones must be
            declined.
          </p>
          <div className="grid gap-x-10 gap-y-8 border-y border-line-soft py-8 sm:grid-cols-2">
            {answers.map(([name, a]) => (
              <Figure key={name} label={a.label} value={`${a.passed}/${a.total}`} note={`${a.model} · ${a.avg_prompt_tokens} prompt tokens on average`} />
            ))}
          </div>
          {answers.map(([name, a]) => {
            const failed = a.cases.filter((c) => !c.passed);
            if (!failed.length) return null;
            return (
              <div key={name} className="mt-8">
                <p className="text-[13px] text-muted">Failed with {name}</p>
                <ul className="mt-3 space-y-4">
                  {failed.map((c) => (
                    <li key={c.id} className="rounded-[12px] bg-subtle p-4 text-[13.5px] ring-1 ring-line-soft">
                      <p className="font-medium text-ink">{c.question}</p>
                      <p className="mt-1 text-bad">{c.reason}</p>
                      <p className="mt-2 line-clamp-3 text-muted">{c.answer}</p>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </section>
      )}

      <section className="mt-16">
        <SectionTitle aside={<TextButton onClick={() => setOnlyFailures((v) => !v)}>{onlyFailures ? "Show all" : "Show failures only"}</TextButton>}>
          Every question
        </SectionTitle>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-[13px]">
            <thead>
              <tr className="text-left text-[12px] text-faint">
                <th className="py-2 pr-4 font-normal">Question</th>
                <th className="py-2 pr-4 font-normal">Type</th>
                {names.map((n) => (
                  <th key={n} className="py-2 pr-4 font-normal whitespace-nowrap">
                    {n}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-line-soft align-top">
                  <td className="max-w-[20rem] py-2.5 pr-4 text-ink">{r.question}</td>
                  <td className="py-2.5 pr-4 text-muted">{r.category}</td>
                  {r.results.map((x, i) => (
                    <td key={names[i]} className="py-2.5 pr-4" title={x.reason || undefined}>
                      <Result passed={x.passed} rank={x.rank} />
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
