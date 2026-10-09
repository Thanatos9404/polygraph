import { useEffect, useMemo, useReducer, useState } from "react";
import { motion } from "framer-motion";
import { ArrowLeft, Check, Download, ExternalLink, FileCode2, GitBranch, Loader2, Radio, ShieldAlert } from "lucide-react";
import { api, downloadText, type Health } from "@/lib/api";
import { initial, reduce, STAGES } from "@/lib/state";
import { Link } from "@/lib/router";
import { ClaimLedger, Code, CopyButton, DivergenceCard, Experiments, Stamp, SuiteStrip, Trace } from "@/components/run";


import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, money } from "@/lib/utils";

export default function RunPage({ id, speed, health }: { id: string; speed: number; health: Health | null }) {
  const [s, dispatch] = useReducer(reduce, initial);
  const [ended, setEnded] = useState(false);
  const [tab, setTab] = useState("overview");
  const [focus, setFocus] = useState<string | null>(null);

  useEffect(() => {
    const stop = api.stream(id, speed, dispatch, () => setEnded(true));
    return stop;
  }, [id, speed]);

  const undeclared = s.divergences.filter((d) => !d.declared_by);
  const declared = s.divergences.filter((d) => d.declared_by);
  const running = !s.done && !ended;
  const counts = s.verdict?.counts;
  const elapsed = s.lastAt && s.startedAt ? s.lastAt - s.startedAt : 0;

  function jump(divId: string) {
    setTab("divergences");
    setFocus(divId);
    setTimeout(() => document.getElementById(`div-${divId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 120);
  }

  const totalInputs = useMemo(() => Object.values(s.execs).reduce((n, e) => n + e.cases, 0), [s.execs]);
  const totalDiv = useMemo(() => Object.values(s.execs).reduce((n, e) => n + e.diverge, 0), [s.execs]);

  return (
    <div className="container pb-10 pt-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/#cases" className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] transition hover:bg-accent">
          <ArrowLeft className="h-3.5 w-3.5" /> Case files
        </Link>
        <span className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          {running ? (
            <>
              <Radio className="h-3.5 w-3.5 animate-pulse2 text-signal" /> {speed > 1 ? `replaying at ${speed}x` : "live"}
            </>
          ) : (
            <>
              <Check className="h-3.5 w-3.5 text-ok" /> examination complete
            </>
          )}
        </span>
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">run {id}</span>
      </div>

      {/* ------------------------------------------------ header */}
      <header className="relative mt-8 grid gap-8 md:grid-cols-[1fr_auto]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 font-mono text-[12px] text-muted-foreground">
            <span>{s.subject?.repo ?? "loading"}</span>
            {s.subject && (
              <>
                <span className="opacity-40">/</span>
                <span className="inline-flex items-center gap-1">
                  <GitBranch className="h-3.5 w-3.5" /> {s.subject.base_ref} ← {s.subject.head_ref}
                </span>
                {s.subject.author && (
                  <>
                    <span className="opacity-40">/</span>
                    <span>{s.subject.author}</span>
                  </>
                )}
                {s.subject.url && (
                  <a href={s.subject.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-foreground">
                    open PR <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </>
            )}
          </div>
          <h1 className="display mt-3 max-w-4xl text-[clamp(32px,4.6vw,60px)]">{s.subject?.title ?? "Opening the case file"}</h1>
          {s.verdict?.headline ? (
            <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-4 max-w-3xl text-[17px] leading-relaxed">
              {s.verdict.headline}
            </motion.p>
          ) : (
            <p className="mt-4 max-w-3xl text-[16px] text-muted-foreground">
              {s.subject?.body?.split("\n")[0] || "Waiting for the first events"}
            </p>
          )}
        </div>
        <div className="flex items-start justify-end md:min-w-[220px]">
          {s.verdict && s.final ? (
            <Stamp label={s.verdict.label} className="scale-125 md:mt-6" />
          ) : (
            <div className="flex items-center gap-2 rounded-full border px-4 py-2 font-mono text-[12px] text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> examining
            </div>
          )}
        </div>
      </header>

      {/* ------------------------------------------------ live strip */}
      <div className="mt-8">
        <Trace order={s.order} execs={s.execs} height={170} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        {[
          ["Claims", s.claims.length],
          ["Inputs run", counts?.cases ?? totalInputs],
          ["Diverged", counts?.diverging_cases ?? totalDiv],
          ["Undeclared", undeclared.length],
          ["Token Factory", money(s.cost, 4)],
        ].map(([k, v]) => (
          <div key={k as string} className="rounded-2xl border bg-card px-4 py-3">
            <div className="eyebrow">{k}</div>
            <motion.div key={String(v)} initial={{ y: 6, opacity: 0.4 }} animate={{ y: 0, opacity: 1 }} className={cn("mt-1 font-serif text-[30px] leading-none", k === "Undeclared" && Number(v) > 0 && "text-signal")}>
              {v}
            </motion.div>
          </div>
        ))}
      </div>

      {s.error && (
        <div className="mt-6 flex items-start gap-3 rounded-2xl border border-signal/40 bg-signal/10 p-4 text-[14px] text-signal">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" /> {s.error}
        </div>
      )}

      {/* ------------------------------------------------ body */}
      <div className="mt-10 grid gap-8 lg:grid-cols-[1fr_300px]">
        <div className="min-w-0">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="overview">Ledger</TabsTrigger>
              <TabsTrigger value="divergences">
                Divergences
                {!!s.divergences.length && <span className="rounded-full bg-signal/15 px-1.5 font-mono text-[10px] text-signal">{s.divergences.length}</span>}
              </TabsTrigger>
              <TabsTrigger value="experiments">Experiments</TabsTrigger>
              <TabsTrigger value="diff">Diff</TabsTrigger>
              <TabsTrigger value="report">Report</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="space-y-8">
              {s.verdict?.summary && <p className="max-w-3xl text-[15.5px] leading-relaxed text-muted-foreground">{s.verdict.summary}</p>}
              <section>
                <SectionTitle title="Claim ledger" note="What the pull request says, checked against what the code does" />
                <ClaimLedger claims={s.claims} ledger={s.ledger} onEvidence={jump} />
              </section>
              <SuiteStrip suites={s.suites} />
              {s.verdict?.speed && (
                <div className="rounded-2xl border bg-card p-4 font-mono text-[13px]">
                  Timing across {s.verdict.speed.inputs} agreeing inputs: B takes {s.verdict.speed.ratio}x the time of A (median{" "}
                  {s.verdict.speed.a_median_us}µs to {s.verdict.speed.b_median_us}µs).
                </div>
              )}
              {s.result?.baseline && <ControlArm b={s.result.baseline} found={undeclared.length} />}
              {!!undeclared.length && (
                <section>
                  <SectionTitle title="Undeclared behavior changes" note="Observed in experiments, mentioned nowhere in the PR" hot />
                  <div className="space-y-4">
                    {undeclared.map((d) => (
                      <DivergenceCard key={d.id} d={d} experiment={s.experiments[d.probe_id]} />
                    ))}
                  </div>
                </section>
              )}
            </TabsContent>

            <TabsContent value="divergences" className="space-y-4">
              {[...undeclared, ...declared].map((d) => (
                <DivergenceCard key={d.id} d={d} experiment={s.experiments[d.probe_id]} highlight={focus === d.id} />
              ))}
              {!s.divergences.length && <Empty text={running ? "No divergences yet" : "Universe A and B agreed on every probed input"} />}
            </TabsContent>

            <TabsContent value="experiments">
              {s.order.length ? <Experiments order={s.order} experiments={s.experiments} execs={s.execs} /> : <Empty text="Designing experiments" />}
            </TabsContent>

            <TabsContent value="diff">
              {s.result?.diff?.unified ? (
                <DiffView text={s.result.diff.unified} />
              ) : (
                <Empty text={running ? "The diff appears when the run finishes" : "No diff recorded"} />
              )}
            </TabsContent>

            <TabsContent value="report" className="space-y-6">
              {s.result ? (
                <>
                  <div className="flex flex-wrap gap-2">
                    <CopyButton text={s.result.artifacts.markdown} label="Copy PR comment" />
                    <button
                      onClick={() => downloadText("test_polygraph_pinned.py", s.result!.artifacts.pinned_tests, "text/x-python")}
                      className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] transition hover:bg-accent"
                    >
                      <Download className="h-3.5 w-3.5" /> Pinned regression tests
                    </button>
                    <button
                      onClick={() => downloadText("polygraph-comment.md", s.result!.artifacts.markdown, "text/markdown")}
                      className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] transition hover:bg-accent"
                    >
                      <FileCode2 className="h-3.5 w-3.5" /> Markdown file
                    </button>
                  </div>
                  <Code code={s.result.artifacts.markdown} className="max-h-[600px] whitespace-pre-wrap" />
                </>
              ) : (
                <Empty text="The report is assembled when the verdict is in" />
              )}
            </TabsContent>
          </Tabs>
        </div>

        {/* ------------------------------------------------ aside */}
        <aside className="space-y-4 lg:sticky lg:top-24 lg:h-fit">
          <div className="rounded-3xl border bg-card p-5">
            <div className="eyebrow mb-4">Pipeline</div>
            <ol className="space-y-3">
              {STAGES.map((st) => {
                const v = s.stages[st.key];
                const state = v?.state ?? "idle";
                return (
                  <li key={st.key} className="flex items-start gap-3">
                    <span
                      className={cn(
                        "mt-1 grid h-4 w-4 shrink-0 place-items-center rounded-full border transition-colors",
                        state === "done" && "border-ok bg-ok text-white",
                        state === "running" && "border-signal",
                      )}
                    >
                      {state === "done" && <Check className="h-2.5 w-2.5" />}
                      {state === "running" && <span className="h-1.5 w-1.5 animate-ping rounded-full bg-signal" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className={cn("text-[13.5px]", state === "idle" && "text-muted-foreground")}>{st.label}</div>
                      <div className="truncate font-mono text-[10.5px] text-muted-foreground">
                        {v?.model || st.note}
                        {v?.seconds != null && ` · ${v.seconds}s`}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>

          <div className="rounded-3xl border bg-card p-5">
            <div className="eyebrow mb-3">Universes</div>
            {["A", "B"].map((l) => {
              const u = s.universes[l];
              return (
                <div key={l} className="flex items-center justify-between border-b py-2 text-[13px] last:border-0">
                  <span className="flex items-center gap-2">
                    <i className={cn("h-2 w-2 rounded-full", l === "A" ? "bg-ua" : "bg-ub")} />
                    {l === "A" ? "A · base" : "B · pull request"}
                  </span>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {u ? (u.state === "ready" ? `${u.backend}${u.python === "venv" ? " · own venv" : ""}` : "building") : "pending"}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="rounded-3xl border bg-card p-5">
            <div className="flex items-baseline justify-between">
              <div className="eyebrow">Nemotron calls</div>
              <div className="font-serif text-2xl">{money(s.cost, 4)}</div>
            </div>
            <ModelBars calls={s.calls} />
            {health && (
              <div className="mt-4 border-t pt-3 font-mono text-[10.5px] leading-relaxed text-muted-foreground">
                Spending caps: {money(health.budget.run_cap, 2)} per run, {money(health.budget.daily_cap, 2)} per day.
              </div>
            )}
          </div>

          {!!s.research.length && (
            <div className="rounded-3xl border bg-card p-5">
              <div className="eyebrow mb-3">Research · Tavily</div>
              <div className="space-y-3 text-[12.5px]">
                {s.research.map((r, i) => (
                  <div key={i}>
                    {r.kind === "dependency" ? (
                      <>
                        <div className="font-medium">
                          {r.package} {r.before} → {r.after}
                        </div>
                        {r.answer && <p className="mt-1 line-clamp-4 text-muted-foreground">{r.answer}</p>}
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {r.sources?.slice(0, 3).map((src) => (
                            <a key={src.url} href={src.url} target="_blank" rel="noreferrer" className="max-w-full truncate rounded-full border px-2 py-0.5 font-mono text-[10px] hover:text-signal">
                              {new URL(src.url).hostname}
                            </a>
                          ))}
                        </div>
                      </>
                    ) : (
                      r.pages?.map((p) => (
                        <a key={p.url} href={p.url} target="_blank" rel="noreferrer" className="block truncate font-mono text-[10.5px] hover:text-signal">
                          {p.url}
                        </a>
                      ))
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {elapsed > 0 && (
            <div className="px-2 font-mono text-[10.5px] text-muted-foreground">
              {Math.round(s.result?.duration ?? elapsed)}s{s.executor && ` · ${s.executor} executor`}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function ControlArm({ b, found }: { b: NonNullable<import("@/lib/api").Result["baseline"]>; found: number }) {
  return (
    <section className="rounded-3xl border bg-card p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-serif text-[26px] leading-none">Control arm: reading the diff</h2>
        <span className="font-mono text-[11px] text-muted-foreground">Nemotron 3 Ultra · {money(b.cost, 4)}</span>
      </div>
      <p className="mt-3 text-[14.5px] leading-relaxed text-muted-foreground">{b.review}</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Stat k="verdict" v={b.approve ? "approve" : "changes"} />
        <Stat k="predictions executed" v={`${b.real}/${b.executable} real`} />
        <Stat k="undeclared found by running" v={String(found)} hot={found > b.real} />
      </div>
      {!!b.predictions.length && (
        <ul className="mt-4 space-y-2">
          {b.predictions.map((p, i) => (
            <li key={i} className="grid gap-1 rounded-xl border bg-background p-3 text-[13px] md:grid-cols-[18px_1fr]">
              <span className={cn("mt-0.5 font-mono", p.real ? "text-ok" : p.real === false ? "text-signal" : "text-muted-foreground")}>
                {p.real ? "✓" : p.real === false ? "✗" : "?"}
              </span>
              <span>
                {p.description}
                <span className="mt-1 block font-mono text-[11.5px] text-muted-foreground">
                  {p.call} → observed {p.observed_before} then {p.observed_after}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Stat({ k, v, hot }: { k: string; v: string; hot?: boolean }) {
  return (
    <div className="rounded-2xl border bg-background px-4 py-3">
      <div className="eyebrow">{k}</div>
      <div className={cn("mt-1 font-serif text-[24px] leading-none", hot && "text-signal")}>{v}</div>
    </div>
  );
}

function SectionTitle({ title, note, hot }: { title: string; note: string; hot?: boolean }) {
  return (
    <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
      <h2 className={cn("font-serif text-[30px] leading-none", hot && "text-signal")}>{title}</h2>
      <span className="text-[13px] text-muted-foreground">{note}</span>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="rounded-2xl border border-dashed p-10 text-center text-sm text-muted-foreground">{text}</div>;
}

function ModelBars({ calls }: { calls: { label: string; cost: number; prompt_tokens: number; completion_tokens: number }[] }) {
  const by = new Map<string, { cost: number; tokens: number; n: number }>();
  for (const c of calls) {
    const v = by.get(c.label) || { cost: 0, tokens: 0, n: 0 };
    v.cost += c.cost;
    v.tokens += c.prompt_tokens + c.completion_tokens;
    v.n += 1;
    by.set(c.label, v);
  }
  const max = Math.max(1, ...[...by.values()].map((v) => v.tokens));
  if (!by.size) return <div className="mt-3 text-[12.5px] text-muted-foreground">No calls yet</div>;
  return (
    <div className="mt-4 space-y-3">
      {[...by.entries()].map(([label, v]) => (
        <Tooltip key={label}>
          <TooltipTrigger asChild>
            <div className="cursor-default">
              <div className="flex justify-between text-[12.5px]">
                <span>{label}</span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  {v.n} calls · {money(v.cost, 4)}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                <motion.div className="h-full rounded-full bg-signal" initial={{ width: 0 }} animate={{ width: `${(v.tokens / max) * 100}%` }} />
              </div>
            </div>
          </TooltipTrigger>
          <TooltipContent>{v.tokens.toLocaleString()} tokens</TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}

function DiffView({ text }: { text: string }) {
  const lines = text.split("\n").slice(0, 1500);
  return (
    <pre className="code max-h-[640px] overflow-auto rounded-2xl border bg-background py-3">
      {lines.map((l, i) => (
        <div
          key={i}
          className={cn(
            "px-4",
            l.startsWith("+++") || l.startsWith("---")
              ? "font-medium text-foreground"
              : l.startsWith("+")
                ? "bg-ok/10 text-ok"
                : l.startsWith("-")
                  ? "bg-signal/10 text-signal"
                  : l.startsWith("@@")
                    ? "text-ua"
                    : "text-muted-foreground",
          )}
        >
          {l || " "}
        </div>
      ))}
    </pre>
  );
}

