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

export const api = {
  health: () => fetch("/api/health").then((r) => json<Health>(r)),
  scenarios: () => fetch("/api/scenarios").then((r) => json<ScenarioCard[]>(r)),
  recorded: () => fetch("/api/recorded").then((r) => json<RecordedRun[]>(r)),
  start: (body: { kind: string; scenario?: string; url?: string; access_code?: string }) =>
    fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => json<{ id: string }>(r)),
  stream(id: string, speed: number, onEvent: (e: StreamEvent) => void, onEnd: () => void): () => void {
    const es = new EventSource(`/api/runs/${id}/events?speed=${speed}`);
    const types = [
      "run", "stage", "universe", "claim", "research", "experiment", "probe", "repair", "execution",
      "suite", "model_call", "divergence", "ledger", "log", "done", "error",
    ];
    for (const t of types) {
      es.addEventListener(t, (msg) => {
        const ev = JSON.parse((msg as MessageEvent).data) as StreamEvent;
        onEvent(ev);
        if (t === "done" || t === "error") {
          es.close();
          onEnd();
        }
      });
    }
    es.onerror = () => {
      es.close();
      onEnd();
    };
    return () => es.close();
  },
};
