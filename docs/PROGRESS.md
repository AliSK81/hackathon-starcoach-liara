# Progress

## Status board

- **Current phase:** 1 and 2 built offline; real runs wait for `.env`. Building phase 3.
- **Live / working:** `version`, `check`, `apps`, `status`, `limits`, `chat`, `recommend`, `create`, `deploy`, `logs`, `events`, `metrics`, `health`, `diagnose`, `verify`, `set-env`, `start`, `stop`, `resize`, `eval` (offline-tested; `health` also proven on a real URL; not yet run against the real API or LLM: needs `.env`). 58 offline tests pass. Diagnosis eval: 100% top-1 on 34 labelled incidents after fixes (see F6, F7 for the honest first runs).

### What we need from the user

| Item | Needed by phase | Status |
|---|---|---|
| `LIARA_API_TOKEN` in `.env` (Liara console → API) | 1 | asked |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` in `.env` | 2 | asked |

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
Proof it works: `starcoach eval` on 34 labelled incidents. First runs, before any tuning on each set: dev 8/8 (baseline 2/8); holdout-1 13/14 = 92.9% (baseline 57.1%) (F6); fresh holdout-2 8/12 = 66.7%, **worse than the baseline's 75%** (F7). After two fixes found that way: 100% top-1 on all three sets; baselines 25% / 57% / 75%. 58 offline tests pass. They include: the demo incident's top cause is `X-ENV-MISSING` with action `set_env SHOP_DB_URL`; OOM is scored lower when memory peaked at 30%; `gather` survives 3 failing sources; `verify_fix` waits 20 s for a restart and then says "fixed"; it says "not fixed" when `ECONNREFUSED` is still logged; `set_env` merges and de-duplicates; it refuses when encrypted envs exist; the env value never appears in events; a danger tool needs the app name typed.

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
