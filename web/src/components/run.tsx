import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Check, Copy, FlaskConical, Gauge, ShieldAlert, TestTube2 } from "lucide-react";
import type { Claim, Divergence, Experiment, LedgerRow, Suite, VerdictLabel } from "@/lib/api";
import type { ExecState } from "@/lib/state";
import { Badge } from "@/components/ui/badge";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn, shortTarget } from "@/lib/utils";

/* ------------------------------------------------------------------ verdict stamp */

const VERDICT_TEXT: Record<VerdictLabel, string> = {
  consistent: "Consistent",
  needs_review: "Needs review",
  inconsistent: "Inconsistent",
  inconclusive: "Inconclusive",
};

export function Stamp({ label, className, animate = true }: { label: VerdictLabel; className?: string; animate?: boolean }) {
  const tone =
    label === "inconsistent"
      ? "text-signal border-signal"
      : label === "consistent"
        ? "text-ok border-ok"
        : label === "inconclusive"
          ? "text-muted-foreground border-muted-foreground"
          : "text-warn border-warn";
  return (
    <div
      className={cn(
        "inline-flex -rotate-[8deg] select-none flex-col items-center rounded-xl border-[3px] px-4 py-1.5 font-mono uppercase",
        tone,
        animate && "animate-stamp",
        className,
      )}
      style={{ maskImage: "radial-gradient(circle at 30% 40%, black 60%, rgba(0,0,0,.82) 100%)" }}
    >
      <span className="text-[9px] tracking-[0.3em] opacity-80">Polygraph</span>
      <span className="text-[19px] font-medium leading-tight tracking-[0.14em]">{VERDICT_TEXT[label]}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ two-pen trace */

function seeded(n: number) {
  const x = Math.sin(n * 91.7 + 13.3) * 43758.5453;
  return x - Math.floor(x);
}

/** Chart-paper strip with one pen per universe. Every probed input is a step; divergences pull pen B away. */
export function Trace({ order, execs, height = 150 }: { order: string[]; execs: Record<string, ExecState>; height?: number }) {
  const segments = useMemo(() => {
    const out: { id: string; target: string; steps: { div: boolean; kind?: string }[] }[] = [];
    for (const id of order) {
      const ex = execs[id];
      if (!ex || ex.error || !ex.cases) continue;
      const divs = new Map(ex.timeline.map((t) => [t.i, t.kind]));
      const steps = Array.from({ length: ex.cases + ex.flaky }, (_, i) => ({ div: divs.has(i), kind: divs.get(i) }));
      out.push({ id, target: ex.target, steps });
    }
    return out;
  }, [order, execs]);

  const total = segments.reduce((n, s) => n + s.steps.length, 0);
  const W = 1000;
  const mid = height / 2;
  const stepW = total ? W / Math.max(total, 40) : 0;

  let x = 0;
  let k = 0;
  const pa: string[] = [];
  const pb: string[] = [];
  const marks: { x: number; y: number; id: string }[] = [];
  const bounds: { x: number; id: string; target: string }[] = [];
  for (const seg of segments) {
    bounds.push({ x, id: seg.id, target: seg.target });
    for (const st of seg.steps) {
      const jitter = (seeded(k) - 0.5) * 10 + Math.sin(k / 3) * 4;
      const ya = mid - 14 + jitter;
      const yb = st.div ? mid + 14 + jitter + (seeded(k + 5) > 0.5 ? 1 : -1) * (26 + seeded(k + 9) * 22) : mid + 14 + jitter;
      pa.push(`${pa.length ? "L" : "M"}${x.toFixed(1)},${ya.toFixed(1)}`);
      pb.push(`${pb.length ? "L" : "M"}${x.toFixed(1)},${yb.toFixed(1)}`);
      if (st.div) marks.push({ x, y: yb, id: seg.id });
      x += stepW;
      k++;
    }
  }

  return (
    <div className="relative overflow-hidden rounded-2xl border bg-background paper-grid">
      <div className="absolute left-4 top-3 z-10 flex items-center gap-4 font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <i className="h-[3px] w-4 rounded bg-ua" /> Universe A · base
        </span>
        <span className="flex items-center gap-1.5">
          <i className="h-[3px] w-4 rounded bg-ub" /> Universe B · PR
        </span>
      </div>
      <div className="absolute right-4 top-3 z-10 font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted-foreground">
        {total} inputs · {marks.length} diverged
      </div>
      <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className="block w-full" style={{ height }}>
        {bounds.map((b) => (
          <g key={b.id}>
            <line x1={b.x} x2={b.x} y1={22} y2={height} stroke="hsl(var(--border))" strokeDasharray="2 4" />
            <text x={b.x + 6} y={height - 8} className="fill-muted-foreground font-mono" fontSize="10">
              {b.id} {shortTarget(b.target)}
            </text>
          </g>
        ))}
        <motion.path
          key={`a-${total}`}
          d={pa.join(" ")}
          fill="none"
          stroke="hsl(var(--ua))"
          strokeWidth={1.6}
          vectorEffect="non-scaling-stroke"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.9, ease: "easeOut" }}
        />
        <motion.path
          key={`b-${total}`}
          d={pb.join(" ")}
          fill="none"
          stroke="hsl(var(--ub))"
          strokeWidth={1.8}
          vectorEffect="non-scaling-stroke"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1.1, ease: "easeOut" }}
        />
        {marks.map((m, i) => (
          <circle key={i} cx={m.x} cy={m.y} r={3.2} fill="hsl(var(--signal))">
            <animate attributeName="r" values="3;5;3" dur="1.8s" repeatCount="indefinite" begin={`${(i % 7) * 0.2}s`} />
          </circle>
        ))}
        {!total && (
          <text x={W / 2} y={mid + 4} textAnchor="middle" className="fill-muted-foreground font-mono" fontSize="12">
            waiting for the first probe to run in both universes
          </text>
        )}
      </svg>
    </div>
  );
}

/* ------------------------------------------------------------------ python highlighting */

const KW = new Set(
  "def return yield if elif else for while in not and or is None True False import from as class with try except finally raise lambda pass break continue global nonlocal assert del async await".split(" "),
);

export function Code({ code, className }: { code: string; className?: string }) {
  const html = useMemo(() => {
    const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const re = /(#[^\n]*)|("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')|(\b\d+(?:\.\d+)?\b)|(\b[A-Za-z_]\w*\b)/g;
    let out = "";
    let last = 0;
    for (const m of code.matchAll(re)) {
      out += esc(code.slice(last, m.index));
      const [tok, com, str, num, word] = m;
      if (com) out += `<span class="tok-com">${esc(tok)}</span>`;
      else if (str) out += `<span class="tok-str">${esc(tok)}</span>`;
      else if (num) out += `<span class="tok-num">${tok}</span>`;
      else if (word && KW.has(word)) out += `<span class="tok-kw">${tok}</span>`;
      else if (word && code[(m.index ?? 0) + tok.length] === "(") out += `<span class="tok-fn">${tok}</span>`;
      else out += esc(tok);
      last = (m.index ?? 0) + tok.length;
    }
    return out + esc(code.slice(last));
  }, [code]);
  return (
    <pre className={cn("code max-h-[460px] overflow-auto rounded-xl border bg-background p-4", className)}>
      <code dangerouslySetInnerHTML={{ __html: html }} />
    </pre>
  );
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1400);
        });
      }}
      className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] transition hover:bg-accent"
    >
      {done ? <Check className="h-3.5 w-3.5 text-ok" /> : <Copy className="h-3.5 w-3.5" />}
      {done ? "Copied" : label}
    </button>
  );
}

/* ------------------------------------------------------------------ claim ledger */

export function ClaimLedger({
  claims,
  ledger,
  onEvidence,
}: {
  claims: Claim[];
  ledger: LedgerRow[];
  onEvidence?: (id: string) => void;
}) {
  const rows = new Map(ledger.map((l) => [l.claim, l]));
  return (
    <div className="divide-y overflow-hidden rounded-2xl border bg-card">
      {claims.map((c, i) => {
        const row = rows.get(c.id);
        const status = row?.status;
        return (
          <motion.div
            key={c.id}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="grid gap-3 p-5 transition-colors hover:bg-background/60 md:grid-cols-[56px_1fr_150px]"
          >
            <div className="font-mono text-sm text-muted-foreground">{c.id}</div>
            <div className="min-w-0">
              <div className="text-[15px] font-medium leading-snug">
                {c.statement}
                {c.implicit && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="ml-2 cursor-help align-middle font-mono text-[10px] uppercase tracking-widest text-muted-foreground underline decoration-dotted">
                        implied
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      The author never said this outright, but a reviewer would assume it from how the PR is labelled.
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
              {c.quote && (
                <div className="mt-1.5 truncate font-serif text-[15px] italic text-muted-foreground">“{c.quote}”</div>
              )}
              {row?.rationale && <p className="mt-2 text-[13.5px] leading-relaxed text-muted-foreground">{row.rationale}</p>}
              {!!row?.evidence?.length && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {row.evidence.map((ev) => (
                    <button
                      key={ev}
                      onClick={() => onEvidence?.(ev)}
                      className="rounded-full border px-2 py-0.5 font-mono text-[11px] transition hover:border-signal hover:text-signal"
                    >
                      {ev}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="md:text-right">
              {status ? (
                <Badge variant={status}>{status === "untestable" ? "not testable" : status}</Badge>
              ) : (
                <Badge variant="muted" className="animate-pulse2">
                  pending
                </Badge>
              )}
            </div>
          </motion.div>
        );
      })}
      {!claims.length && <div className="p-6 text-sm text-muted-foreground">Reading the pull request…</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ divergences */

const SEV_TONE: Record<string, string> = {
  critical: "bg-signal text-white",
  high: "bg-signal/15 text-signal",
  medium: "bg-warn/15 text-warn",
  low: "bg-muted text-muted-foreground",
};

export function DivergenceCard({ d, experiment, highlight }: { d: Divergence; experiment?: Experiment; highlight?: boolean }) {
  const [more, setMore] = useState(false);
  const declared = !!d.declared_by;
  const ex = d.examples[0];
  return (
    <motion.article
      id={`div-${d.id}`}
      layout
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "group relative overflow-hidden rounded-2xl border bg-card p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-lift",
        highlight && "ring-2 ring-signal",
      )}
    >
      <div
        className={cn(
          "absolute inset-y-0 left-0 w-1",
          declared ? "bg-ok" : d.severity === "high" || d.severity === "critical" ? "bg-signal" : "bg-warn",
        )}
      />
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-muted-foreground">{d.id}</span>
        {declared ? (
          <Badge variant="confirmed">declared by {d.declared_by}</Badge>
        ) : (
          <Badge variant="contradicted">
            <ShieldAlert className="h-3 w-3" /> undeclared
          </Badge>
        )}
        <span className={cn("rounded-full px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-widest", SEV_TONE[d.severity] || SEV_TONE.medium)}>
          {d.severity}
        </span>
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">
          {d.count}/{d.total} inputs · {shortTarget(d.target)}
        </span>
      </div>
      <h4 className="mt-3 font-serif text-[26px] leading-tight">{d.explanation?.title || d.kind.replace(/_/g, " ")}</h4>
      {d.explanation?.summary && <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-muted-foreground">{d.explanation.summary}</p>}

      {ex && (
        <div className="mt-5 overflow-hidden rounded-xl border bg-background">
          <div className="grid border-b font-mono text-[11.5px] md:grid-cols-[1fr]">
            <div className="flex items-baseline gap-3 px-4 py-2.5">
              <span className="w-12 shrink-0 text-[10px] uppercase tracking-widest text-muted-foreground">input</span>
              <span className="break-all">{ex.case}</span>
            </div>
          </div>
          <div className="grid font-mono text-[12px] md:grid-cols-2">
            <div className="border-b px-4 py-3 md:border-b-0 md:border-r">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-ua">
                <i className="h-1.5 w-1.5 rounded-full bg-ua" /> before · A
              </div>
              <div className="break-all">{ex.a}</div>
            </div>
            <div className="px-4 py-3">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-ub">
                <i className="h-1.5 w-1.5 rounded-full bg-ub" /> after · B
              </div>
              <div className="break-all">{ex.b}</div>
            </div>
          </div>
        </div>
      )}

      {d.rationale && <p className="mt-4 text-[13px] leading-relaxed text-muted-foreground">{d.rationale}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {d.examples.length > 1 && (
          <button onClick={() => setMore((v) => !v)} className="rounded-full border px-3 py-1 text-[12px] transition hover:bg-accent">
            {more ? "Hide" : `${d.examples.length - 1} more witnesses`}
          </button>
        )}
        {experiment?.code && <ProbePeek experiment={experiment} />}
      </div>
      {more && (
        <div className="mt-3 space-y-2">
          {d.examples.slice(1).map((x, i) => (
            <div key={i} className="grid gap-2 rounded-xl border bg-background p-3 font-mono text-[11.5px] md:grid-cols-3">
              <span className="break-all text-muted-foreground">{x.case}</span>
              <span className="break-all text-ua">{x.a}</span>
              <span className="break-all text-ub">{x.b}</span>
            </div>
          ))}
        </div>
      )}
    </motion.article>
  );
}

function ProbePeek({ experiment }: { experiment: Experiment }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen((v) => !v)} className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[12px] transition hover:bg-accent">
        <FlaskConical className="h-3.5 w-3.5" /> {open ? "Hide probe" : `Probe ${experiment.id}`}
      </button>
      {open && <Code code={experiment.code} className="mt-3 w-full basis-full" />}
    </>
  );
}

/* ------------------------------------------------------------------ experiments */

export function Experiments({ order, experiments, execs }: { order: string[]; experiments: Record<string, Experiment>; execs: Record<string, ExecState> }) {
  return (
    <Accordion type="multiple" className="rounded-2xl border bg-card px-5">
      {order.map((id) => {
        const e = experiments[id];
        if (!e) return null;
        const ex = execs[id];
        const st = e.stats || (ex ? { cases: ex.cases, diverge: ex.diverge, flaky: ex.flaky } : null);
        return (
          <AccordionItem key={id} value={id}>
            <AccordionTrigger>
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-mono text-xs text-muted-foreground">{id}</span>
                <span className="truncate font-mono text-[13.5px]">{e.target}</span>
                <Badge variant="outline">{e.mode}</Badge>
                {e.round > 1 && <Badge variant="unverified">follow-up</Badge>}
                {e.repaired && <Badge variant="muted">repaired</Badge>}
                <span className="ml-auto font-mono text-[11.5px] text-muted-foreground">
                  {e.error ? <span className="text-signal">failed</span> : st ? `${st.cases} inputs · ${st.diverge} diverged` : "running"}
                </span>
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
                <div className="space-y-4 text-[14px]">
                  <div>
                    <div className="eyebrow mb-1">Focus</div>
                    <p className="leading-relaxed">{e.focus}</p>
                  </div>
                  {!!e.hypotheses.length && (
                    <div>
                      <div className="eyebrow mb-1">Hypotheses</div>
                      <ul className="space-y-1.5 text-muted-foreground">
                        {e.hypotheses.map((h, i) => (
                          <li key={i} className="flex gap-2">
                            <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-signal" />
                            {h}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {e.stats?.speed && (
                    <div className="flex items-center gap-2 rounded-xl border bg-background p-3 font-mono text-[12px]">
                      <Gauge className="h-4 w-4 text-muted-foreground" />
                      B takes {e.stats.speed.ratio}x the time of A over {e.stats.speed.inputs} inputs
                    </div>
                  )}
                  {e.error && <p className="text-[13px] text-signal">{e.error}</p>}
                </div>
                {e.code ? <Code code={e.code} /> : <div className="text-sm text-muted-foreground">Writing probe…</div>}
              </div>
            </AccordionContent>
          </AccordionItem>
        );
      })}
    </Accordion>
  );
}

/* ------------------------------------------------------------------ suites */

export function SuiteStrip({ suites }: { suites: Record<string, Suite> }) {
  const labels = ["A", "B"].filter((l) => suites[l]);
  if (!labels.length) return null;
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {labels.map((l) => {
        const s = suites[l];
        const green = s.ran && !s.failed && !s.errors;
        return (
          <div key={l} className="flex items-center gap-3 rounded-2xl border bg-card p-4">
            <TestTube2 className={cn("h-5 w-5", green ? "text-ok" : "text-signal")} />
            <div className="min-w-0">
              <div className="eyebrow">Project tests · universe {l}</div>
              <div className="truncate font-mono text-[13px]">{s.summary || s.error || "no result"}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
