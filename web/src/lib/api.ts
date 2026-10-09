export type Status = "confirmed" | "contradicted" | "unverified" | "untestable";
export type VerdictLabel = "consistent" | "needs_review" | "inconsistent" | "inconclusive";

export interface Claim {
  id: string;
  statement: string;
  quote: string;
  kind: string;
  implicit: boolean;
  testable: boolean;
}

export interface LedgerRow {
  claim: string;
  status: Status;
  evidence: string[];
  rationale: string;
}

export interface Example {
  case: string;
  a: string;
  b: string;
  index: string;
}

export interface Divergence {
  id: string;
  probe_id: string;
  target: string;
  kind: string;
  count: number;
  total: number;
  examples: Example[];
  explanation: {
    title?: string;
    before?: string;
    after?: string;
    summary?: string;
    category?: string;
    severity?: string;
  };
  declared_by: string | null;
  severity: string;
  rationale: string;
}

export interface Speed {
  inputs: number;
  ratio: number;
  a_median_us: number;
  b_median_us: number;
}

export interface Experiment {
  id: string;
  target: string;
  status: string;
  mode: string;
  claims: string[];
  focus: string;
  hypotheses: string[];
  round: number;
  code: string;
  repaired: boolean;
  error: string | null;
  stats: null | {
    cases: number;
    agree: number;
    diverge: number;
    flaky: number;
    load_error_a: string | null;
    load_error_b: string | null;
    speed: Speed | null;
  };
}

export interface Suite {
  ran: boolean;
  passed?: number;
  failed?: number;
  errors?: number;
  skipped?: number;
  summary?: string;
  error?: string;
}

export interface Verdict {
  label: VerdictLabel;
  headline: string;
  summary: string;
  counts: Record<string, number>;
  speed: Speed | null;
  suites: Record<string, Suite>;
}

export interface Subject {
  id: string;
  kind: string;
  title: string;
  body: string;
  repo: string;
  base_ref: string;
  head_ref: string;
  url: string | null;
  author: string | null;
  scenario?: string | null;
  commits: string[];
}

export interface ResearchNote {
  kind: string;
  package?: string;
  before?: string;
  after?: string;
  answer?: string;
  sources?: { title: string; url: string; snippet: string }[];
  pages?: { url: string; excerpt: string }[];
}

export interface Result {
  id: string;
  created_at: number;
  duration: number;
  subject: Subject;
  executor: string;
  universes: Record<string, Record<string, unknown>>;
  roster: Record<string, { id: string; label: string; role: string }>;
  diff: {
    files_changed: string[];
    files_added: string[];
    files_removed: string[];
    stats: { additions: number; deletions: number };
    dependency_changes: { package: string; before: string | null; after: string | null }[];
    unified: string;
    targets: { qualname: string; status: string; reason: string; public: boolean }[];
  };
  intent: string;
  claims: Claim[];
  research: ResearchNote[];
  suites: Record<string, Suite>;
  experiments: Experiment[];
  divergences: Divergence[];
  ledger: LedgerRow[];
  verdict: Verdict;
  meter: {
    total_cost: number;
    total_tokens: number;
    models: Record<string, { calls: number; prompt_tokens: number; completion_tokens: number; cost: number; seconds: number }>;
  };
  artifacts: { markdown: string; pinned_tests: string };
  baseline?: Baseline;
}

export interface Baseline {
  review: string;
  approve: boolean;
  executable: number;
  real: number;
  cost: number;
  predictions: {
    description: string;
    call: string;
    before: string;
    after: string;
    real: boolean | null;
    observed_before: string;
    observed_after: string;
  }[];
}

export interface ScenarioCard {
  id: string;
  title: string;
  repo: string;
  blurb: string;
  author: string;
  recorded?: {
    id: string;
    verdict: VerdictLabel;
    headline: string;
    counts: Record<string, number>;
    cost: number;
    duration: number;
  } | null;
}

export interface RecordedRun {
  id: string;
  title: string;
  repo: string;
  kind: string;
  url: string | null;
  author: string | null;
  verdict: VerdictLabel;
  headline: string;
  counts: Record<string, number>;
  cost: number;
  duration: number;
  undeclared: { title: string; case: string; a: string; b: string }[];
  baseline_approve: boolean | null;
}

export interface Health {
  ok: boolean;
  llm: boolean;
  tavily: boolean;
  live: boolean;
  access_code_required: boolean;
  remote_prs: boolean;
  executor: string;
  budget: Record<string, number>;
  roster: Record<string, { id: string; label: string; role: string }>;
}

export interface StreamEvent {
  type: string;
  ts: number;
  data: Record<string, any>;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body.detail || msg;
    } catch {
      /* body was not JSON */
    }
    throw new Error(msg);
  }
  return res.json();
}

/** Static mode (GitHub Pages): recorded runs replay in the browser; live runs go to VITE_API_BASE when set. */
export const STATIC = import.meta.env.VITE_STATIC === "1";
const REMOTE = ((import.meta.env.VITE_API_BASE as string | undefined) || "").replace(/\/$/, "");
const API = STATIC ? REMOTE : "";
const DATA = `${import.meta.env.BASE_URL}data`;
const canLive = !STATIC || !!REMOTE;

const STATIC_HEALTH: Health = {
  ok: true,
  llm: false,
  tavily: true,
  live: false,
  access_code_required: true,
  remote_prs: false,
  executor: "local",
  budget: { run_cap: 0.25, daily_cap: 1.5 },
  roster: {
    ultra: { id: "nvidia/Nemotron-3-Ultra-550b-a55b", label: "Nemotron 3 Ultra", role: "Reads the PR and the code, writes the claim ledger and the experiment plan, delivers the final verdict." },
    super: { id: "nvidia/nemotron-3-super-120b-a12b", label: "Nemotron 3 Super", role: "Splits diverging behavior by root cause, explains it in plain language, and rates its severity." },
    lightning: { id: "nvidia/Nemotron-3_5-Lightning", label: "Nemotron 3.5 Lightning", role: "Writes executable probes in parallel, one experiment per target." },
    nano: { id: "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", label: "Nemotron 3 Nano", role: "Repairs probes that fail to run before they reach the comparison stage." },
  },
};

type RunDoc = { result: Result; events: StreamEvent[] };
const staticRuns = new Map<string, Promise<RunDoc | null>>();
function staticRun(id: string) {
  if (!staticRuns.has(id)) {
    staticRuns.set(
      id,
      fetch(`${DATA}/runs/${id}.json`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    );
  }
  return staticRuns.get(id)!;
}

async function remoteOr<T>(path: string, fallback: () => Promise<T>): Promise<T> {
  if (STATIC && !REMOTE) return fallback();
  try {
    return await fetch(`${API}${path}`).then((r) => json<T>(r));
  } catch (e) {
    if (STATIC) return fallback();
    throw e;
  }
}

export function downloadText(name: string, text: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const EVENT_TYPES = [
  "run", "stage", "universe", "claim", "research", "experiment", "probe", "repair", "execution",
  "suite", "model_call", "divergence", "ledger", "log", "done", "error",
];

export const api = {
  isStatic: STATIC,
  canLive,
  health: () => remoteOr<Health>("/api/health", async () => STATIC_HEALTH),
  scenarios: () =>
    remoteOr<ScenarioCard[]>("/api/scenarios", () => fetch(`${DATA}/scenarios.json`).then((r) => json<ScenarioCard[]>(r))),
  recorded: () =>
    remoteOr<RecordedRun[]>("/api/recorded", () => fetch(`${DATA}/recorded.json`).then((r) => json<RecordedRun[]>(r))),
  async run(id: string): Promise<Result> {
    const local = STATIC ? await staticRun(id) : null;
    if (local) return local.result;
    return fetch(`${API}/api/runs/${id}`).then((r) => json<Result>(r));
  },
  start: (body: { kind: string; scenario?: string; url?: string; access_code?: string }) => {
    if (!canLive) {
      return Promise.reject(new Error("This static demo replays recorded runs. Run live with the CLI: polygraph pr <url>"));
    }
    return fetch(`${API}/api/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<{ id: string }>(r));
  },
  stream(id: string, speed: number, onEvent: (e: StreamEvent) => void, onEnd: () => void): () => void {
    let stopped = false;
    let es: EventSource | null = null;
    const replay = async (doc: RunDoc) => {
      const k = Math.max(0.5, Math.min(speed, 50));
      let prev: number | null = null;
      for (const ev of doc.events) {
        if (stopped) return;
        if (prev !== null) {
          const gap = Math.min(Math.max(ev.ts - prev, 0), 1.5);
          await new Promise((r) => setTimeout(r, (gap * 1000) / k));
        }
        prev = ev.ts;
        onEvent(ev);
      }
      if (!stopped) {
        onEvent({ type: "done", ts: Date.now() / 1000, data: { result: doc.result } });
        onEnd();
      }
    };
    const live = () => {
      es = new EventSource(`${API}/api/runs/${id}/events?speed=${speed}`);
      for (const t of EVENT_TYPES) {
        es.addEventListener(t, (msg) => {
          const ev = JSON.parse((msg as MessageEvent).data) as StreamEvent;
          onEvent(ev);
          if (t === "done" || t === "error") {
            es?.close();
            onEnd();
          }
        });
      }
      es.onerror = () => {
        es?.close();
        onEnd();
      };
    };
    if (STATIC) {
      staticRun(id).then((doc) => (doc ? replay(doc) : canLive ? live() : onEnd()));
    } else {
      live();
    }
    return () => {
      stopped = true;
      es?.close();
    };
  },
};
