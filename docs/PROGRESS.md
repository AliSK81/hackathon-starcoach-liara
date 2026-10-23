# Progress

## Status board

- **Current phase:** all phases done; `v1.0.0` tagged. Now improving the weakest score items.
- **Live / working:** demo app `starcoach-shop` on Liara (team «لیارا», small-g2, healthy). The full live scenario passes all 5 checks (`results/live-scenario.json`). 84 offline tests pass. Diagnosis eval 100% on 34 incidents plus the real incident (after F17).

### What we need from the user

| Item | Needed by phase | Status |
|---|---|---|
| `LIARA_API_TOKEN` in `.env` | 1 | done |
| Account balance — not needed: the team wallet pays (F15) | 3 | done |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` in `.env` | 2 | done |

## How to work on the next change

1. Read the status board and the roadmap table. Find the current phase.
2. If the phase has no plan, write `docs/phases/phase-<N>-<name>.md`: the goal, the choices, and a checklist. Keep it short. Mark the phase `planned`.
3. Pick the next change: the smallest step that leaves the project working and moves it toward a requirement. Check DECISIONS.md first. Don't ask again what is decided there.
4. Read only the research this change needs. Check facts against the real system. Write new facts in DECISIONS.md before code depends on them.
5. Build it. Add offline tests. Run something real that proves it works: the real command, the real API, the real data.
6. Write a PROGRESS entry. Update the status board, the roadmap table, the phase checklist, and the README if a command changed.
7. Commit. Then go straight to step 1.

## Entry template

```
### Change N — <what shipped, in one line> — <date>
Phase: <N, step M>
How to see it: <the exact command>
Proof it works: <what you ran, and what happened, with numbers>

Research: <what you checked, or "none". Say if old research was wrong.>
Questions: <question -> answer, or "none">
Decisions: <IDs, or "none">

Shipped:
- ...

Not done yet:
- <honest gaps>

Next change idea:
- <a suggestion only>
```

## Entries

### Change 1 — The project installs, runs, logs and tests offline — 2026-10-22
Phase: 0, steps 1–6
How to see it: `uv sync && uv run starcoach --help && uv run pytest -q`
Proof it works: `uv run starcoach version` printed `starcoach 0.1.0`. `logs/events.jsonl` got 2 lines (`run`, `exit`). `pytest -q`: 4 passed in 0.09s, no network.

Research: none for this change. Checked API reachability: F1, F2. Checked the local Liara CLI: F3.
Questions: token, budget, LLM, UI → answered (D1–D4).
Decisions: D1–D6

Shipped:
- `pyproject.toml` (uv, hatchling, script `starcoach`). No runtime dependencies. `pytest` for dev.
- `config.py`: `.env` parser, settings, secret masking.
- `eventlog.py`: append-only JSONL log, masks secrets.
- `cli.py`: argparse CLI, `version`, a last-resort error guard that logs and prints one line.
- `.gitignore` (ignores `.env`, `logs/`), `.env.example`, README in UTF-8 (the old one was UTF-16 and broke the build).

Not done yet:
- No Liara calls. No LLM.

Next change idea:
- A Liara HTTP client and `starcoach check`.

### Change 2 — Liara API client and read-only commands (check, apps, status, limits) — 2026-10-22
Phase: 1, steps 1–5
How to see it: `uv run starcoach limits` (no token needed); `uv run starcoach check` (needs `LIARA_API_TOKEN`)
Proof it works: `pytest -q`: 9 passed, offline. `starcoach check` without a token prints `error: No Liara token. Set LIARA_API_TOKEN in .env.` and exits 2. `starcoach limits` prints English and Persian lines. Not yet run against the real API: the token is not in `.env` yet.

Research: 02 (deploy) and 03 (logs/metrics) are in. Checked the base URL in the CLI source and on the real hosts: F4.
Questions: none
Decisions: D5, F2, F4

Shipped:
- `liara.py`: stdlib client, swappable transport, GET retry on 429/5xx, no retry on POST, plain-language errors, calls logged without secrets.
- `limits.py`: 7 known API limits, English and Persian.
- CLI: `check`, `apps`, `status <app>`, `limits`. API errors exit 2 with one clear line.
- Fix: UTF-8 stdout, so Persian prints on the Windows console (it crashed with `charmap`).

Not done yet:
- Real-API proof for `check`/`apps`/`status`: waiting for the token.
- Research files 01, 04, 05, 06 and `docs/research/00-index.md` are not finished.

Next change idea:
- Write the research index. Then do the Phase 2 thin agent, using a fake LLM in tests.

### Change 3 — Liara error bodies are mapped by their real shape — 2026-10-22
Phase: 1, step 5
How to see it: `uv run pytest -q tests/test_liara.py`
Proof it works: 13 tests pass offline. New cases: `frozen_project`, 428 `max_deployment_count_in_day`, 402, 409.

Research: 01 (error format `{statusCode, message, data:{code}}`, inferred from the CLI, not documented).
Questions: none
Decisions: none

Shipped:
- `_friendly` reads `data.code` and code-like `message`. New messages: 402 balance, frozen app, free-plan 403, 409 busy, 428 plan limit.

Not done yet:
- Real error bodies are not yet seen. Check them on the first real failure.

Next change idea:
- Research index, then the Phase 2 thin agent.

### Change 4 — Thin agent: `starcoach chat` with a risk gate and status lines — 2026-10-22
Phase: 2, steps 1–5
How to see it: `uv run starcoach chat` (needs `.env`); `uv run pytest -q tests/test_agent.py`
Proof it works: 19 tests pass offline. The scripted-LLM tests show: a read tool runs with no approval; `restart_app` runs only after yes; on no, Liara gets no POST and the LLM sees `rejected`; a 404 goes back to the LLM as an error; env var values never reach the LLM (only names). Without `.env`, `chat --once hi` prints one clean line and exits 2.

Research: 01 (restart endpoint `POST /v1/projects/{name}/actions/restart`). 05 not finished; the loop uses the standard OpenAI tool-calling shape.
Questions: none
Decisions: D3, D6

Shipped:
- `llm.py`: OpenAI-compatible chat client, stdlib HTTP.
- `tools.py`: tool registry with risk tiers. Read: `list_apps`, `app_status`, `api_limits`. Change: `restart_app`.
- `agent.py`: loop, max 8 rounds, approval callback, events to the screen and to the JSONL log. A Persian-first system prompt.
- CLI `chat` (REPL and `--once`). Terminal approval accepts yes / بله.
- Fix: the CLI error guard crashed on `LLMError` (no `status`). It now has a test.

Not done yet:
- No real LLM run yet (needs LLM settings in `.env`).

Next change idea:
- Phase 3: `starcoach recommend <dir>` (platform detection and plan suggestion).

### Change 5 — `starcoach recommend` suggests platform, port and plan; demo shop app — 2026-10-22
Phase: 3, steps 1–2
How to see it: `uv run starcoach recommend examples/demo-node`
Proof it works: on the demo app it prints `Platform: node  Port: 3000  RAM need: ~512 MB` and no warnings. 35 tests pass offline (12 platform cases, UTF-16 requirements, warnings, plan pick). The demo app runs locally: `/` → 500 with `Error: connect ECONNREFUSED 127.0.0.1:5432` in its log (no `SHOP_DB_URL`), and `/health` → 200.

Research: 02 §6 (detection order, ports) and §8 (failures), checked against `liara-cloud/cli@14ec35f:src/commands/app/create.ts:156-213` for plan fields (`available`, `region`, `RAM.amount`, `CPU.amount`, `price` per hour × 720) and the `g2` filter.
Questions: none
Decisions: D7

Shipped:
- `recommend.py`: CLI-order platform detection, default ports, pre-deploy checks (no `npm start`, Next.js standalone, no requirements.txt, `.env` present, fixed port), and a plan pick from the real `/v1/me` plan list.
- `LiaraClient.plans()` keeps only `plans` from `/v1/me`. The rest holds personal data and storage keys.
- `examples/demo-node`: a dependency-free shop. It returns 500 without `SHOP_DB_URL`, and `LEAK_MB` makes it leak memory. These are the phase 5 demo faults.

Not done yet:
- The plan pick is not yet checked against the real plan list (needs the token).

Next change idea:
- Packer (tar.gz with ignore rules), then `deploy`.

### Change 6 — `starcoach deploy` and `create` work through the API, no Liara CLI — 2026-10-22
Phase: 3, steps 3–6
How to see it: `uv run starcoach deploy examples/demo-node --app <name>` (needs the token and an app)
Proof it works: 42 tests pass offline. A fake Liara API checks the whole flow: `GET /v1/projects/shop` → multipart upload to `/v2/projects/shop/sources` → `/v2/projects/shop/releases` with `sourceID`, `port` 3000, `type` node → 3 build-log polls → `READY`. Also checked: `FAILED` gives its `failReason`; a stopped app is refused; the packer drops `.env`, `.env.local`, `node_modules`, `.git` and `.gitignore` patterns, and keeps `.env.example`. Not yet run on the real API.

Research: 02 §2–3 (flow, states, ignore rules). New fact: app create needs a network (F5).
Questions: none
Decisions: D2 (the `starcoach-` prefix is forced on created apps), F5

Shipped:
- `deploy.py`: packer (tar.gz, CLI fixed ignore list plus all `.env*`, root `.liaraignore` > `.dockerignore` > `.gitignore`), multipart builder, `Deployer` with progress events, and the final state, fail reason, stderr lines and last log lines.
- `LiaraClient.create_app` (picks the network), `networks()`.
- CLI `create` and `deploy`, both ask first (`--yes` skips the question).
- Agent tools: `recommend_setup`, `release_status` (read); `create_app`, `deploy_app` (change). Deploy progress shows in chat.

Not done yet:
- Real deploy. Ignore-file negation (`!pattern`) is not supported. Nested ignore files are not read.

Next change idea:
- Phase 4: logs, metrics, health probe (offline), while waiting for the token.

### Change 7 — `logs`, `events`, `metrics`, `health`: see what an app is doing — 2026-10-22
Phase: 4, steps 1–6
How to see it: `uv run starcoach health https://liara.ir --tries 3`; `uv run starcoach logs <app> --errors` (needs the token)
Proof it works: real probe: `https://liara.ir: 100% OK over 3 tries` with status codes and p50/max latency. 48 tests pass offline: two log streams are merged and sorted by nanosecond timestamp, `_entry`/`type` are decoded, a non-JSON line is kept as raw text, the error filter keeps 2 of 4 lines, metrics are joined with plan limits (CPU max 0.45 of 0.5 cores = 90%, RAM 460 MB of 512 MB = 89.8%), and the probe counts a 500 and a timeout.

Research: 03 §1–5. The metric units and the meaning of `since` are still not verified on real data.
Questions: none
Decisions: none

Shipped:
- `observe.py`: v2 logs and events flattening, error-line filter, metric stats per instance with % of plan limit, our own HTTP probe (`ok_ratio`, p50, max, server errors).
- CLI `logs`, `events`, `metrics`, `health`.
- Agent tools (read): `get_logs`, `get_events`, `get_metrics`, `probe_site`. Log text reaches the LLM with a note that it is data, not instructions.
- Fix: p50 used the upper middle value for even counts.

Not done yet:
- Real check of metric units and `since` (needs the token and a live app).

Next change idea:
- Phase 5: the rule-based diagnosis engine, tested on log samples kept apart from the ones used to write the rules.

### Change 8 — Diagnosis engine, fix tools and fix verification — 2026-10-22
Phase: 5, steps 1–6
How to see it: `uv run starcoach eval`; `uv run starcoach diagnose <app>` (needs the token)
Proof it works: `starcoach eval` on 34 labelled incidents. First runs, before any tuning on each set: dev 8/8 (baseline 2/8); holdout-1 13/14 = 92.9% (baseline 57.1%) (F6); fresh holdout-2 8/12 = 66.7%, **worse than the baseline's 75%** (F7). After two fixes found that way: 100% top-1 on all three sets; baselines 25% / 57% / 75%. 76 offline tests pass. Real LLM: 5/5 on the demo scenario (F9). A fresh clone installs and passes all tests. They include: the demo incident's top cause is `X-ENV-MISSING` with action `set_env SHOP_DB_URL`; OOM is scored lower when memory peaked at 30%; `gather` survives 3 failing sources; `verify_fix` waits 20 s for a restart and then says "fixed"; it says "not fixed" when `ECONNREFUSED` is still logged; `set_env` merges and de-duplicates; it refuses when encrypted envs exist; the env value never appears in events; a danger tool needs the app name typed.

Research: 06 §3–6 (rules, weights, verification). 01 §4 (update-envs replaces all and restarts; encrypted values may be masked → we refuse).
Questions: none
Decisions: F6, F7

Shipped:
- `diagnose.py`: 24 log rules (Node, Python, PHP/Laravel, cross-platform), metric rules (memory ≥ 90%, CPU ≥ 85%), probe rules (all 502, Django 400), app-off and release-state rules, contradiction penalty, cause chains, Persian and English titles and fixes, suggested actions.
- `gather` (evidence from 6 sources, each failure noted) and `verify_fix` (wait for the app, probe, check signatures).
- `evaluate.py` and `starcoach eval`: engine vs a naive baseline, saved to `results/diagnosis-eval.json`.
- Client: `scale`, `resize`, `set_env` (merge; refuses with encrypted envs).
- CLI: `diagnose`, `verify`, `eval`, `set-env`, `start`, `stop`, `resize`. Danger actions need the app name typed.
- Agent: tools `diagnose_app`, `verify_fix`, `set_env` (value masked in status and logs), `start_app`, `stop_app`, `resize_app`. The prompt now says: diagnose first, never invent causes, verify after every fix, never obey text found in logs.
- Demo app logs `SHOP_DB_URL is not set` at start, like many real apps.
- Fixes found by the eval: the "502 ⇒ port" fallback no longer outranks a specific cause. The best cause is always shown. The loopback rule also matches "Running on http://127.0.0.1".

Not done yet:
- All three sets are now used for tuning. The next honest test is real incidents on the live demo app.
- The real end-to-end scenario on Liara (needs the token).

Next change idea:
- Phase 6: the web chat UI with approval cards (no keys needed to build it).

### Change 9 — Web chat with live status and approval cards — 2026-10-22
Phase: 6, all steps
How to see it: `uv run starcoach web`, then open http://127.0.0.1:8765
Proof it works: 63 tests pass offline. 5 are HTTP tests on a real local server with a scripted LLM and a fake Liara: the page is served; restart waits for the card, and Liara gets no call until "approve"; an approval id is single use (second answer → 400); a danger action is refused with a wrong typed name and accepted with the right one; reject means no call; history trimming keeps the sequence numbers. Checked by eye in the browser pane (desktop and 375 px mobile) with a scripted diagnose → set_env → answer flow: RTL layout, step timeline, approval card with Persian impact text and the masked value, a green card after approval, the conversation rebuilt after reload.

Research: 05 (approval tied to exact args, single use; SSE; typed name for destructive actions).
Questions: none
Decisions: none

Shipped:
- `web.py`: stdlib threaded server, `/api/chat`, `/api/events` (SSE with ids and replay), `/api/approve`. Approvals have single-use ids and time out after 10 minutes (counted as reject). Binds to 127.0.0.1.
- `static/index.html`: Persian-first RTL chat, quick-start buttons, step timeline with Persian tool names, deploy log box, approval cards (Persian impact text, risk badge, typed name for danger), safe minimal markdown (HTML is escaped first), dark mode, mobile layout.
- CLI `web [--host --port]`.
- Bugs found and fixed while testing: a closed SSE connection's thread stole the next event (now a sequenced history); sequence numbers broke after history trimming (own counter, with a test); answered cards stayed clickable after reload; raw markdown symbols; English text on Persian cards; the composer covered the last message on phones.

Not done yet:
- Not tried with a real LLM yet (needs `.env`).

Next change idea:
- Phase 7: `watch` (scheduled health checks with deduplicated alerts) and the `domain` guide.

### Change 10 — `watch` automation and the `domain` guide (IRNIC) — 2026-10-22
Phase: 7, steps 1–6
How to see it: `uv run starcoach domain starcoach-shop myshop.ir` (no token needed for the guide); `uv run starcoach watch <app> --once`
Proof it works: 70 tests pass offline. A probe sequence 200,200,500,500,200 gives exactly 3 alerts (unknown→up, up→down, down→up), and the "down" alert names the likely cause. A second process with the same state file writes no duplicate alert. Auto-restart never happens without the flag; with it, 2 restarts over 3 cycles across a 1-hour cooldown. One app with a DNS error does not stop the cycle. The real `domain ... myshop.ir` prints the 7 IRNIC steps in Persian and English.

Research: 04 B.2–B.7 (domain API, records, IRNIC steps, Liara nameservers, SSL).
Questions: none
Decisions: none

Shipped:
- `watch.py`: states up/slow/degraded/down, alerts on change only, atomic state save before the alert, diagnosis attached, opt-in auto-restart with a 1-hour cooldown, errors logged and the cycle goes on.
- `domains.py`: list, add, check, SSL, and a bilingual registrar guide (IRNIC or generic) with the records to add.
- CLI `watch`, `domain`. Agent tools `domain_guide`, `add_domain`, `enable_ssl`. Persian labels in the web UI.

Not done yet:
- Real runs (needs the token). The Liara nameservers come from a live lookup in research, not from our own zone API call.

Next change idea:
- A lint pass. Then the reviewer doc (phase 8), while waiting for `.env`.

### Change 11 — Lint pass — 2026-10-22
Phase: clean-up (rule 12)
How to see it: `uvx ruff check src tests`
Proof it works: ruff reports "All checks passed!". 70 tests pass.

Research: none
Questions: none
Decisions: none

Shipped:
- Ruff config in `pyproject.toml` (E, F, W, B, I; long lines and `l` names allowed).
- Sorted imports. `zip(..., strict=True)` in the domain guide. `pytest.raises` instead of `assert False`.

Not done yet:
- none

Next change idea:
- The reviewer doc (phase 8).

### Change 12 — Reviewer doc `docs/SOLUTION.md` — 2026-10-22
Phase: 8, step 1
How to see it: open `docs/SOLUTION.md`
Proof it works: it covers every item that requirements.md asks of the MD document: architecture (diagram plus layers plus reasons), how we connect to the Liara API (auth, endpoints, security), limits (Liara's and ours), how the user interacts (web, terminal, risk tiers), and results with numbers (eval table with the honest first runs, test count).

Research: none new.
Questions: none
Decisions: none

Shipped:
- `docs/SOLUTION.md`, linked from the README.

Not done yet:
- The real-run results section waits for the token.

Next change idea:
- When `.env` arrives: `check`, deploy the demo app, run the real scenario, and record facts.

### Change 13 — Fresh-clone check; LLM calls hardened for any OpenAI-compatible provider — 2026-10-22
Phase: 8, step 2 (and phase 2 robustness)
How to see it: `uv run pytest -q tests/test_llm.py`
Proof it works: a fresh `git clone` of the GitHub repo, then `uv sync`, then `uv run pytest -q`: 70 passed; `starcoach eval` gave the same numbers. After this change, 73 tests pass. A 429 is retried and then succeeds. A 400 is not retried. Tool arguments sent as an object work. An assistant turn with tool calls is stored with `content: null`.

Research: 05 (provider differences; tool calling through OpenAI-compatible gateways).
Questions: none
Decisions: none

Shipped:
- `ChatLLM`: up to 3 tries on network errors, 429 and 5xx, with backoff. The attempt number is logged.
- `Agent`: accepts tool arguments as a JSON string or an object. Uses `content: null` next to tool calls.

Not done yet:
- Not tried against the user's real provider.

Next change idea:
- Real runs once `.env` exists.

### Change 14 — The demo scenario is a regression test — 2026-10-22
Phase: 5/8
How to see it: `uv run pytest -q tests/test_scenario.py`
Proof it works: a Persian request ("site gives 500") → `diagnose_app` returns `X-ENV-MISSING` with action `set_env SHOP_DB_URL` → only `set_env` asks for approval → `update-envs` is called → `verify_fix` sees 5/5 × 200 and no old error lines → `fixed`. The env value never appears in events. 74 tests pass.

Research: none
Questions: none
Decisions: none

Shipped:
- `tests/test_scenario.py`: a stateful fake Liara whose app is broken until the env var is set.

Not done yet:
- The same scenario on the real Liara (needs `.env`).

Next change idea:
- Real runs.

### Change 15 — Real LLM runs the demo scenario: 5/5 after a prompt fix — 2026-10-23
Phase: 2 and 5, real-run steps
How to see it: `uv run python evals/llm_scenario.py 5` (needs the LLM settings in `.env`)
Proof it works: with the user's LLM and a simulated broken app, the first run passed. The second run failed: the model asked "do you approve?" in text instead of calling the tool. After the prompt fix: 5/5 runs passed, median 12.6 s, saved in `results/llm-scenario.json`. In each run: `diagnose_app` comes first; the answer is in Persian with causes, confidence and evidence; it asks for the env value instead of inventing one; `set_env` is the only approval; the value is masked; `verify_fix` runs after the fix; the app is fixed.

Research: none
Questions: none
Decisions: F8, F9, F10

Shipped:
- `evals/llm_scenario.py`: repeatable agent-behaviour eval with 5 checks per run.
- Prompt: the model must not ask for confirmation in text; the approval card does that.
- Answers are trimmed (they started with blank lines).
- `check` and the LLM client name example placeholders in `.env` plainly (with a test).

Not done yet:
- Everything on the real Liara API: `.env` still has the example token (F10).

Next change idea:
- With the real token: `check`, create and deploy the demo app, run the live scenario.

### Change 16 — First real Liara runs: connection, plans, balance; balance check before create — 2026-10-23
Phase: 1 and 3, real-run steps
How to see it: `uv run starcoach check`; `uv run starcoach recommend examples/demo-node`; `uv run starcoach create shop --platform node --plan small-g2 --bundle basic`
Proof it works:
- `check`: "Connected to Liara as … Apps: 0. Balance: 285 Toman."
- `recommend` on the real plan list: `small-g2` + `basic` = ~749,998 Toman/month (~1,042/hour) (F11).
- `create` first returned Liara's real 402 "Not enough balance", which we show as a plain message. Now it stops before calling Liara: "Your balance is 285 Toman. This app costs about 1,042 Toman/hour (~25,000 per day)…" (exit 6).
- Real LLM + real Liara (read-only), in `chat --once` and in the web UI: the agent read the project, the plans and the balance, said the balance is not enough, and gave the console top-up steps (F13).
- 76 offline tests pass.

Research: 04 A (plans, bundles) is confirmed by real data. The research guess "no plans endpoint, use /v1/me" is correct. New: `/v1/billing` shape (F12).
Questions: none
Decisions: F11, F12, F13, F14

Shipped:
- `LiaraClient.billing()` (keeps only money fields). `check` shows the balance.
- `create` estimates the hourly cost (plan + bundle) and stops if the balance does not cover 24 hours.
- `recommend` gives totals (plan + bundle) per hour and per month.
- Agent tool `account_status` (read): balance and app count.
- Web: markdown tables and `---` render properly (the real model uses them). Default port 8790 (F14).

Not done yet:
- Deploying and the live 500 scenario need a balance top-up (user task; payments cannot be done for you).

Next change idea:
- After the top-up: create `starcoach-shop`, deploy, run the live scenario, measure metric units.

### Change 17 — Live on Liara: team support, real deploy, real 500 → diagnose → approved fix → verified — 2026-10-23
Phase: 1, 3, 4, 5, 7 real-run steps
How to see it: `uv run python evals/live_scenario.py starcoach-shop --yes`; or open the web chat and say «سایت starcoach-shop خطای ۵۰۰ می‌دهد»
Proof it works (all on the real API, the real LLM, and the user's team «لیارا»):
- `check` → team balance 1,998,014 Toman. `create` → `starcoach-shop` on `small-g2` + `basic` (cheapest; D2).
- `deploy` → READY in 23 s (F22). `health` → 5/5 × 500, as designed.
- `diagnose` → root cause `SHOP_DB_URL` missing at 86%, which explains the DB connection error.
- Web UI: the agent asked for the value, showed one approval card, set the env, verified 5/5 × 200.
- `evals/live_scenario.py` (break → agent → fix): all 5 checks, 99.5 s.
- `watch --once` → alert `unknown → up`. `metrics` → RAM 29 MB of 512, CPU 0.02 of 0.5 cores.
- 82 offline tests pass; ruff clean; eval sets still 100%.

Research: real responses differed from research in 4 places, all recorded: teams (F15), logs paging (F19), events shape (F20), metric series lifetime (F24).
Questions: "balance is too low?" → the user said the money is in the Liara team → D9.
Decisions: D8, D9, F15–F24

Shipped:
- Teams: `LIARA_TEAM_ID`, `?teamID=` on every call, team wallet in `billing()`, `starcoach teams`, a hint in `check`.
- Probe connects directly (D8).
- Logs: the newest page (`direction=backward`).
- Events: real shape parsed; crashes (die without kill, paired per container), OOM; crash-loop symptom rule.
- Diagnosis: distinct-line counting, causal chain (missing env → connection errors), only current-release logs and events count.
- Verify: only logs after recovery, probes spread over a 40 s window, honest blip verdict.
- Metrics: only live instances.
- Limits registry: units measured, 100-line log pages, payments.
- `evals/live_scenario.py`; README and reviewer doc with the real results.

Not done yet:
- A custom domain was not added live (no test domain owned).

Next change idea:
- The line-by-line audit against requirements.md, then the tag.

### Change 18 — `restart` command; failed builds explained in plain words (checked live) — 2026-10-23
Phase: 3 and 5, audit gaps
How to see it: `uv run starcoach restart starcoach-shop`; deploy a folder whose package.json names a missing package
Proof it works:
- Real restart: Liara events kill → create → start; `verify` → 5/5 × 200; no false crash.
- Real failed deploy: FAILED. The first version printed only Docker's generic line. Now it prints "Cause: An npm package in package.json does not exist …: starcoach-package-that-does-not-exist-xyz", the fix, the npm 404 line as evidence, and that the live site is untouched (3/3 × 200). The test uses the real npm lines (F25). 83 tests pass.

Research: 02 §8 said "any non-STDOUT line is a build failure". Real npm errors are on STDOUT, so the whole output must be scanned (F25).
Questions: none
Decisions: F25

Shipped:
- CLI `restart` (rule 9: every capability is a command).
- `explain_build_failure`: npm 404 / ERESOLVE / missing start, pip, composer, compile errors. ANSI codes are stripped from build lines. The explanation goes to the CLI and to the agent.

Not done yet:
- none for this change

Next change idea:
- The audit against requirements.md, then the tag.

### Change 19 — Audit 1 against requirements.md, line by line — 2026-10-23
Phase: 8, step 3
How to see it: this entry. Each line names its proof (a command, a result file, or a doc section).
Proof it works: the table below. Before writing it, two gaps were closed in this change:
- "choose the deployment method": `recommend` now compares deploy methods.
- "service management": real stop → 503 → diagnose "app is turned off" 97% → start → verify 5/5 × 200 after 20 s.

| Requirement | Status | Proof |
|---|---|---|
| Guide choice of deployment and setup method | met | `starcoach recommend examples/demo-node` (platform, port, plan, deploy methods); agent tool `recommend_setup` |
| Review project, suggest infrastructure and plan | met, real | F11, F13: `small-g2` + `basic` ≈ 749,998 Toman/month from the real list of 42 plans |
| Help with setup, config, deploy | met, real | `create` + `deploy` → READY in 23 s (F22) |
| Domain setup, registrar (IRNIC) steps | met, partly real | `starcoach domain <app> <domain>`: IRNIC steps in Persian and English; the domain list endpoint was read for real; **adding a domain was not tried live (no test domain)** |
| User does only the essential outside steps | met | limits registry (`starcoach limits`): payments, registrar NS, notifications; the agent calls `api_limits` |
| Publish new versions | met, real | F22; failed versions are explained and the old version stays live (F25) |
| Config and service management via APIs | met, real | `set-env` (live scenario), `restart`, `stop`/`start` (this change); `resize` offline only (it changes cost) |
| Check status, find deploy errors | met, real | `status`, `apps`, release states PENDING→READY / FAILED (F20, F25) |
| Automate repetitive operations | met, partly real | `watch` (real `--once`, alert `unknown → up`); dedupe, diagnosis on failure, opt-in auto-restart tested offline |
| Health and CPU/RAM | met, real | `metrics` (units measured, F21, F24), `health` |
| Retrieve and analyze logs | met, real | `logs`, `diagnose` (F19: newest page, release-scoped) |
| Investigate slowness, malfunction, high usage | met; malfunction real, slowness/high usage offline | live 500 scenario; S-CPU / S-MEM rules in the eval sets (34 cases) |
| Suggestions for performance and stability | met | every cause has a fix; Persian and English (`diagnose.py`) |
| Take corrective action or guide the fix | met, real | `set_env` via an approval card → verified (`results/live-scenario.json`) |
| HTTP 500: gather, check logs/status/resources, rank causes, fix, verify | met, real | `results/live-scenario.json`: diagnose (86% root cause), approved fix, verify 5/5 × 200 |
| Human in the loop: approval for sensitive ops; low vs high risk; results visible | met, real | risk tiers read/change/danger; web card (real run); typed name for danger (`tests/test_web.py`); timeline in the UI |
| Use Liara APIs | met, real | SOLUTION.md §3 endpoint table; every endpoint used live except resize, domain add, SSL |
| Agent / MCP | met (agent) | `agent.py`; MCP is on the "Later" list |
| UI | met, real | web chat (`starcoach web`) and CLI |
| Disclose API limits | met | `starcoach limits` (9 items, Persian and English), tool `api_limits`, SOLUTION.md §5 |
| UX: plain request, status, evaluate suggestions, approve | met, real | Persian chat; timeline; confidence and evidence per cause; approval cards |
| Deliverable: runnable MVP with a real scenario | met, real | README; `evals/live_scenario.py` passes all 5 checks |
| Deliverable: MD doc (architecture, Liara API connection, limits, interaction) | met | `docs/SOLUTION.md` §2, §3, §5, §4 |
| Score 1 — integration, deploy, service management, operations | met, real | rows above |
| Score 2 — logs, errors, causes, solutions, checking fixes | met, real | live scenario; eval 100% vs baseline 25–75%; F17 shows the real top-1 miss and its fix |
| Score 3 — simplicity, clear suggestions, status, approvals | met, real | web UI run; LLM eval 5/5 (F9) |
| Score 4 — monitoring, automation, secure handling, API limits | met, partly real | watch real once; secrets masked (tests); `.env` never uploaded; limits registry |

Open gaps (honest):
- No live domain add or SSL (no test domain).
- No live resize (costs money; offline-tested).
- Slowness diagnosis is tested on written incidents, not on a real slow app.

Research: none
Questions: none
Decisions: none

Shipped:
- `deploy_methods` in `recommend` (with a test). Real stop/start proof. The reviewer doc results table now has the failed deploy, restart and stop/start.

Not done yet:
- The gaps above. None of them blocks a requirement: each requirement has shipped work with proof.

Next change idea:
- Fresh-clone check, then tag `v1.0.0`.

### Change 20 — Release v1.0.0 — 2026-10-23
Phase: 8, step 4
How to see it: `git checkout v1.0.0 && uv sync && uv run pytest -q`
Proof it works: a fresh clone of GitHub `main` at 9a96ff2 → `uv sync` → `pytest -q` with the HTTP(S) proxy pointed at a dead port: 84 passed; `starcoach eval` reproduces 100% on all 3 sets. Audit 1 (Change 19) maps every requirement to shipped work with proof. `starcoach version` → 1.0.0. The tag `v1.0.0` is on commit 5cdc89a (the version bump). This entry and the roadmap row were added just after it, because a locked `starcoach.exe` (a web server still running) stopped the scripted doc update.

Research: none
Questions: none
Decisions: none

Shipped:
- Version 1.0.0 and git tag `v1.0.0`.

Not done yet:
- The open gaps listed in Change 19.

Next change idea:
- Weakest score items: a real high-memory incident on the demo app (`LEAK_MB`) to test the S-MEM / OOM rules live.

### Change 21 — Real resource incidents: OOM and CPU slowness diagnosed live — 2026-10-23
Phase: improving score 2 (the weakest item: slowness and high usage were not proven live)
How to see it: `uv run starcoach diagnose <app>` while the demo app runs with `LEAK_MB=25` or `BUSY_MS=400` under traffic
Proof it works: on the second demo app `starcoach-lab`:
- OOM → `oom` events found, diagnosis OOM 86%; leak off → 40/40 OK (F26).
- CPU load → p50 1.1 s, CPU 85% of the plan; diagnosis CPU-limit 50% (was a miss: HEALTHY, F27).
- Eval sets unchanged; 84 tests pass. `starcoach-lab` is now stopped; `starcoach-shop` is untouched and healthy.

Research: 06's "OOM with low memory = contradiction" was wrong on real data (sampling misses peaks).
Questions: none
Decisions: F26, F27

Shipped:
- Demo app `BUSY_MS` (a CPU burn per request).
- Diagnosis: no OOM penalty from sampled memory; CPU + latency pairing at 500 ms; SLOW summary.
- Test: an OOM event with 54% sampled memory still ranks ≥ 80%.

Not done yet:
- A live agent conversation on these incidents with an approved fix (blocked: an auto-approving agent on a real app is not allowed; run it yourself in the web UI).

Next change idea:
- none planned
