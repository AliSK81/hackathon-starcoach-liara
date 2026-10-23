# Roadmap — StarCoach, a Liara website assistant

## Goal
- An assistant that helps a website owner on Liara: set up, deploy, monitor, diagnose, fix.
- The user talks in plain words (Persian or English). The assistant does the infrastructure work.
- Safe by default: read-only actions run at once; risky actions wait for the user's "yes".
- Honest: when the Liara API cannot do something, the assistant says so.
- A runnable MVP that shows one real scenario end to end: a request, an operation, a diagnosis, a fix, a check.

## Rules for every phase
1. **Always keep it working.** Every commit runs and can be shown. Thin version first, then improve.
2. **Small patches.** One change = one idea. Many small commits beat one big one.
3. **Don't design ahead.** Plan only the phase you are starting.
4. **Measure, don't guess.** Limits, prices, formats, rules come from the real system. Write them as `F` facts with their source.
5. **Check results, not only code.** Before a phase is `done`, look at its real output and ask: does this meet the requirement, or earn the score? If an output looks odd or always the same, find out why. Fix it before the next phase.
6. **Test honestly.** Test on data you did not tune on. Compare with a simple baseline. Keep only what holds up. Record what failed too (as `F` facts).
7. **Log everything.** Every run, decision and error goes to an append-only log (JSONL) on disk. Save results to `results/`, so anyone can check them.
8. **Survive errors.** Long-running parts log the error and go on. They never crash on one bad input. They never record the same event twice after a failure.
9. **Every capability is a command.** One CLI subcommand per capability, so each one can be run and shown alone.
10. **Blocked? Don't wait.** If a change needs something from the user, add it to "What we need from the user", ask once, and work on the next unblocked phase.
11. **Tag what ships for real.** Any version used for the real thing gets a git tag.
12. **Clean as you go.** After a few changes, run a lint pass and small refactors as their own commits. Fix bugs found in real runs at once, with a test.

## Status

| Phase | Name | Status | Plan |
|---|---|---|---|
| 0 | The project runs | done | [phase-0](phases/phase-0-runs.md) |
| 1 | Connect to Liara (read-only) | done | [phase-1](phases/phase-1-connect.md) |
| 2 | Thin agent: chat that calls read-only tools | done | [phase-2](phases/phase-2-agent.md) |
| 3 | Deploy: recommend, create, deploy, release status | done | [phase-3](phases/phase-3-deploy.md) |
| 4 | Observe: logs, metrics, health probe | done | [phase-4](phases/phase-4-observe.md) |
| 5 | Diagnose and fix, with approval and re-check | done | [phase-5](phases/phase-5-diagnose.md) |
| 6 | Web chat UI: approval cards and status | done | [phase-6](phases/phase-6-web.md) |
| 7 | Automation: watch loop, domain guide | done | [phase-7](phases/phase-7-automation.md) |
| 8 | Reviewer doc, audit, tag | done | PROGRESS changes 19–20 |

## Requirement → phase

| Requirement or score item | Phase |
|---|---|
| Guide choice of deploy method and setup | 3 |
| Review project, suggest Liara platform and plan | 3 |
| Help with setup, config, deploy steps | 3 |
| Domain setup and registrar (IRNIC) steps | 7 |
| Simplify setup: user does only steps we cannot reach | 3, 7 |
| Publish new versions | 3 |
| Config and service management via Liara APIs | 1, 5 |
| Check service status, find deploy errors | 1, 3 |
| Automate repetitive operations | 7 |
| Health and CPU/RAM usage | 4 |
| Retrieve and analyze logs | 4, 5 |
| Investigate slowness, malfunction, high usage | 5 |
| Suggestions for performance and stability | 5 |
| Take corrective action or guide the fix | 5 |
| HTTP 500 troubleshooting: gather, check, rank causes, fix, verify | 5 |
| Human-in-the-loop: approval for sensitive actions, low vs high risk | 2, 5, 6 |
| Results and errors visible to the user | 2, 6 |
| Liara APIs used; limits disclosed to the user | 1, 2, 8 |
| UX: plain-language requests, status, suggestions, approvals | 2, 6 |
| Deliverable: runnable MVP with a real scenario | 5, 8 |
| Deliverable: MD doc (architecture, Liara API connection, limits, interaction) | 8 (started in 1) |
| Score 1 — Liara integration, deploy, service management, operations (100) | 1, 3, 5 |
| Score 2 — logs, errors, causes, solutions, checking fixes (100) | 4, 5 |
| Score 3 — simplicity, clear suggestions, status, approvals (50) | 2, 6 |
| Score 4 — monitoring, automation, secure handling, API limits (50) | 4, 7, 1 |

## Phases

### Phase 0 — The project runs
- **Why:** everything else needs a base that runs and tests offline.
- **Done when:**
  - `starcoach --help` works after one install command.
  - One offline test passes.
  - `.env` is gitignored. `.env.example` lists every name.
  - Every run writes a line to an append-only JSONL log.
  - README says how to install, run and test.
- **Not yet:** no Liara calls, no LLM.

### Phase 1 — Connect to Liara (read-only)
- **Why:** score 1 starts with a working API connection. Every later phase uses this client.
- **Done when:**
  - `starcoach check` proves the token works against the real API (account name, app count).
  - `starcoach apps` and `starcoach status <app>` show real data.
  - Errors (bad token, network, 4xx/5xx) show a clear message, never a stack trace.
  - The token never appears in logs or output.
  - A limits registry lists what the API cannot do.
- **Not yet:** no changes to apps.

### Phase 2 — Thin agent
- **Why:** the earliest end-to-end path: plain-language request → tool call → answer.
- **Done when:**
  - `starcoach chat` answers "what apps do I have and are they up?" with real data, in Persian or English.
  - Each tool has a risk tier. `change`/`danger` tools stop and ask for "yes".
  - Each tool call and its result show as status lines. All go to the JSONL log.
  - Offline tests use a scripted fake LLM.
- **Not yet:** no web UI. Only the tools from phase 1.

### Phase 3 — Deploy
- **Why:** setup and deploy are core of score 1 and the first expected capability.
- **Done when:**
  - `starcoach recommend <dir>` detects the platform and suggests a plan, with reasons.
  - `starcoach create` makes an app (after approval).
  - `starcoach deploy <dir> --app <name>` uploads, releases, shows build progress and the final state.
  - A failed build is detected and its cause is shown.
  - A real demo app is live on Liara and answers HTTP 200.
- **Not yet:** no domains, no auto-fix.

### Phase 4 — Observe
- **Why:** monitoring and log analysis feed scores 2 and 4.
- **Done when:**
  - `starcoach logs <app>` shows recent logs.
  - `starcoach metrics <app>` shows CPU and RAM against plan limits (or says it is not available).
  - `starcoach health <app>` probes the site URL and reports status code and latency.
- **Not yet:** no diagnosis rules.

### Phase 5 — Diagnose and fix
- **Why:** score 2 (100 points): causes, solutions, checking the fix.
- **Done when:**
  - `starcoach diagnose <app>` gathers evidence and returns ranked causes, each with evidence and a fix.
  - Fix actions (restart, set env, change plan, redeploy) run only after approval.
  - After a fix, the tool re-checks and reports "fixed" or "not fixed" with numbers.
  - A real broken demo app (HTTP 500) is diagnosed and fixed end to end.
  - Diagnosis rules are tested on log samples that were not used to write them.
- **Not yet:** no background watch.

### Phase 6 — Web chat UI
- **Why:** UX is 50 points. Non-technical users need a chat, not a terminal.
- **Done when:**
  - `starcoach web` serves a local chat page. Persian right-to-left text renders correctly.
  - Tool calls show live status. Sensitive actions show an approval card with Approve / Reject.
  - Results and errors are visible in the page.
- **Not yet:** no accounts or multi-user.

### Phase 7 — Automation and domains
- **Why:** automation and monitoring (score 4) and the domain requirement.
- **Done when:**
  - `starcoach watch` checks apps on a schedule, logs each check once, and alerts on change.
  - `starcoach domain <app> <domain>` adds the domain (if the API allows) and prints the exact registrar/IRNIC steps.
- **Not yet:** nothing from "Later".

### Phase 8 — Reviewer doc, audit, tag
- **Why:** the deliverables and judging depend on clear docs and a tagged version.
- **Done when:**
  - The reviewer doc covers architecture, Liara API connection, limits, and interaction, with real results.
  - A fresh clone runs from the README. All tests pass offline.
  - The line-by-line audit against requirements passes. The version is tagged.
- **Not yet:** —

## Later
- MCP server exposing the same tools.
- Rollback to an older release.
- Managed database checks.
- Telegram or email alerts from `watch`.
