# Phase 2 — Thin agent

## Goal
Plain-language request → tool calls on Liara → a clear answer. Risky tools wait for "yes".

## Choices
- LLM: the user's OpenAI-compatible provider (D3). `POST {LLM_BASE_URL}/chat/completions` with `tools`. Stdlib HTTP, swappable transport.
- One tool registry. Each tool has a name, a JSON schema, a risk tier (D6), and a function.
- The agent loop is synchronous. Approval is a callback: the CLI asks on the terminal; the web UI (phase 6) blocks on a click.
- Every step emits an event (`tool_start`, `tool_done`, `approval_needed`, `approved`, `rejected`, `error`, `answer`). The CLI prints them as status lines. All go to the JSONL log.
- What reaches the LLM is cleaned: env var values and account secrets are never sent (only env names).
- Max 8 LLM rounds per user message. A tool error goes back to the LLM as a result, not a crash.

## Checklist
- [x] `llm.py` chat client
- [x] `tools.py` registry with read tools: `list_apps`, `app_status`, `api_limits`; change tool: `restart_app`
- [x] `agent.py` loop with risk gate and events
- [x] `starcoach chat` (REPL) and `starcoach chat --once "..."`
- [x] offline tests with a scripted fake LLM (read tool, approval yes, approval no, tool error)
- [ ] real run with the user's LLM and token
