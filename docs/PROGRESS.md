# Progress

## Status board

- **Current phase:** 1 — Connect to Liara (read-only)
- **Live / working:** `version`, `check`, `apps`, `status`, `limits` (offline-tested; not yet run against the real API: needs the token). 9 offline tests pass.

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
