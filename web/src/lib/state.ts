import type {
  Claim, Divergence, Experiment, LedgerRow, ResearchNote, Result, StreamEvent, Subject, Suite, Verdict,
} from "./api";

export const STAGES: { key: string; label: string; note: string }[] = [
  { key: "ingest", label: "Ingest", note: "Static diff and call graph" },
  { key: "claims", label: "Claim ledger", note: "What the PR says it does" },
  { key: "research", label: "Research", note: "Changelogs and linked pages" },
  { key: "plan", label: "Experiment plan", note: "Targets and hypotheses" },
  { key: "probes", label: "Probe synthesis", note: "Executable experiments" },
  { key: "execute", label: "Twin execution", note: "Same inputs, two universes" },
  { key: "calibrate", label: "Calibration", note: "Base run twice to drop noise" },
  { key: "compare", label: "Divergence mining", note: "Cluster and explain" },
  { key: "verdict", label: "Verdict", note: "Claims against evidence" },
];

export interface StageState {
  state: "idle" | "running" | "done";
  model?: string;
  seconds?: number;
  info?: Record<string, any>;
}

export interface ExecState {
  cases: number;
  agree: number;
  diverge: number;
  flaky: number;
  timeline: { i: number; kind: string }[];
  error: string | null;
  target: string;
}

export interface ModelCall {
  label: string;
  purpose: string;
  cost: number;
  prompt_tokens: number;
  completion_tokens: number;
  seconds: number;
}

export interface RunState {
  subject: Subject | null;
  executor: string;
  roster: Record<string, { id: string; label: string; role: string }>;
  stages: Record<string, StageState>;
  universes: Record<string, Record<string, any>>;
  claims: Claim[];
  research: ResearchNote[];
  experiments: Record<string, Experiment>;
  order: string[];
  execs: Record<string, ExecState>;
  repairs: string[];
  suites: Record<string, Suite>;
  calls: ModelCall[];
  cost: number;
  divergences: Divergence[];
  ledger: LedgerRow[];
  verdict: Verdict | null;
  final: boolean;
  logs: string[];
  ingest: Record<string, any> | null;
  result: Result | null;
  error: string | null;
  done: boolean;
  startedAt: number | null;
  lastAt: number | null;
}

export const initial: RunState = {
  subject: null,
  executor: "",
  roster: {},
  stages: {},
  universes: {},
  claims: [],
  research: [],
  experiments: {},
  order: [],
  execs: {},
  repairs: [],
  suites: {},
  calls: [],
  cost: 0,
  divergences: [],
  ledger: [],
  verdict: null,
  final: false,
  logs: [],
  ingest: null,
  result: null,
  error: null,
  done: false,
  startedAt: null,
  lastAt: null,
};

export function reduce(s: RunState, ev: StreamEvent): RunState {
  const d = ev.data;
  const next: RunState = { ...s, lastAt: ev.ts, startedAt: s.startedAt ?? ev.ts };
  switch (ev.type) {
    case "run":
      next.subject = d.subject;
      next.executor = d.executor;
      next.roster = d.roster;
      break;
    case "stage": {
      const prev = s.stages[d.key] || { state: "idle" };
      next.stages = {
        ...s.stages,
        [d.key]:
          d.state === "start"
            ? { ...prev, state: "running", model: d.model || d.provider || d.executor }
            : { ...prev, state: "done", seconds: d.seconds, info: d },
      };
      if (d.key === "ingest" && d.state === "end") next.ingest = d;
      break;
    }
    case "universe":
      next.universes = { ...s.universes, [d.label]: { ...(s.universes[d.label] || {}), ...d } };
      break;
    case "claim":
      next.claims = [...s.claims.filter((c) => c.id !== d.id), d as Claim];
      break;
    case "research":
      next.research = [...s.research, d as ResearchNote];
      break;
    case "experiment":
      next.experiments = { ...s.experiments, [d.id]: d as Experiment };
      next.order = s.order.includes(d.id) ? s.order : [...s.order, d.id];
      break;
    case "probe":
      if (s.experiments[d.id]) next.experiments = { ...s.experiments, [d.id]: { ...s.experiments[d.id], code: d.code, error: d.error } };
      break;
    case "repair":
      next.repairs = [...s.repairs, d.id];
      break;
    case "execution":
      next.execs = {
        ...s.execs,
        [d.id]: {
          cases: d.cases || 0,
          agree: d.agree || 0,
          diverge: d.diverge || 0,
          flaky: d.flaky || 0,
          timeline: d.timeline || [],
          error: d.error || null,
          target: d.target,
        },
      };
      break;
    case "suite":
      if (d.state === "done") next.suites = { ...s.suites, [d.label]: d as Suite };
      break;
    case "model_call":
      next.calls = [...s.calls, d as ModelCall];
      next.cost = d.total_cost;
      break;
    case "divergence":
      next.divergences = [...s.divergences.filter((x) => x.id !== d.id), d as Divergence].sort((a, b) =>
        a.id.localeCompare(b.id, undefined, { numeric: true }),
      );
      break;
    case "ledger":
      next.ledger = d.ledger;
      next.verdict = d.verdict;
      next.divergences = d.divergences;
      next.final = d.final;
      break;
    case "log":
      next.logs = [...s.logs, d.text];
      break;
    case "done": {
      const r = d.result as Result;
      next.result = r;
      next.done = true;
      next.subject = r.subject;
      next.claims = r.claims;
      next.ledger = r.ledger;
      next.verdict = r.verdict;
      next.divergences = r.divergences;
      next.suites = r.suites || s.suites;
      next.cost = r.meter.total_cost;
      next.final = true;
      const exps: Record<string, Experiment> = {};
      for (const e of r.experiments) exps[e.id] = e;
      next.experiments = exps;
      next.order = r.experiments.map((e) => e.id);
      break;
    }
    case "error":
      next.error = d.message;
      next.done = true;
      break;
  }
  return next;
}
