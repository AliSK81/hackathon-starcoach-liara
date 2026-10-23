# Phase 1 — Connect to Liara (read-only)

## Goal
A tested API client. Real read-only commands. Clear errors. A list of API limits.

## Choices
- HTTP with stdlib `urllib`. It works through the dev machine's proxy (F2). No new library.
- The transport is a plain function, so tests swap it for a fake. No network in tests.
- Base URL `https://api.liara.ir`, the official CLI default (F4). Bearer token (research 01/02).
- GET retries on 429 and 5xx, twice, with a short backoff. Mutating calls never retry.
- Each call is logged: method, path, status, milliseconds. Never headers or bodies with secrets.
- `/v1/me` holds personal data. We show only the full name, and never log the body.
- Limits live in one registry (`limits.py`). The CLI and later the agent read it.

## Checklist
- [x] `LiaraClient` with errors mapped to plain messages
- [x] `starcoach check` — token works, account name, app count
- [x] `starcoach apps` — table of apps
- [x] `starcoach status <app>` — app state and instances
- [x] `starcoach limits` — what the API cannot do
- [x] offline tests with a fake transport
- [x] real run with the user's token
