# Phase 6 — Web chat UI

## Goal
A simple, Persian-first chat page. You see each step live, and you approve risky steps with a click.

## Choices
- Stdlib `http.server` (threaded) and server-sent events. No web framework (fewest libraries).
- One agent per browser session. `agent.ask` runs in a worker thread. Events are kept in a numbered history; each SSE connection replays from its last id (`Last-Event-ID`), so a reconnect or reload never loses events and the page rebuilds the conversation.
- Approval cards: the server makes a single-use id for the exact tool and arguments shown (research 05). Approve or reject by id. `danger` tools also need the app name typed. No answer within 10 minutes counts as reject.
- Page: RTL, Vazirmatn font, a timeline of status lines, a card per approval, quick-start buttons for common requests, plain-text rendering (no HTML from the model or logs is injected).
- Local only: binds to `127.0.0.1` by default.

## Checklist
- [x] `web.py` server: `/`, `/api/chat`, `/api/events` (SSE), `/api/approve`
- [x] approval registry with single-use ids and typed-name check
- [x] `static/index.html`: chat, timeline, approval cards, quick buttons, RTL
- [x] `starcoach web [--port]`
- [x] offline tests: approval flow through HTTP with a scripted LLM
- [x] look at it in a browser
