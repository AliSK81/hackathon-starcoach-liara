# Decisions and checked facts

Rules:
- Never edit old entries.
- A new entry can replace an old one. It says which one ("replaces D3").
- PROGRESS entries link to these IDs.

## Decisions

| ID | Decision | Date | Who |
|---|---|---|---|
| D1 | The Liara API token comes from the user's own `.env` (`LIARA_API_TOKEN`). The tool never reads `~/.liara-auth.json`. | 2026-10-22 | user |
| D2 | Real demo apps are allowed: at most 2 apps, cheapest plan, names start with `starcoach-`. Delete or resize only after the user says yes. | 2026-10-22 | user |
| D3 | The LLM is the user's own OpenAI-compatible provider. Base URL, model and key come from `.env` (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`). | 2026-10-22 | user |
| D4 | Interface: a local web chat and a CLI. The assistant answers in the user's language, Persian first. Docs are in English. | 2026-10-22 | user |
| D5 | Language: Python. Few libraries. Tests run offline. | 2026-10-22 | Claude |
| D6 | Risk tiers for every tool: `read` runs at once; `change` and `danger` need a user "yes" first. | 2026-10-22 | rules (requirements: Human-in-the-Loop) |
| D7 | Plan choice: the cheapest available Iran `g2*` plan with enough RAM for the platform class, plus the cheapest available feature bundle. The free plan is not suggested. RAM classes: static 256 MB, node/python/flask/go/php 512 MB, django/laravel/next/docker/dotnet 1 GB. | 2026-10-22 | Claude |

## Checked facts

| ID | Fact | Value | Date | Source |
|---|---|---|---|---|
| F1 | The Liara Iran API is reachable from the dev machine. Without a token it returns 401. | `GET https://api.iran.liara.ir/v1/projects` → 401 `{"error":"Unauthorized."}` | 2026-10-22 | `python -c "urllib.request.urlopen(...)"` |
| F2 | The dev machine uses an HTTPS proxy. curl/schannel fails the TLS revocation check through it. Python works. | `https_proxy=http://127.0.0.1:10808`; curl exit 35 `CRYPT_E_REVOCATION_OFFLINE` | 2026-10-22 | `curl -sv https://api.iran.liara.ir/v1/projects` |
| F3 | The installed Liara CLI is broken on the dev machine. We do not depend on it. | `Cannot find module ...@liara\cli\bin\run.js` | 2026-10-22 | `liara --version` |
| F4 | The official CLI uses `https://api.liara.ir` for the Iran region. `api.iran.liara.ir` also answers. We default to `api.liara.ir`. | both return 401 to `GET /v1/me` without a token | 2026-10-22 | liara-cloud/cli@14ec35f:src/constants.ts:11; `urllib.request.urlopen` on both hosts |
| F5 | Creating an app needs a private network id. The CLI reads `GET /v1/networks` and sends `network: <_id>` with `name, planID, platform, bundlePlanID`. | body fields as listed | 2026-10-22 | liara-cloud/cli@14ec35f:src/commands/app/create.ts:62-88; src/base.ts:457-505 |
| F6 | Diagnosis eval, first run. Dev set (8 cases): engine top-1 100%, naive baseline 25%. Holdout-1 (14): engine 92.9%, baseline 57.1%. Miss: the '502 ⇒ port' fallback outranked a specific log cause. Holdout-1 was then used to fix that, so it counts as dev from here on. | dev 1.0/0.25; holdout-1 0.929/0.571 | 2026-10-22 | `evaluate()` on `evals/incidents_dev.json`, `evals/incidents_holdout.json` |
| F7 | Diagnosis eval on fresh holdout-2 (12 cases), first run before any tuning: engine top-1 66.7%, baseline 75% — **the engine lost**. Causes: (a) the 0.3 confidence cut removed every moderate cause and even the generic 5xx fallback (3 misses → 'unclear'); (b) the loopback rule missed Flask's 'Running on http://127.0.0.1'. Holdout-2 is now used for tuning; the next unseen test is real incidents on the live demo app. | engine 0.667, baseline 0.75 | 2026-10-22 | `evaluate('evals/incidents_holdout2.json')` |
| F8 | The user's OpenAI-compatible LLM (a Qwen 27B model; gateway host kept private) does tool calling in the OpenAI format: one `list_apps` call for a Persian question in 1.1 s. Replies carry extra keys (`reasoning_content`, `provider_specific_fields`), which we ignore. | tool call OK, 1.1 s | 2026-10-23 | `ChatLLM.complete` with one tool |
| F9 | Real LLM on the demo scenario (simulated app). Before the prompt fix, 1 of 2 runs passed: once the model asked 'do you approve?' in text instead of calling the tool (a double confirmation). After telling it the system shows the card: 5/5 passed (diagnose first, only `set_env` approved, value masked, verify after fix, app fixed), median 12.6 s. | before 1/2, after 5/5 | 2026-10-23 | `uv run python evals/llm_scenario.py 5` → `results/llm-scenario.json` |
| F10 | `.env` still had the example Liara token (`fake-liara-token`), so Liara answered 401. `check` now says so plainly. | 401 | 2026-10-23 | `starcoach check` |
| F11 | Real plan catalog from `/v1/me`: 42 project plans. The cheapest available is `small-g2` (0.5 CPU, 0.5 GB RAM, 5 GB disk, `price` 659.72 Toman/hour → 474,998/month). Plan objects have no `region` key. Bundles are keyed by plan id; for `small-g2` the cheapest available is `basic` (`displayPrice` 275,000 per month); `free` is unavailable. Total ≈ 1,042 Toman/hour ≈ 750k/month, which matches the pricing page (research 04: Earth 750k). | as listed | 2026-10-23 | `LiaraClient.plans()` |
| F12 | `GET /v1/billing` returns `{user: {balance, minCreditAmount, ...}}` in Toman. The account balance was 284.91. Creating an app returned 402 'Not enough balance.' (our message: top up in the console). A create with a bad network id returns 400 'Invalid network id' (nothing created). | balance 285; 402; 400 | 2026-10-23 | `starcoach create shop ...`; `request('GET','/v1/billing')` |
| F13 | With the real LLM and the real Liara API (read-only), the agent quoted the plan-only hourly price (660) instead of plan + bundle (1,042). Fixed by giving `total_per_hour` / `total_per_month` in `recommend`. Re-run in the web UI: it quoted 749,998/month correctly. | 660 → 1,042 | 2026-10-23 | `starcoach chat --once ...`; web UI |
| F14 | Port 8765 is used by another local app on the dev machine, so the default web port is now 8790. | conflict | 2026-10-23 | `starcoach web` showed a different app |
