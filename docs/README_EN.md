<p align="center">
  <img src="https://www.evoloop.cn/assets/images/WoodenRobot.png" alt="EvoLoop" width="120" />
</p>
<p align="center"><b>EvoLoop Agent - Self-Duty Agent with Task Orchestration, Excels at Night Shifts</b></p>

<p align="center">
  <img src="https://img.shields.io/github/stars/wonderful-team/evoloop" alt="GitHub stars" />
  <img src="https://img.shields.io/github/v/release/wonderful-team/evoloop" alt="GitHub release" />
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License: MIT" />
  <a href="https://github.com/wonderful-team/evoloop/wiki"><img src="https://img.shields.io/badge/Docs-Wiki-blue" alt="Docs" /></a>
</p>

<p align="center">
  <a href="https://github.com/wonderful-team/evoloop/releases">Releases</a> &nbsp;·&nbsp;
  <a href="https://www.evoloop.cn">Website</a> &nbsp;·&nbsp;
  <a href="https://www.evoloop.cn/agent_multi">Try Online</a> &nbsp;·&nbsp;
  <a href="https://github.com/wonderful-team/evoloop/issues">Issues</a>
</p>

<p align="center">
  <a href="README_EN.md">English</a> | <a href="README_CN.md">中文</a> | <a href="README_JA.md">日本語</a> | <a href="README_KO.md">한국어</a>
</p>

---

EvoLoop is a **self-duty agent with orchestratable tasks** — it has a built-in three-power communication mechanism — **Decision-Maker, Executor, Reviewer-Supervisor** — making sure every item of a task gets done properly.

Have you ever run into this with an Agent: it plans a long-horizon task beautifully, but even with SKILL constraints, the actual execution comes out **incomplete, with loose ends, or drifting off course** — and you're stuck checking and correcting it through round after round of back-and-forth?

EvoLoop is built to solve exactly this, with a newly designed **duty-style task system**: tasks auto-execute when due, every step logs its progress in real time; upon completion, the **Reviewer-Supervisor** verifies the result from your standpoint — the executor saying "done" doesn't count, incomplete work gets sent back for rework; money and irreversible operations wait for the **Decision-Maker** (you) to sign off. You just plan tasks and accept results.

The system covers Web, desktop, and mobile, with natural voice conversation driven by a wake word.

🌐 Website [evoloop.cn](https://evoloop.cn) · 💻 [GitHub](https://github.com/wonderful-team/evoloop)

---

## 🎬 Product Demo

<table>
  <tr>
    <td valign="top">
      <img src="images/evoloop-ui.png" alt="EvoLoop Desktop" height="500" />
      <p align="center"><em>Desktop</em></p>
    </td>
    <td valign="top">
      <img src="images/evoloop-mobile.jpg" alt="EvoLoop Mobile" height="500" />
      <p align="center"><em>Mobile</em></p>
    </td>
  </tr>
<tr>
<td colspan="2" align="center">
<img src="images/evoloop-duty.png" alt="EvoLoop Duty" height="500" />
<p align="center"><em>Duty</em></p>

<img src="images/evoloop-duty-2.png" alt="EvoLoop Duty" height="500" />
<p align="center"><em>Duty HITL</em></p>
</td>
</tr>
</table>

**EvoLoop Full Feature Demo**

https://www.evoloop.cn/assets/video/demo.mp4

**Duty Task System Demo 1**

https://www.evoloop.cn/assets/video/duty1.webm

**Duty Task System Demo 2**

https://www.evoloop.cn/assets/video/duty2.webm

---

## 🏗 System Architecture

<p><img src="images/arch.png" alt="EvoLoop Architecture" /></p>

| Layer | Components |
|------|------|
| Clients | Web (React + Vite), Desktop (Tauri + Rust voice pipeline), Mobile (React Native, remote approve/accept) |
| Service | FastAPI: REST + SSE + voice WebSocket channel |
| Engine | Agent engine built on the [OpenHands](https://github.com/All-Hands-AI/OpenHands) SDK: plan → tool execution → structured self-check → suspend-and-ask when in doubt |
| Routing | Command triage: common commands execute directly; uncertain ones go to the Agent |
| Duty | Task queue + Supervisor scheduling: on-time execution, crash convergence, circuit-breaker guardrails |
| Extensions | MCP tool services, capability packs (SOP), runtime tool creation, macro engine (deterministic replay + self-heal) |
| Data | Desktop embedded (SQLite + LanceDB, data never leaves the machine) / SaaS server (PostgreSQL + Redis) |

---

## ⏱ Duty Task System (Autonomous Duty)

### The Problem

LLMs execute requirements **incompletely or with drift** — halfway through a long-horizon task, context drowns in noise and rots; the model fatigues, exits early, falsely claims completion, dodges direct answers, and deliverables drift from the goal. You're stuck **checking repeatedly and correcting through endless rounds of communication**, dragged into the execution details yourself.

The duty task system is designed to eliminate exactly this correction cost: tasks are created with scenario, goal, and acceptance criteria defined up front; execution state is fully persisted with breakpoint resume; upon completion, the result is **fed back to the original conversation under your name**, where the Agent that originally understood your requirement verifies it from your standpoint — the executor's "done" doesn't count; after two failed reworks, it escalates to human arbitration.

### The Goal

Let an Agent reliably run a business long-term: state the requirement once, and let the system handle the corrections. Humans only appear at three moments — approve, accept, arbitrate.

### Task Execution Flow

<p><img src="images/duty-workflow.png" alt="Duty Workflow" height="500" /></p>

### Suitable Scenarios

- **E-commerce / Retail Ops Management**: product research → pricing → listing → daily patrols (stockouts, bad reviews, anomalous orders) — the first pilot scenario is "take over a mall"
- **Content & Growth Pipelines**: planning → writing → asset creation → multi-platform publishing → campaign retrospective, every step traced and accepted
- **Data & Patrol Bots**: daily business reports, scheduled patrols of inventory / funds / metrics — anomalies trigger alerts and proposals instantly
- **Third-Party Event Response**: orders, tickets, review messages auto-enqueue for processing with a full audit trail
- **Enterprise Back-Office SOPs**: approval assistance, reconciliation, stocktaking — repeatable, auditable workflows
- **R&D Project Steward**: codebase patrols, dependency security checks, backup verification, backlog grooming
- **Customer Service Reception**: WeCom / WeChat customer service auto-replies; money-related issues escalate to humans
- **Eyes-Off Operation**: a 7×24 duty loop where humans only appear at three moments — approve, accept, arbitrate

Swap the takeover target (mall → CRM → supply chain → content site) by only swapping capability packs and task data — the scheduling and execution layers stay unchanged.

### Workbench

Infinite canvas as the main view: heterogeneous deliverable cards + dependency lines, visual focus auto-follows the Agent's current node; approve / accept / review cards embedded in nodes. You can answer three questions at any time — **what the Agent is doing, what it has done, what it will do next**.

---

## 🌟 Key Features

| Capability | Description |
|---|---|
| **Long-Horizon Execution** | 300+ continuous steps per task, hours of stable runtime, automatic error recovery |
| **Cross-Device A2A Collaboration** | Agents across devices discover, delegate, and return results asynchronously |
| **Duty Execution** | Tasks auto-queue and run when due; every step logs progress, completion attaches verifiable evidence. The executor's "done" doesn't count — results are sent back to your original request under your name, where the reviewer-supervisor verifies "was it really done right?". Money and irreversible operations always wait for human sign-off |
| **Imitation Learning** | You demonstrate once, it learns the whole workflow — click through a flow and it records the trace; drop in a screen recording and it watches frame-by-frame, distilling reusable skills or "macros". Later runs replay mechanically without burning compute; environment changes trigger automatic fallback to AI; AI-authored workflows must pass real execution tests before going live |
| **At Your Beck and Call** | Voice, web, WeCom/WeChat customer service, mobile — all sources treated equally. Common commands execute in seconds without waking the LLM; only unclear or complex requests get careful AI reasoning |
| **Voice Conversation** | Say "Hi Evo" to start talking, interrupt it mid-sentence, or dictate for it to type — audio never leaves your device |
| **Hands-On For You** | Works on the devices you already have — web pages in the browser, apps on the desktop, Android / iOS / HarmonyOS phones; away from the computer? Approve and accept from your phone |
| **Finds Help (A2A)** | The Agent on this machine can hand work to an Agent on another of your devices — the main flow waits automatically during delegation and resumes the moment results return; the whole handoff is visible in real time on the UI |
| **Safety Fuses** | Unsure? Stop and ask — never fabricate an answer. Dangerous operations sit behind permission gates; secrets never appear in output; runaway loops get cut off decisively |
| **Ecosystem Ready** | External tools plug in and unplug via MCP; business knowledge ships as capability packs — taking over a mall today, another system tomorrow, without touching core code |

---

## 🚀 Installation & Deployment

EvoLoop has three deployment modes — pick what fits:

| Mode | Scenario | Stack | Config File |
|---|---|---|---|
| **Desktop Embedded** | Personal computer, local use | SQLite + LanceDB + Huey | `.env.prod.desktop` |
| **Web Single-User** | Personal server | SQLite + LanceDB + Huey | `.env.prod.web.single` |
| **Web Multi-User** | Team / enterprise production | PostgreSQL + Redis + Meilisearch + Neo4j + Celery | `.env.prod.web.multi` |

### Desktop Embedded Mode (Personal Computer, Zero External Dependencies)

The backend bundles SQLite + LanceDB + Huey — runs standalone with the desktop app, data never leaves the machine:

```bash
# Clone the repo
git clone https://github.com/wonderful-team/evoloop.git
cd evoloop

# Backend: install deps + one-command start
cd backend
./bin/evo install
cp .env.prod.desktop .env      # Fill in your LLM API Key
./bin/evo start                # Brings up API + Worker together (evo stop to stop)

# Desktop app (Tauri, with voice wake; backend runs as a sidecar)
cd frontend
npm install
npm run tauri dev
```

### Web Single-User Mode (Personal Server)

```bash
cd backend
cp .env.prod.web.single .env
./bin/evo start
```

### Web Multi-User Mode (Team / Enterprise Production)

```bash
cd backend
cp .env.prod.web.multi .env
# Configure PostgreSQL / Redis / Meilisearch / Neo4j, or run ./bin/evo install full
./bin/evo start
```

`evo` command cheat sheet: `evo start / stop / status / logs` for services, `evo test` for tests, `evo check` for code quality — full list via `./bin/evo help`.

---

## 📦 Build & Release

```bash
# Desktop packaging
./deploy/build.sh macos-arm64 --env-file=.env.prod.desktop
./deploy/build.sh macos-x86_64 --env-file=.env.prod.desktop

# Mobile packaging (Android APK / AAB, iOS, HarmonyOS HAP)
./deploy/build.sh android --env-file=.env.prod.desktop   # APK; use --aab for Google Play
./deploy/build.sh ios --env-file=.env.prod.desktop
./deploy/build.sh harmony --env-file=.env.prod.desktop
./deploy/build.sh mobile --env-file=.env.prod.desktop    # all three platforms in one run

# Web static assets
./deploy/build.sh web --env-file=.env.prod.web.multi

# Model download
./deploy/download_models.sh --models nomic-embed,paraformer-zh
```

---

## 🤝 Cooperation & Community

We take on **custom agent projects** of all kinds — building duty agents for your business with EvoLoop (e-commerce ops, customer-service reception, patrol bots, and more), full-service from pilot to delivery. Get in touch:

**We also warmly welcome anyone interested to join this project and build it with us** — filing requirements, reporting bugs, writing code, or sharing playbooks all make you a builder of this ecosystem.

- **Website**: [evoloop.cn](https://evoloop.cn)
- **GitHub**: [wonderful-team/evoloop](https://github.com/wonderful-team/evoloop)
- **Issues**: [GitHub Issues](https://github.com/wonderful-team/evoloop/issues)
- **Email**: [preterchan@gmail.com](mailto:preterchan@gmail.com)
- **WeChat**: scan to reach me

<p align="center">
  <img src="images/wechat.png" alt="EvoLoop WeChat" width="200" />
</p>

---

<p align="center">
  <b>Built with ❤️ by EvoLoop Team</b>
</p>
