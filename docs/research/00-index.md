# Research index

Research is a reference, not truth. Facts that code depends on are checked against the real system and recorded as `F` entries in `docs/DECISIONS.md`.

| File | Topic | Serves |
|---|---|---|
| [01-liara-api.md](01-liara-api.md) | Liara REST API: base URL, auth, apps, lifecycle, envs, settings, disks, domains, errors | Score 1 (integration, service management); limits disclosure (score 4) |
| [02-liara-deploy.md](02-liara-deploy.md) | Deploy without the CLI: pack, upload, release, build logs, states, liara.json, platforms, failures | Setup & deploy; publish new versions; deploy-error detection (score 1) |
| [03-liara-logs-metrics.md](03-liara-logs-metrics.md) | Logs (v2), metrics, applets, events, release states, health checks, missing HTTP metrics | Monitoring, log analysis (scores 2, 4) |
| [04-domains-plans.md](04-domains-plans.md) | Hardware plans and feature bundles, prices, custom domains, Liara DNS, IRNIC steps, SSL | Plan suggestion; domain setup and registrar guidance |
| [05-agent-design.md](05-agent-design.md) | Agent loop, approval pattern, risk tiers, audit log, MCP, Liara AI gateway, UX, offline testing | Human-in-the-loop, UX (score 3), secure handling (score 4) |
| [06-troubleshooting.md](06-troubleshooting.md) | Rule base of error signatures, slowness diagnosis, fix verification, cause scoring | Intelligent troubleshooting (score 2) |

## Consolidated design

1. Talk to `https://api.liara.ir` with `Authorization: Bearer <token>` (01, 02). Optional `teamID` query parameter for teams.
2. Use `GET /v1/me` as the connection test, but keep only the fields we need. It also returns personal data and storage keys (01).
3. Deploy without the Liara CLI: tar.gz → `POST /v2/projects/{app}/sources` → `POST /v2/projects/{app}/releases` → poll `GET /v2/releases/{id}/build-logs` until `READY` / `FAILED` / `UNHEALTHY` / `TIMEDOUT` / `CANCELED` (02).
4. Never upload `.env`. The CLI only skips it for Django/Flask (02 §2 step 3).
5. Plans come from `/v1/me` → `plans.projects` (hourly `price`, `RAM.amount`, `CPU.amount`) and `plans.projectBundlePlans` (02, 04). Only `g2` Iran plans are current (CLI filter).
6. Runtime logs: `GET /v2/projects/{app}/logs?start=<unix s>&direction=forward`, a Loki-like stream shape that must be flattened and sorted (03 §1.1).
7. Metrics: `/v1/projects/{app}/metrics/{cpu|memory}` and `/summary`. Units are undocumented. Plan limits must be joined from `/v1/me` (03 §2).
8. No HTTP metrics exist. We probe the site URL ourselves (03 §5).
9. Instance state from `/applets`; OOM and crash signals from `/events` (03 §3–4).
10. Lifecycle: restart `POST .../actions/restart`, on/off `POST .../actions/scale`, plan `POST .../resize`, envs `POST /v1/projects/update-envs` (replaces the whole set and restarts) (01).
11. No official rollback endpoint. Redeploy an old version instead (01, 02).
12. Diagnosis: deterministic rules with weighted evidence give ranked causes. The LLM explains them. A fix is verified by re-probing and re-reading logs (06 §3, §5, §6).
13. Approval is enforced in code, not in the prompt. Approval is tied to the exact arguments shown. Destructive actions need the app name typed (05).
14. Log text is untrusted input to the LLM (prompt injection). Keep it in tool results and never let it trigger mutating tools without approval (05 Q12).
15. Domains: `POST /v1/domains`, then `GET /v1/domains/{id}/check`, then `POST /v1/domains/provision-ssl-certs`. Registrar steps (IRNIC: nameservers `ns1.liara.zone`, `ns2.liara.zone`) are the user's manual steps (04).

## Conflicts and gaps

| Topic | Conflict or gap | How we check |
|---|---|---|
| Base URL | 01/02 say `api.liara.ir`; older CLI used `api.iran.liara.ir` | Both answer 401 without a token: F4. Confirm 200 with the token. |
| Error body shape | `{statusCode, message, data:{code}}` is inferred from CLI code | Capture the first real error body and record it as an F fact. |
| Logs | v1 (spec) and v2 (CLI) shapes differ | Use v2. Check one real response. |
| Metric units and `since` | Not documented | Call each endpoint once on the demo app and compare with known load. Record F facts. |
| Deploy limits per plan | CLI 10/50 per day vs docs 20/50/unlimited | Not needed for the MVP. A 428 is shown plainly. |
| Health-check units | ms (CLI prompts) vs seconds (docs example) | Not used in the MVP. |
| `envs` in the release body | May wipe existing envs | We do not send `envs` in releases. We use `update-envs` with a merged set. |
| `{id}` vs `{name}` in some routes | Spec mixes both | Test each route we use with the real app. |
| Free plan | Docs: no free credit; API still has a `free` plan | We never suggest the free plan (D7). |
| Rollback | Only an unofficial MCP shows a rollback endpoint | Listed as an API limit; redeploy instead. |
| Rate limits | Undocumented | Retry GET on 429/5xx with backoff. Polling ≤ 1 request/s per app. |
