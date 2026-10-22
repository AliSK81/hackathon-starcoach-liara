# Phase 7 — Automation and domains

## Goal
Watch apps without a human, and make custom domains easy, including the IRNIC steps.

## Choices
- `watch`: probe each app (3 tries) every N seconds. States: up, slow, degraded, down.
- Alert only when the state changes. State is saved atomically to `results/watch-state.json` **before** the alert is written to `results/alerts.jsonl`. A crash or restart never repeats an alert.
- When an app leaves "up", run the read-only diagnosis and put the likely cause in the alert.
- Auto-restart only with `--auto-restart` (the user opts in once). At most one restart per hour per app. Logged.
- One failing app or network error is logged; the cycle goes on.
- Domains: `POST /v1/domains`, `GET /v1/domains/{id}/check`, `POST /v1/domains/provision-ssl-certs` (research 04 B.3). Registrar steps (IRNIC for `.ir`, generic otherwise) come from research 04 B.5–B.6, in Persian and English. They are shown as the user's manual steps (API limit `registrar-outside`).

## Checklist
- [x] `watch.py` with dedupe, persistent state, diagnosis on failure, opt-in auto-restart with cooldown
- [x] `starcoach watch <apps...> [--interval --once --cycles --auto-restart]`
- [x] `domains.py`: list, add, check, SSL, guide
- [x] `starcoach domain <app> <domain> [--add --check --ssl]`
- [x] agent tools: `domain_guide` (read), `add_domain`, `enable_ssl` (change)
- [x] offline tests
- [ ] real watch run on the demo app
