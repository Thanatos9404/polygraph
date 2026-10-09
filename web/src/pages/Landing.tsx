import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useScroll, useTransform } from "framer-motion";
import {
  ArrowRight, Beaker, Binary, Bot, Braces, Check, Cpu, FileSearch, GitPullRequest, Globe, Layers, Play,
  ScanSearch, Scale, Sparkles, Split, TerminalSquare, Timer, X,
} from "lucide-react";
import Hero3D from "@/components/Hero3D";
import { CountUp, Magnetic, Parallax, Reveal, ScrollWords, TiltCard } from "@/components/effects";
import { ClaimLedger, Code, CopyButton, Stamp } from "@/components/run";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api, type Health, type RecordedRun, type Result, type ScenarioCard } from "@/lib/api";
import { navigate } from "@/lib/router";
import { saveCode, savedCode } from "@/lib/access";
import { cn, money } from "@/lib/utils";
import { REPO_URL } from "@/components/brand";

/* ================================================================== live run launcher */

type Launch = { kind: "scenario"; scenario: string } | { kind: "github"; url: string };

function useLauncher(health: Health | null) {
  const [pending, setPending] = useState<Launch | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start(l: Launch, accessCode?: string) {
    setBusy(true);
    setError(null);
    try {
      const { id } = await api.start({ ...l, access_code: accessCode });
      if (accessCode) saveCode(accessCode);
      setPending(null);
      navigate(`/run/${id}`);
    } catch (e) {
      setError((e as Error).message);
      setPending(l);
    } finally {
      setBusy(false);
    }
  }

  function launch(l: Launch) {
    if (health?.access_code_required) {
      const saved = savedCode();
      if (saved) return start(l, saved);
      setPending(l);
      return;
    }
    return start(l);
  }

  const dialog = (
    <Dialog open={!!pending} onOpenChange={(o) => !o && (setPending(null), setError(null))}>
      <DialogContent>
        <DialogTitle>Run it live</DialogTitle>
        <DialogDescription>
          Live runs spend real Token Factory credits, so this deployment asks for an access code. Judges will find it in the
          Devpost testing instructions. Recorded runs replay for free without one.
        </DialogDescription>
        <form
          className="mt-5 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (pending) start(pending, code);
          }}
        >
          <Input autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder="Access code" type="password" />
          <Button type="submit" disabled={busy || !code}>
            {busy ? "Starting" : "Start"}
          </Button>
        </form>
        {error && <p className="mt-3 text-sm text-signal">{error}</p>}
      </DialogContent>
    </Dialog>
  );

  return { launch, dialog, error, busy };
}

/* ================================================================== page */

export default function Landing({ health }: { health: Health | null }) {
  const [cases, setCases] = useState<ScenarioCard[]>([]);
  const [showcase, setShowcase] = useState<Result | null>(null);
  const [contrast, setContrast] = useState<Result | null>(null);
  const launcher = useLauncher(health);

  useEffect(() => {
    api
      .scenarios()
      .then((s) => {
        setCases(s);
        const first = s.find((c) => c.recorded)?.recorded;
        if (first) api.run(first.id).then(setShowcase).catch(() => {});
        const dep = s.find((c) => c.id === "packaging-bump")?.recorded;
        if (dep) api.run(dep.id).then(setContrast).catch(() => {});
      })
      .catch(() => setCases([]));
  }, []);

  return (
    <>
      <Hero health={health} launcher={launcher} />
      <ProductFrame result={showcase} />
      <Manifesto />
      <ReadVsRun result={contrast ?? showcase} />
      <CaseFiles cases={cases} health={health} launcher={launcher} />
      <Wild />
      <HowItWorks />
      <Models health={health} cases={cases} />
      <Compare />
      <Install />
      {launcher.dialog}
    </>
  );
}

/* ================================================================== hero */

function Hero({ health, launcher }: { health: Health | null; launcher: ReturnType<typeof useLauncher> }) {
  const [url, setUrl] = useState("");
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const canvasY = useTransform(scrollYProgress, [0, 1], ["0%", "35%"]);
  const textY = useTransform(scrollYProgress, [0, 1], ["0%", "-25%"]);
  const fade = useTransform(scrollYProgress, [0, 0.8], [1, 0]);
  const title = ["Every", "pull", "request", "makes", "claims."];

  return (
    <section ref={ref} className="relative overflow-hidden pb-10 pt-10 md:pt-16">
      <motion.div style={{ y: canvasY }} className="absolute inset-x-0 top-[46%] h-[62%] md:top-[44%]">
        <Hero3D className="h-full w-full" />
      </motion.div>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-background to-transparent" />

      <motion.div style={{ y: textY, opacity: fade }} className="container relative">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="mx-auto flex w-fit items-center gap-2 rounded-full border bg-background/70 px-3 py-1 text-[12.5px] text-muted-foreground shadow-soft backdrop-blur"
        >
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-signal" />
          </span>
          A lie detector for pull requests
        </motion.div>

        <h1 className="display mx-auto mt-7 max-w-5xl text-center text-[clamp(44px,7.2vw,108px)]">
          <span className="block">
            {title.map((w, i) => (
              <motion.span
                key={w}
                className="mr-[0.2em] inline-block"
                initial={{ opacity: 0, y: "0.5em", rotateX: -60 }}
                animate={{ opacity: 1, y: 0, rotateX: 0 }}
                transition={{ duration: 0.9, delay: 0.1 + i * 0.07, ease: [0.2, 0.9, 0.2, 1] }}
              >
                {w}
              </motion.span>
            ))}
          </span>
          <motion.span
            className="block italic text-signal"
            initial={{ opacity: 0, filter: "blur(12px)" }}
            animate={{ opacity: 1, filter: "blur(0px)" }}
            transition={{ duration: 1.1, delay: 0.6 }}
          >
            We check them by experiment.
          </motion.span>
        </h1>

        <motion.p
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.85, duration: 0.7 }}
          className="mx-auto mt-7 max-w-2xl text-center text-[17px] leading-relaxed text-muted-foreground md:text-[19px]"
        >
          Polygraph runs the code before and after a change in two isolated universes, feeds both the same inputs, and
          reports every behavior that moved. Each promise in the PR gets tested. Every change nobody mentioned gets flagged.
        </motion.p>

        <motion.form
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 1, duration: 0.7 }}
          onSubmit={(e) => {
            e.preventDefault();
            if (url.trim()) launcher.launch({ kind: "github", url: url.trim() });
          }}
          className="relative z-10 mx-auto mt-9 flex max-w-xl items-center gap-2 rounded-full border bg-background/80 p-1.5 shadow-lift backdrop-blur-xl"
        >
          <GitPullRequest className="ml-3 h-4 w-4 shrink-0 text-muted-foreground" />
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo/pull/123"
            className="min-w-0 flex-1 bg-transparent px-1 text-[15px] outline-none placeholder:text-muted-foreground"
            aria-label="Public GitHub pull request URL"
          />
          <Button type="submit" disabled={!url.trim() || launcher.busy || (health ? !health.remote_prs : false)}>
            Examine <ArrowRight />
          </Button>
        </motion.form>
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
          className="mt-4 text-center text-[13px] text-muted-foreground"
        >
          {api.isStatic && !api.canLive ? "Static demo: recorded runs replay in your browser; run live with the CLI. " : "Public Python repositories. "}
          <button
            className="underline decoration-dotted underline-offset-4 hover:text-foreground"
            onClick={() => document.getElementById("cases")?.scrollIntoView({ behavior: "smooth" })}
          >
            Or replay a recorded case file
          </button>
          {launcher.error && !launcher.busy && <span className="ml-2 text-signal">{launcher.error}</span>}
        </motion.div>
      </motion.div>
      <div className="h-[34vh] md:h-[38vh]" />
    </section>
  );
}

/* ================================================================== product frame (tilts flat on scroll) */

function ProductFrame({ result }: { result: Result | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "center center"] });
  const rotateX = useTransform(scrollYProgress, [0, 1], [32, 0]);
  const scale = useTransform(scrollYProgress, [0, 1], [0.84, 1]);
  const y = useTransform(scrollYProgress, [0, 1], [60, 0]);
  const shadow = useTransform(scrollYProgress, [0, 1], [0.15, 0.45]);
  const boxShadow = useTransform(shadow, (s) => `0 60px 120px -40px hsl(var(--shadow) / ${s})`);

  const undeclared = result?.divergences.filter((d) => !d.declared_by) ?? [];

  return (
    <section className="container relative -mt-[20vh] md:-mt-[24vh]">
      <div ref={ref} style={{ perspective: 1400 }}>
        <motion.div
          style={{ rotateX, scale, y, boxShadow, transformOrigin: "50% 0%" }}
          className="mx-auto max-w-6xl overflow-hidden rounded-[22px] border bg-card"
        >
          <div className="flex items-center gap-2 border-b bg-background/60 px-4 py-3">
            <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
            <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
            <span className="h-3 w-3 rounded-full bg-[#28c840]" />
            <div className="mx-auto flex items-center gap-2 rounded-full bg-muted px-4 py-1 font-mono text-[11.5px] text-muted-foreground">
              polygraph / {result?.subject.repo ?? "acme/slugkit"} / {result ? "report" : "loading"}
            </div>
          </div>
          {result ? (
            <div className="grid gap-6 p-5 md:grid-cols-[1.25fr_1fr] md:p-8">
              <div className="min-w-0">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="eyebrow">{result.subject.author} wants to merge into {result.subject.base_ref}</div>
                    <h3 className="mt-2 font-serif text-[28px] leading-[1.05] md:text-[34px]">{result.subject.title}</h3>
                  </div>
                  <Stamp label={result.verdict.label} className="shrink-0 scale-90" />
                </div>
                <p className="mt-4 text-[14.5px] leading-relaxed text-muted-foreground">{result.verdict.headline}</p>
                <div className="mt-5">
                  <ClaimLedger claims={result.claims.slice(0, 4)} ledger={result.ledger} />
                </div>
              </div>
              <div className="space-y-3">
                <div className="eyebrow">Undeclared changes</div>
                {undeclared.slice(0, 3).map((d) => (
                  <div key={d.id} className="rounded-2xl border bg-background p-4 transition hover:-translate-y-0.5 hover:shadow-soft">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[11px] text-muted-foreground">{d.id}</span>
                      <span className="truncate font-serif text-[19px]">{d.explanation.title}</span>
                    </div>
                    <div className="mt-2 grid gap-1 font-mono text-[11.5px]">
                      <span className="truncate text-muted-foreground">in {d.examples[0]?.case}</span>
                      <span className="truncate text-ua">A {d.examples[0]?.a}</span>
                      <span className="truncate text-ub">B {d.examples[0]?.b}</span>
                    </div>
                  </div>
                ))}
                <div className="grid grid-cols-3 gap-2 pt-1 text-center">
                  {[
                    ["inputs", result.verdict.counts.cases],
                    ["diverged", result.verdict.counts.diverging_cases],
                    ["cost", money(result.meter.total_cost, 3)],
                  ].map(([k, v]) => (
                    <div key={k as string} className="rounded-xl border bg-background py-3">
                      <div className="font-serif text-2xl">{v}</div>
                      <div className="eyebrow mt-0.5">{k}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="grid h-[420px] place-items-center text-sm text-muted-foreground">Loading a recorded case file</div>
          )}
        </motion.div>
      </div>
    </section>
  );
}

/* ================================================================== manifesto */

function Manifesto() {
  return (
    <section className="container py-28 md:py-40">
      <div className="eyebrow mb-8">Why this exists</div>
      <ScrollWords
        className="display max-w-5xl text-[clamp(32px,4.6vw,64px)] leading-[1.06]"
        text="Coding agents now open more pull requests than people can read. Review still means reading a diff, and a diff never runs. Tests stay green because they only check what someone thought to check. *Polygraph* *runs* *the* *code.*"
      />
    </section>
  );
}

/* ================================================================== read vs run switch */

function ReadVsRun({ result }: { result: Result | null }) {
  const [run, setRun] = useState(true);
  const undeclared = result?.divergences.filter((d) => !d.declared_by) ?? [];
  const suites = result?.verdict.suites ?? {};
  return (
    <section className="container">
      <div className="grid items-center gap-10 rounded-3xl border bg-card p-6 md:grid-cols-[1fr_1.3fr] md:p-12">
        <div>
          <div className="display text-[clamp(34px,4.4vw,58px)]">
            Same PR.
            <br />
            <span className="inline-flex flex-wrap items-center gap-3">
              Flip the
              <Switch checked={run} onCheckedChange={setRun} aria-label="Toggle between reading and running" />
            </span>
            <br />
            <span className={cn("transition-colors duration-500", run ? "italic text-signal" : "text-muted-foreground")}>
              {run ? "run it." : "read it."}
            </span>
          </div>
          <p className="mt-6 max-w-md text-[15.5px] leading-relaxed text-muted-foreground">
            Both sides are real output for the same pull request. On the left, Nemotron 3 Ultra reviews it by reading the
            diff. On the right, Polygraph runs both versions on the same inputs.
          </p>
          {result && (
            <p className="mt-3 max-w-md font-mono text-[12px] text-muted-foreground">case: {result.subject.title}</p>
          )}
        </div>
        <div className="relative min-h-[380px]" style={{ perspective: 1200 }}>
          <AnimatePresence mode="wait">
            {!run ? (
              <motion.div
                key="read"
                initial={{ rotateY: -90, opacity: 0 }}
                animate={{ rotateY: 0, opacity: 1 }}
                exit={{ rotateY: 90, opacity: 0 }}
                transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
                className="rounded-2xl border bg-background p-6 shadow-soft"
              >
                <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
                  <FileSearch className="h-4 w-4" /> Nemotron 3 Ultra, reading the diff
                </div>
                <div className="mt-5 space-y-3 text-[15px] leading-relaxed">
                  <p>{result?.baseline?.review ?? "Loading the recorded review"}</p>
                  {Object.keys(suites).length > 0 && (
                    <p className="font-mono text-[12.5px] text-muted-foreground">CI: {suites.B?.summary}</p>
                  )}
                </div>
                {result?.baseline && (
                  <div
                    className={cn(
                      "mt-6 flex items-center gap-2 rounded-xl px-3 py-2 text-[13px]",
                      result.baseline.approve ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn",
                    )}
                  >
                    {result.baseline.approve ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
                    {result.baseline.approve ? "Approved" : "Changes requested"} · {result.baseline.predictions.length} behavior
                    changes predicted
                  </div>
                )}
              </motion.div>
            ) : (
              <motion.div
                key="run"
                initial={{ rotateY: 90, opacity: 0 }}
                animate={{ rotateY: 0, opacity: 1 }}
                exit={{ rotateY: -90, opacity: 0 }}
                transition={{ duration: 0.45, ease: [0.4, 0, 0.2, 1] }}
                className="rounded-2xl border bg-background p-6 shadow-lift"
              >
                <div className="flex items-center justify-between gap-2 text-[13px] text-muted-foreground">
                  <span className="flex items-center gap-2">
                    <ScanSearch className="h-4 w-4" /> What running both versions gives you
                  </span>
                  {result && <Stamp label={result.verdict.label} className="scale-75" />}
                </div>
                <div className="mt-4 space-y-3">
                  {undeclared.slice(0, 3).map((d) => (
                    <div key={d.id} className="rounded-xl border p-3">
                      <div className="flex items-center gap-2 text-[14px] font-medium">
                        <X className="h-4 w-4 shrink-0 text-signal" /> {d.explanation.title}
                      </div>
                      <div className="mt-1.5 grid gap-0.5 pl-6 font-mono text-[11.5px]">
                        <span className="truncate text-muted-foreground">{d.examples[0]?.case}</span>
                        <span className="truncate">
                          <span className="text-ua">{d.examples[0]?.a}</span>
                          <span className="mx-2 text-muted-foreground">became</span>
                          <span className="text-ub">{d.examples[0]?.b}</span>
                        </span>
                      </div>
                    </div>
                  ))}
                  {!undeclared.length && <div className="text-sm text-muted-foreground">Loading evidence</div>}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}

/* ================================================================== case files */

function CaseFiles({
  cases,
  health,
  launcher,
}: {
  cases: ScenarioCard[];
  health: Health | null;
  launcher: ReturnType<typeof useLauncher>;
}) {
  return (
    <section id="cases" className="container scroll-mt-24 pt-32">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <Reveal>
          <div className="eyebrow mb-4">Case files</div>
          <h2 className="display max-w-3xl text-[clamp(40px,5.6vw,76px)]">
            Four pull requests.
            <br />
            <span className="italic text-muted-foreground">Four very different truths.</span>
          </h2>
        </Reveal>
        <Reveal delay={0.1} className="max-w-sm text-[15px] leading-relaxed text-muted-foreground">
          Each case replays a real recorded run, event by event, for free. With an access code you can run it live on
          Nemotron and watch the universes diverge in real time.
        </Reveal>
      </div>
      <div className="mt-12 grid gap-5 md:grid-cols-2">
        {cases.map((c, i) => (
          <Reveal key={c.id} delay={i * 0.08}>
            <TiltCard className="h-full">
              <article className="group relative flex h-full flex-col overflow-hidden rounded-3xl border bg-card p-7 shadow-soft transition-shadow duration-500 hover:shadow-lift">
                <div className="absolute -right-24 -top-24 h-56 w-56 rounded-full bg-signal/0 blur-3xl transition-all duration-700 group-hover:bg-signal/20" />
                <div className="flex items-center justify-between gap-3" style={{ transform: "translateZ(30px)" }}>
                  <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                    Case {String(i + 1).padStart(2, "0")} · {c.repo}
                  </span>
                  {c.recorded && <Stamp label={c.recorded.verdict} animate={false} className="scale-[0.72] origin-right" />}
                </div>
                <h3 className="mt-5 font-serif text-[30px] leading-[1.05]" style={{ transform: "translateZ(40px)" }}>
                  {c.title}
                </h3>
                <p className="mt-3 text-[14.5px] text-muted-foreground">{c.blurb}</p>
                <div className="mt-2 font-mono text-[11.5px] text-muted-foreground">by {c.author}</div>
                {c.recorded && (
                  <div className="mt-6 grid grid-cols-4 gap-2 border-t pt-5 text-center">
                    {[
                      ["claims", c.recorded.counts.claims],
                      ["contradicted", c.recorded.counts.contradicted],
                      ["undeclared", c.recorded.counts.undeclared],
                      ["inputs", c.recorded.counts.cases],
                    ].map(([k, v]) => (
                      <div key={k as string}>
                        <div className={cn("font-serif text-[28px] leading-none", k !== "inputs" && Number(v) > 0 && k !== "claims" && "text-signal")}>
                          {v}
                        </div>
                        <div className="mt-1 font-mono text-[9.5px] uppercase tracking-[0.14em] text-muted-foreground">{k}</div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="mt-auto flex flex-wrap gap-2 pt-7" style={{ transform: "translateZ(20px)" }}>
                  {c.recorded && (
                    <Magnetic>
                      <Button onClick={() => navigate(`/run/${c.recorded!.id}?speed=3`)}>
                        <Play /> Replay recorded run
                      </Button>
                    </Magnetic>
                  )}
                  <Button
                    variant="outline"
                    disabled={!health?.live || launcher.busy}
                    onClick={() => launcher.launch({ kind: "scenario", scenario: c.id })}
                  >
                    <Sparkles /> Run live
                  </Button>
                  {c.recorded && (
                    <span className="ml-auto self-center font-mono text-[11px] text-muted-foreground">
                      {money(c.recorded.cost, 3)} · {Math.round(c.recorded.duration)}s
                    </span>
                  )}
                </div>
              </article>
            </TiltCard>
          </Reveal>
        ))}
        {!cases.length && <div className="text-sm text-muted-foreground">Loading case files</div>}
      </div>
    </section>
  );
}

/* ================================================================== real merged PRs */

function Wild() {
  const [runs, setRuns] = useState<RecordedRun[]>([]);
  useEffect(() => {
    api.recorded().then((r) => setRuns(r.filter((x) => x.kind === "github"))).catch(() => {});
  }, []);
  if (!runs.length) return null;
  return (
    <section className="container pt-28">
      <Reveal>
        <div className="eyebrow mb-4">From the wild</div>
        <h2 className="display max-w-4xl text-[clamp(36px,4.6vw,64px)]">
          Real merged pull requests, <span className="italic text-muted-foreground">already reviewed by people.</span>
        </h2>
      </Reveal>
      <div className="mt-10 grid gap-5 md:grid-cols-2">
        {runs.map((r, i) => (
          <Reveal key={r.id} delay={i * 0.08}>
            <div className="group relative h-full overflow-hidden rounded-3xl border bg-card p-7 transition-all duration-500 hover:-translate-y-1 hover:shadow-lift">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
                    {r.repo} · {r.url?.split("/").pop() ? `#${r.url.split("/").pop()}` : ""} · merged
                  </div>
                  <h3 className="mt-3 font-serif text-[26px] leading-[1.1]">{r.title}</h3>
                </div>
                <Stamp label={r.verdict} animate={false} className="shrink-0 origin-top-right scale-[0.7]" />
              </div>
              <p className="mt-3 text-[14px] leading-relaxed text-muted-foreground">{r.headline}</p>
              {r.undeclared.slice(0, 1).map((u) => (
                <div key={u.case} className="mt-4 rounded-2xl border bg-background p-4 font-mono text-[12px]">
                  <div className="mb-1.5 font-sans text-[13.5px] font-medium text-signal">Undeclared: {u.title}</div>
                  <div className="truncate text-muted-foreground">input {u.case}</div>
                  <div className="truncate text-ua">before {u.a}</div>
                  <div className="truncate text-ub">after {u.b}</div>
                </div>
              ))}
              <div className="mt-6 flex flex-wrap items-center gap-2">
                <Button onClick={() => navigate(`/run/${r.id}?speed=3`)}>
                  <Play /> Replay
                </Button>
                {r.url && (
                  <Button asChild variant="outline">
                    <a href={r.url} target="_blank" rel="noreferrer">
                      <GitPullRequest /> Original PR
                    </a>
                  </Button>
                )}
                {r.baseline_approve != null && (
                  <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                    diff reader: {r.baseline_approve ? "approved" : "changes"}
                  </span>
                )}
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ================================================================== how it works (sticky) */

const STEPS = [
  { icon: GitPullRequest, model: "Static analysis", title: "Ingest", body: "Both trees are parsed. Changed functions, their public callers, and any code that leans on a bumped dependency become targets." },
  { icon: Scale, model: "Nemotron 3 Ultra", title: "Claim ledger", body: "The PR title, description, commits, and linked issues are split into separate promises, including the ones a reviewer silently assumes, like no behavior change in a refactor." },
  { icon: Globe, model: "Tavily", title: "Research", body: "When a dependency moves, Polygraph reads its changelog. When the PR links a page, it reads that too. The planner aims at what the notes say changed." },
  { icon: Braces, model: "Nemotron 3 Ultra", title: "Experiment plan", body: "With both versions of every target in context, Ultra writes falsifiable hypotheses: which inputs should behave differently, and why." },
  { icon: Binary, model: "Nemotron 3.5 Lightning", title: "Probe synthesis", body: "One executable probe per experiment, written in parallel. Probes that crash are repaired by Nemotron 3 Nano, or rewritten from scratch." },
  { icon: Split, model: "Isolated sandboxes", title: "Twin execution", body: "Every probe runs in universe A, again in A for calibration, and in B. Inputs where A disagrees with itself are thrown out as noise. The project's own tests run in both." },
  { icon: Layers, model: "Nemotron 3 Super", title: "Divergence mining", body: "Disagreements are clustered, the clearest witness is picked, and each cluster is explained in plain words with a severity." },
  { icon: Bot, model: "Nemotron 3 Ultra", title: "Verdict", body: "Each claim is confirmed, contradicted, or left unverified, and every divergence nobody declared is surfaced. Unverified claims trigger a second round of experiments." },
];

function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.6", "end 0.6"] });
  const [active, setActive] = useState(0);
  useEffect(() => scrollYProgress.on("change", (v) => setActive(Math.min(STEPS.length - 1, Math.max(0, Math.floor(v * STEPS.length))))), [scrollYProgress]);
  const bar = useTransform(scrollYProgress, [0, 1], ["0%", "100%"]);

  return (
    <section id="how" className="container scroll-mt-24 pt-36">
      <div className="grid gap-12 md:grid-cols-[0.9fr_1.1fr]">
        <div className="md:sticky md:top-28 md:h-fit">
          <div className="eyebrow mb-4">How it works</div>
          <h2 className="display text-[clamp(40px,5.2vw,72px)]">
            Eight stages.
            <br />
            <span className="italic">Four Nemotrons.</span>
          </h2>
          <p className="mt-5 max-w-md text-[15.5px] leading-relaxed text-muted-foreground">
            Each stage uses the smallest model that does the job well. Reasoning-heavy judgement goes to Ultra, volume work to
            Lightning and Nano, so a full examination costs a few cents.
          </p>
          <div className="mt-10 hidden items-end gap-5 md:flex">
            <AnimatePresence mode="popLayout">
              <motion.div
                key={active}
                initial={{ y: 40, opacity: 0, rotateX: -50 }}
                animate={{ y: 0, opacity: 1, rotateX: 0 }}
                exit={{ y: -40, opacity: 0, rotateX: 50 }}
                transition={{ duration: 0.45 }}
                className="font-serif text-[150px] leading-[0.8] text-signal"
              >
                {String(active + 1).padStart(2, "0")}
              </motion.div>
            </AnimatePresence>
            <div className="pb-3">
              <div className="font-serif text-3xl">{STEPS[active].title}</div>
              <div className="font-mono text-[12px] text-muted-foreground">{STEPS[active].model}</div>
            </div>
          </div>
        </div>
        <div ref={ref} className="relative pl-8">
          <div className="absolute left-0 top-0 h-full w-px bg-border" />
          <motion.div style={{ height: bar }} className="absolute left-0 top-0 w-px bg-signal" />
          {STEPS.map((s, i) => (
            <Reveal key={s.title} className="relative mb-6">
              <div
                className={cn(
                  "absolute -left-[37px] top-7 h-3 w-3 rounded-full border-2 transition-all duration-500",
                  i <= active ? "border-signal bg-signal" : "border-border bg-background",
                )}
              />
              <div
                className={cn(
                  "rounded-3xl border bg-card p-6 transition-all duration-500",
                  i === active ? "-translate-y-1 shadow-lift" : "opacity-70",
                )}
              >
                <div className="flex items-center gap-3">
                  <div className="grid h-10 w-10 place-items-center rounded-2xl bg-background shadow-soft">
                    <s.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="font-serif text-[24px] leading-none">{s.title}</div>
                    <div className="mt-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">{s.model}</div>
                  </div>
                </div>
                <p className="mt-4 text-[14.5px] leading-relaxed text-muted-foreground">{s.body}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ================================================================== models */

const TIER_STYLE: Record<string, string> = {
  ultra: "from-signal/25",
  super: "from-ember/20",
  lightning: "from-warn/20",
  nano: "from-ua/20",
};

function Models({ health, cases }: { health: Health | null; cases: ScenarioCard[] }) {
  const roster = health?.roster ?? {
    ultra: { id: "nvidia/Nemotron-3-Ultra-550b-a55b", label: "Nemotron 3 Ultra", role: "Claims, plan, verdict" },
    super: { id: "nvidia/nemotron-3-super-120b-a12b", label: "Nemotron 3 Super", role: "Explains divergences" },
    lightning: { id: "nvidia/Nemotron-3_5-Lightning", label: "Nemotron 3.5 Lightning", role: "Writes probes" },
    nano: { id: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", label: "Nemotron 3 Nano", role: "Repairs probes" },
  };
  const rec = cases.map((c) => c.recorded).filter(Boolean) as NonNullable<ScenarioCard["recorded"]>[];
  const avgCost = rec.length ? rec.reduce((n, r) => n + r.cost, 0) / rec.length : 0.04;
  const avgInputs = rec.length ? rec.reduce((n, r) => n + (r.counts.cases || 0), 0) / rec.length : 80;
  const avgSecs = rec.length ? rec.reduce((n, r) => n + r.duration, 0) / rec.length : 45;

  return (
    <section id="models" className="container scroll-mt-24 pt-36">
      <Reveal>
        <div className="eyebrow mb-4">Models</div>
        <h2 className="display max-w-4xl text-[clamp(40px,5.4vw,74px)]">
          Big model for judgement.
          <br />
          <span className="italic text-muted-foreground">Small models for volume.</span>
        </h2>
      </Reveal>
      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(roster).map(([tier, m], i) => (
          <Reveal key={tier} delay={i * 0.07}>
            <TiltCard max={7}>
              <div className={cn("relative h-full overflow-hidden rounded-3xl border bg-gradient-to-b to-card p-6", TIER_STYLE[tier])}>
                <Cpu className="h-5 w-5" />
                <div className="mt-8 font-serif text-[28px] leading-none">{m.label}</div>
                <div className="mt-2 truncate font-mono text-[10.5px] text-muted-foreground">{m.id}</div>
                <p className="mt-5 text-[14px] leading-relaxed text-muted-foreground">{m.role}</p>
              </div>
            </TiltCard>
          </Reveal>
        ))}
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-3">
        {[
          { icon: Beaker, v: <CountUp to={avgCost} decimals={3} prefix="$" />, k: "average cost per examined PR" },
          { icon: TerminalSquare, v: <CountUp to={avgInputs} />, k: "inputs run in each universe, on average" },
          { icon: Timer, v: <CountUp to={avgSecs} suffix="s" />, k: "from PR link to verdict, on average" },
        ].map((s, i) => (
          <Reveal key={i} delay={i * 0.06}>
            <div className="flex items-center gap-5 rounded-3xl border bg-card p-6">
              <s.icon className="h-6 w-6 text-signal" />
              <div>
                <div className="font-serif text-[46px] leading-none">{s.v}</div>
                <div className="mt-1 text-[13px] text-muted-foreground">{s.k}</div>
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ================================================================== compare (pricing-style) */

function Compare() {
  const rows = [
    ["Reads the PR description", true, true],
    ["Executes the old and new code", false, true],
    ["Finds changes nobody mentioned", false, true],
    ["Evidence you can rerun", false, true],
    ["Discards flaky noise by calibration", false, true],
    ["Measures speed claims", false, true],
    ["Hands you failing tests to commit", false, true],
  ] as const;
  return (
    <section className="container pt-36">
      <Reveal className="text-center">
        <div className="eyebrow mb-4">The difference</div>
        <h2 className="display mx-auto max-w-3xl text-[clamp(40px,5.2vw,72px)]">
          Opinion, or <span className="italic text-signal">evidence.</span>
        </h2>
      </Reveal>
      <div className="mx-auto mt-12 grid max-w-4xl gap-5 md:grid-cols-2">
        {[
          { name: "Diff-reading review", sub: "Human or model, reading text", hot: false },
          { name: "Polygraph", sub: "Experiments in two universes", hot: true },
        ].map((col, ci) => (
          <Reveal key={col.name} delay={ci * 0.1}>
            <div
              className={cn(
                "relative h-full rounded-3xl border p-7 transition-all duration-500 hover:-translate-y-1",
                col.hot ? "bg-[hsl(var(--frame))] text-white shadow-lift" : "bg-card",
              )}
            >
              {col.hot && (
                <span className="absolute right-6 top-6 rounded-full bg-signal px-3 py-1 font-mono text-[10px] uppercase tracking-[0.16em] text-white">
                  Runs the code
                </span>
              )}
              <div className="font-serif text-[34px] leading-none">{col.name}</div>
              <div className={cn("mt-2 text-[13.5px]", col.hot ? "text-white/60" : "text-muted-foreground")}>{col.sub}</div>
              <ul className="mt-8 space-y-3.5">
                {rows.map(([label, a, b]) => {
                  const ok = col.hot ? b : a;
                  return (
                    <li key={label} className={cn("flex items-center gap-3 text-[14.5px]", !ok && (col.hot ? "text-white/40" : "text-muted-foreground/70"))}>
                      {ok ? <Check className={cn("h-4 w-4", col.hot ? "text-signal" : "text-ok")} /> : <X className="h-4 w-4" />}
                      {label}
                    </li>
                  );
                })}
              </ul>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

/* ================================================================== install */

function Install() {
  const cli = useMemo(
    () => `pip install "git+${REPO_URL}"
export NEBIUS_API_KEY=...        # Token Factory key
polygraph pr https://github.com/owner/repo/pull/123`,
    [],
  );
  const action = `# .github/workflows/polygraph.yml
name: polygraph
on: pull_request
jobs:
  examine:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: Thanatos9404/polygraph@main
        with:
          nebius-api-key: \${{ secrets.NEBIUS_API_KEY }}`;
  return (
    <section id="install" className="container scroll-mt-24 pt-36">
      <div className="grid gap-10 md:grid-cols-[0.8fr_1.2fr]">
        <Reveal>
          <div className="eyebrow mb-4">Install</div>
          <h2 className="display text-[clamp(40px,5vw,68px)]">
            From your terminal,
            <br />
            <span className="italic">or on every PR.</span>
          </h2>
          <p className="mt-5 max-w-md text-[15.5px] leading-relaxed text-muted-foreground">
            The CLI exits non-zero on an inconsistent verdict, so it can gate a merge. The GitHub Action posts the claim
            ledger as a PR comment and uploads pinned regression tests for every finding.
          </p>
        </Reveal>
        <Parallax speed={0.15}>
          <div className="space-y-4">
            {[
              ["Command line", cli],
              ["GitHub Action", action],
            ].map(([label, code]) => (
              <div key={label} className="overflow-hidden rounded-3xl border bg-card shadow-soft">
                <div className="flex items-center justify-between border-b px-5 py-3">
                  <span className="eyebrow">{label}</span>
                  <CopyButton text={code} />
                </div>
                <Code code={code} className="rounded-none border-0 bg-transparent" />
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">Apache 2.0</Badge>
              <Badge variant="outline">Python 3.11+</Badge>
              <Badge variant="outline">Local or Token Factory Sandboxes</Badge>
              <Badge variant="outline">Hard spending caps</Badge>
            </div>
          </div>
        </Parallax>
      </div>
      <div className="mt-20 flex justify-center">
        <Magnetic>
          <Button size="lg" variant="signal" onClick={() => document.getElementById("cases")?.scrollIntoView({ behavior: "smooth" })}>
            Open a case file <ArrowRight />
          </Button>
        </Magnetic>
      </div>
    </section>
  );
}

