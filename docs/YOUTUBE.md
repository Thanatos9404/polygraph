# YouTube upload

**File:** `docs/video/polygraph-youtube.mp4` (9.4 MB, 1600x900). Full-quality master: `docs/video/polygraph-final.mp4`.

**Title**

Polygraph: AI Code Review That Runs Your PR in Two Universes | NVIDIA Nemotron x Nebius

**Description**

Your tests passed. Your code still changed. Polygraph catches it.

Every pull request makes claims: "No behavior change." "Fixes the crash." "Routine dependency update." Polygraph checks them by experiment. It runs the code before and after the change in two isolated universes, feeds both the same inputs, and reports every behavior that moved, especially the ones nobody mentioned.

What you'll see:
🔬 An AI agent's "no behavior change" refactor that silently turns slugify('Straße') from "strasse" into "strae", while every test stays green
📦 A one-line dependency bump that a model reading the diff approved, and Polygraph found 5 breaking changes in
🐍 A real merged PR in python-humanize where natural_list(None) went from '' to a TypeError, mentioned nowhere

How it works:
• NVIDIA Nemotron 3 Ultra reads the PR, writes the claim ledger and experiment plan, and delivers the verdict
• Nemotron 3.5 Lightning writes executable probes in parallel, Nemotron 3 Nano repairs them
• Nemotron 3 Super splits divergences by root cause and explains each one
• Everything runs on Nebius Token Factory, about 2 to 9 cents per pull request
• Tavily pulls the official changelog when a dependency moves
• Each finding ships as a PR comment and a pytest file you can commit

Chapters
0:00 The idea in 30 seconds
0:34 Polygraph web app
0:58 Same PR: reading vs running
1:10 Live run on NVIDIA Nemotron
1:52 Claim ledger and witnesses
2:15 Dependency bump, Tavily, and the control arm
2:31 A real merged PR, caught
2:44 Merge what you can prove

Open source (Apache 2.0): https://github.com/Thanatos9404/polygraph

Built for the Nebius x NVIDIA Global AI Hackathon, Coding and Agentic Engineering track.

#AI #CodeReview #NVIDIA #Nemotron #Nebius #AIAgents #DevTools #OpenSource #Python #Hackathon

**Tags**

AI code review, code review, pull request, NVIDIA Nemotron, Nemotron 3, Nebius, Nebius Token Factory, AI agents, coding agents, agentic AI, LLM, differential testing, regression testing, software testing, GitHub, GitHub Actions, dependency update, Dependabot, developer tools, devtools, open source, Python, Tavily, AI hackathon, Devpost, Nebius NVIDIA hackathon, AI tools, code quality, software engineering, AI coding

**Settings:** Not made for kids · Visibility: Public · Category: Science & Technology · Language: English
