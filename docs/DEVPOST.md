# Devpost submission: Polygraph

**Tagline (200 chars):** Every pull request makes claims. Polygraph checks them by experiment: it runs the old and new code side by side on NVIDIA Nemotron and reports every behavior that changed.

**Track:** Coding and Agentic Engineering

**Built with:** python, fastapi, react, typescript, tailwindcss, shadcn-ui, framer-motion, three.js, nvidia-nemotron, nebius-token-factory, tavily, uv, pytest, docker, github-actions, hugging-face-spaces

---

## Inspiration

Coding agents now open pull requests faster than people can read them, and every one of those PRs arrives with a confident description: "No behavior change." "Fixes the crash." "Routine dependency update." Review still means reading a diff, and a diff never runs. Tests stay green because they only check what someone thought to check. A dependency bump is worse: the diff is one line and the behavior change lives inside a library, so there is nothing to read at all.

We wanted a reviewer that does not take the description's word for it.

## What it does

Point Polygraph at a pull request. It:

1. Reads the title, description, commits and linked issues and splits them into a **claim ledger**, including implied claims such as "no behavior change" for a refactor.
2. Builds **two universes**: the code before the PR (A) and after (B), each with its own interpreter and, for real projects, its own venv with the project installed. A dependency bump really runs two library versions side by side.
3. Designs experiments, writes executable probes, and runs every probe in A, in A again (calibration, to discard noisy inputs), and in B. The project's own test suite runs in both universes, and every agreeing input is timed.
4. Rules on every claim: **confirmed, contradicted, or unverified**, and surfaces every **undeclared behavior change** with a witness: the same input, the output before, the output after.
5. Ships the result as a PR comment, a verdict that can gate the merge, and a pytest file that pins each finding (undeclared changes fail until they are declared or reverted).

It runs as a web app with live streaming runs, a CLI, a GitHub Action, and an API.

## Results

- **AI-agent refactor**, "No behavior change. All tests pass." Tests green, 2x speedup confirmed by timing, and `slugify('Straße')` silently changed from `strasse` to `strae`. Verdict: inconsistent.
- **Dependency bump** packaging 21.3 to 24.1, "routine maintenance". Tavily pulled the official changelog window (LegacyVersion removed in 22.0); Polygraph found five undeclared changes, e.g. `sort_versions(['1.0.0', 'invalid.version'])` now raises `InvalidVersion`. A diff-reading review by the same Nemotron 3 Ultra **approved it with zero findings**.
- **An honest rounding fix**: every divergence was declared. Verdict: consistent. Polygraph clears good PRs too.
- **Real merged PRs in python-humanize**: three honest fixes cleared with confirming witnesses, and in #381 Polygraph found that `natural_list(None)` used to return `''` and now raises `TypeError`, mentioned nowhere in the PR and approved by the diff reader.
- A full examination costs **2 to 9 cents** of Token Factory credit and takes under two minutes.

## How we built it

- **NVIDIA Nemotron on Nebius Token Factory**, four tiers, each sized to its job:
  - Nemotron 3 Ultra (550B): claim ledger, experiment plan with concrete witness calls, final verdict. Reasoning on.
  - Nemotron 3 Super (120B): splits each cluster of diverging inputs by root cause, explains it, rates severity.
  - Nemotron 3.5 Lightning: writes executable probes in parallel (cheap, fast, 1M context).
  - Nemotron 3 Nano: repairs probes that fail identically in both universes; Lightning regenerates if the repair does not compile.
- The pipeline is an agent loop: plan, write code, run it, repair it, compare, judge, and plan again for claims still unverified.
- **Twin execution** with a stdlib-only harness that canonicalizes outputs (type-preserving, address-scrubbed), per-case timeouts, micro-benchmarks, and calibration. Each universe is a separate tree with its own interpreter; installable projects get an editable install with an SCM version stub so generated files exist.
- **Token Factory Sandboxes** executor (beta): each universe becomes an immutable image, each probe a disposable branched operation.
- **Tavily** finds a bumped dependency's official sites through PyPI, scopes a search to them, and extracts the changelog entries between the two versions for the planner.
- **Spending safety**: every model call reserves its worst-case cost before it is sent; lifetime, daily, per-run and Tavily caps are enforced across processes. The public site replays recorded runs for free; live runs need an access code and are rate limited.
- **Front end**: React, Tailwind, shadcn/ui, Framer Motion and a three.js hero with two diverging "universe" traces; light and dark themes.
- **Control arm**: the same Nemotron 3 Ultra reviews each PR by reading it and predicts behavior changes as concrete calls, which Polygraph then executes. That measures what reading alone gets right.

## Challenges we ran into

- **Reasoning budgets.** Ultra sometimes spent its whole budget thinking and returned no answer. Every structured call now names a required key and retries once with reasoning off.
- **Real repositories are not importable as checked out.** humanize generates `_version.py` at build time. Universes now get editable installs, and import failures raised inside project code are classified as environment problems instead of being "repaired" (which wasted credits).
- **Fairness.** Our first real-world run called an honest PR inconsistent because the author's "800 tests pass" became "726 passed, 74 skipped" on our machine. Environment-dependent claims now earn review, not guilt, and a run where nothing executed is `inconclusive`.
- **One cluster, many causes.** Grouping by function merged unrelated changes; Super now splits them by root cause.

## Accomplishments that we're proud of

- A verdict computed from evidence, not from a model's opinion: the final label comes from the ledger in code.
- Catching an undeclared change in a real merged PR that people and a strong model both approved.
- The whole project, including every recorded case file, ran on free hackathon credits under hard caps.

## What we learned

A strong model reading a small diff is genuinely good at predicting what changed: every executable prediction in our control arm was real. It is blind to what is not in the diff. The useful role for the model is not judge but experimenter: write the hypotheses, then let execution decide.

## What's next

JavaScript and TypeScript universes, Hypothesis-style input shrinking for minimal witnesses, Polygraph as a check on agent-authored PRs before they reach humans, and running probes at scale on Token Factory Sandboxes.

---

## Testing instructions

- Live demo: https://yvt94-polygraph.static.hf.space
- Video: https://youtu.be/VFzUl18uwP8
- Pitch deck: https://drive.google.com/file/d/1qhkE1zz1Kd63j91KUNJRkx0nBC0VPRRt/view?usp=sharing
- Source: https://github.com/Thanatos9404/polygraph
- Recorded runs replay for free from the landing page ("Replay recorded run").
- Live runs: click "Run live" on any case file, or paste a public GitHub PR URL into the hero. Access code: `<ACCESS CODE>`.
- Local: `uv venv && uv pip install -e .`, add `NEBIUS_API_KEY` to `.env`, then `polygraph scenario packaging-bump` or `polygraph pr https://github.com/python-humanize/humanize/pull/381`.

## Feedback on Nebius Token Factory, AI Cloud and NVIDIA models

1. **Model IDs differ between sources.** The cookbook uses `nvidia/nvidia-nemotron-3-nano-30b-a3b` and the regional base URL `api.tokenfactory.us-central1.nebius.com`, while `/v1/models` and the public catalog use `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` on `api.tokenfactory.nebius.com`. One canonical ID per model, with aliases accepted, would remove guesswork.
2. **The public catalog endpoint (`/api/public/models_info`) is excellent.** Prices, context windows, regions and throughput in one call let us meter cost per call accurately. Linking it from the API reference would help others find it.
3. **Reasoning output when the budget runs out.** With `enable_thinking`, Nemotron 3 Ultra occasionally returns empty `content` and a long `reasoning_content` once `max_tokens` is reached. A documented reasoning budget parameter, or a `finish_reason` that says the answer was never started, would make this easy to handle.
4. **`chat_template_kwargs` works well** for per-call reasoning control. It deserves a section in the Token Factory docs, since it is the main cost lever for Nemotron 3.
5. **Per-key spending limits.** Builders on free credits need a hard cap on a key so a bug or a public demo cannot overspend. We built a reservation-based ledger to get that; a native cap would make public demos much safer.
6. **Sandboxes is a natural fit for agent testing.** "Branch, compare" maps directly onto differential testing. Beta access gating meant we shipped the executor without being able to test it end to end; a small free sandbox quota for hackathon participants would unlock more projects.
7. **Rate limit headers are clear and useful.** `x-ratelimit-remaining-*` plus the dynamic scale-up rules made concurrency tuning straightforward.
8. **Nemotron 3.5 Lightning** is a great code-writing workhorse at its price; most of our token volume runs on it for well under a cent per PR.
