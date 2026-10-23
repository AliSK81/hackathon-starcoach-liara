# Phase 4 — Observe

## Goal
See what an app is doing: logs, CPU and RAM against plan limits, events, and how the site answers.

## Choices
- Logs: `GET /v2/projects/{app}/logs?start=<unix s>&direction=forward`. Flatten the streams, sort by time, decode `_entry` and `type` (research 03 §1.1). Bad lines are kept as raw text, never dropped silently.
- Events: `GET /v1/projects/{app}/events?start&end`, the same stream shape (03 §4).
- Metrics: `/metrics/cpu` and `/metrics/memory` with `since`. Units are undocumented, so we report raw values and our reading of them, and mark the reading `unverified` until an F fact confirms it (03 §2).
- Plan limits: join `planID` from the app with `/v1/me` plans.
- Health probe: our own HTTP GET to `https://<app>.liara.run` (or a given URL), N tries, status codes and latency (p50/max). No Liara API has this (03 §5).
- Each is a CLI command and a `read` agent tool.

## Checklist
- [x] `starcoach logs <app> [--minutes N] [--errors]`
- [x] `starcoach events <app>`
- [x] `starcoach metrics <app>`
- [x] `starcoach health <app|url> [--tries N]`
- [x] agent tools: `get_logs`, `get_events`, `get_metrics`, `probe_site`
- [x] offline tests with recorded-shape fixtures
- [x] real check of metric units on the demo app (F fact)
