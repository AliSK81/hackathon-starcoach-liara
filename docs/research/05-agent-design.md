# 05 - Agent design: tool-calling loop, approvals, MCP, UX, testing

Research date: 2026-10-22. Scope: how to build a Python assistant that deploys, manages, monitors and troubleshoots sites on Liara. It runs read-only actions on its own, asks the user before sensitive ones (restart, plan change, env change, delete), and shows the status of each operation.
Liara REST endpoints are covered in `01-liara-api.md`, deploy in `02-liara-deploy.md`, and logs/metrics in `03-liara-logs-metrics.md`. This file cites them where it needs to and does not repeat them.

Every claim has a source URL. Anything I could not confirm is marked **(unverified)** and repeated in the last section.

---

## 1. Existing Liara AI / MCP work

### 1.1 MCP servers for Liara (none official)

| Project | What it is | Notes |
|---|---|---|
| `razavioo/liara-mcp` (npm `liara-mcp` 1.1.0, TypeScript, MIT) | Unofficial MCP server for the Liara platform API | About 100 granular tools, e.g. `liara_list_apps`, `liara_restart_app`, `liara_resize_app`, `liara_set_env_vars`, `liara_get_logs`, `liara_get_metrics`, `liara_delete_app`. It also has a "consolidated" mode with 8 tools, enabled by `LIARA_MCP_CONSOLIDATED=true`. Env vars: `LIARA_API_TOKEN`, `LIARA_TEAM_ID`, `LIARA_API_BASE_URL` (the example uses `https://api.iran.liara.ir`). The README describes no confirmation, approval or dry-run features. Sources: https://github.com/razavioo/liara-mcp, https://raw.githubusercontent.com/razavioo/liara-mcp/main/README.md, https://registry.npmjs.org/-/v1/search?text=liara%20mcp&size=20 |
| `@iflow-mcp/razavioo-liara-mcp` 1.0.1 | Republished copy of the above | https://registry.npmjs.org/-/v1/search?text=liara%20mcp&size=20 |
| `SoroushMB/liara-docs-mcp` (TS) | MCP server over the Liara *documentation* (no API actions) | https://api.github.com/search/repositories?q=liara+mcp&per_page=30 |
| `SalehB1/Lira-mcp` (Python) | MCP server over the Liara docs: Persian/English search, deploy config, build-log diagnosis. The corpus is bundled and it needs no API key | same search URL |

- GitHub search for "liara mcp" returns only these 3 repos. https://api.github.com/search/repositories?q=liara+mcp&per_page=30
- The `liara-cloud` org has `cli`, `docs`, `openapi`, `desktop`, the `ai-*-examples` repos and the getting-started repos. None is an MCP server or an agent. https://api.github.com/orgs/liara-cloud/repos?per_page=100&sort=pushed
- PyPI has no `liara-mcp` package: https://pypi.org/pypi/liara-mcp/json returns 404.
- **What this means for us:** the field is open for a *safety-first* agent. The existing MCP server exposes destructive tools with no gating, so our risk tiers and approval flow set us apart. Its tool list is a good checklist of the API surface.

### 1.2 Liara AI service (OpenAI-compatible gateway)

- **What it is:** Liara "AIaaS" gives access to many providers' models through one API, including OpenAI, Google Gemini, xAI Grok, DeepSeek, Anthropic Claude, Meta Llama, Qwen, Kimi, GLM and Mistral. https://docs.liara.ir/ai/about/
- **OpenAI SDK compatible:** the Claude provider page says (in Persian) that every model Liara offers is compatible with the OpenAI SDK. Its examples use `from openai import OpenAI` with `base_url="<baseUrl>"` and `api_key="<LIARA_API_KEY>"`. https://docs.liara.ir/ai/anthropic-claude/ , https://docs.liara.ir/ai/openai/
- **Base URL format:** `https://ai.liara.ir/api/<workspaceID>/v1`, then `/chat/completions`.
  - Verbatim curl: `curl https://ai.liara.ir/api/682b7ab82bd70203933013ae/v1/chat/completions -H "Authorization: Bearer $LIARA_API_KEY"`. https://docs.liara.ir/ai/details/full-log-request/
  - The official example `.env` has `BASE_URL=https://ai.liara.ir/api/<id>/v1`. https://raw.githubusercontent.com/liara-cloud/ai-rerank-examples/nodejs/.env.example
  - The quick-start page shows a different order, `https://ai.liara.ir/api/v1/682833f68c7347b1c1612d00`. https://docs.liara.ir/ai/quick-start/ Treat that as a doc inconsistency and copy the baseUrl from the console.
  - The workspace ID is the segment after `ai/` in the console URL, e.g. `https://console.liara.ir/ai/682b7ab82bd70203933013ae/models`. https://docs.liara.ir/ai/details/id/
- **API key:** create it in Console -> AI -> Keys -> "Create key", scoped to one AI project. It is shown only once. Keys can be deactivated or deleted. https://docs.liara.ir/ai/quick-start/ , https://docs.liara.ir/ai/details/keys/
- **Model IDs** use the `provider/model` form:
  - OpenAI examples: `openai/gpt-4o-mini`, `openai/gpt-4.1`, `openai/gpt-5.4-mini`, `openai/gpt-5.5`. https://docs.liara.ir/ai/openai/
  - Claude examples: `anthropic/claude-sonnet-5.5`, `anthropic/claude-opus-5.5`, `anthropic/claude-haiku-4.5`. https://docs.liara.ir/ai/anthropic-claude/
  - Liara's own cookbooks use `openai/gpt-4o-mini`. https://docs.liara.ir/ai/getting-started/nodejs/
- **Tool calling:** the provider pages list `tools` and `tool_choice` as supported OpenAI-SDK parameters. The Python example defines a `summarize_text` function with `tool_choice="auto"`. They warn that some parameters may not be supported by some models. https://docs.liara.ir/ai/openai/ , https://docs.liara.ir/ai/anthropic-claude/
  - Liara has cookbooks for calling tools, parallel tool calls, multi-step tool calls and human-in-the-loop. https://docs.liara.ir/ai/cookbook/about/ , https://docs.liara.ir/ai/cookbook/nodejs/call-tools/ , https://docs.liara.ir/ai/cookbook/nextjs/human-in-the-loop/
  - Caveat: OpenAI says "GPT-6 Astra and GPT-6.1 Sol require the Responses API for tool calling". Do not choose `openai/gpt-6-*` for a Chat-Completions tool loop. https://developers.openai.com/api/docs/guides/function-calling
- **Billing:**
  - An AI *plan* is billed per hour or per month in Toman:
    - Mirzakhani: 825,000 T/month or 1,145 T/hour, 10 requests/s, 30-day log retention.
    - Turing: 1,475,000 T/month or 2,048 T/hour, 100 requests/s, 60-day log retention.
  - *Tokens* are billed on top "according to the model provider's tariff". https://liara.ir/pricing/
  - You can only use models included in your plan. https://docs.liara.ir/ai/quick-start/
  - The docs plans page gives 58 and 97 models per plan, while the pricing page gives 66 and 113. https://docs.liara.ir/ai/details/plans/
  - Each response's `usage` includes `total_cost_toman` and `cost` next to the token counts. The response `id` is a log ID that you can fetch later with `GET https://ai.liara.ir/v1/workspaces/<workspaceID>/logs/<logID>`. https://docs.liara.ir/ai/details/full-log-request/
  - We can show "this answer cost X Toman" in the UI.
- **Liara platform API** (deploy, restart and so on) is a separate API at `https://api.liara.ir` (the legacy host `https://api.iran.liara.ir` also works), with a Bearer token. See `01-liara-api.md`.

---

## 2. Tool-calling agent loop with human-in-the-loop approval

### 2.1 Wire formats (what the loop must handle)

**OpenAI-compatible Chat Completions.** This is what the Liara gateway speaks. Reference: https://developers.openai.com/api/docs/api-reference/chat

- Request: `tools: [{type:"function", function:{name, description, parameters (JSON Schema), strict}}]`, `tool_choice: "none"|"auto"|"required"|{type:"function",function:{name}}`, and `parallel_tool_calls: bool`.
- Response: `choices[0].message.tool_calls[] = {id, type:"function", function:{name, arguments}}`. `arguments` is a **JSON string**, and the model "does not always generate valid JSON", so validate it before calling anything. `finish_reason` is one of `stop`, `length`, `tool_calls` or `content_filter`.
- Result: append the assistant message unchanged, then one `{role:"tool", tool_call_id, content}` per call.
- Setting `parallel_tool_calls` to false "ensures exactly zero or one tool is called" per turn. https://developers.openai.com/api/docs/guides/function-calling

**Anthropic Messages API.** Optional direct path. https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview , https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls

- The response has `stop_reason: "tool_use"` and content blocks `{type:"tool_use", id, name, input}`. `input` is already an object.
- Reply with a `user` message whose content starts with `{type:"tool_result", tool_use_id, content, is_error?}` blocks.
- "Tool result blocks must immediately follow their corresponding tool use blocks", and `tool_result` blocks "must come FIRST in the content array".
- Use `is_error: true` for failures, and write instructive error text.
- `tool_choice={"type":"auto","disable_parallel_tool_use":True}` limits each turn to one tool call. The model ID is `claude-opus-5-5`, from the overview page's examples.
- Tool results are untrusted input. Keep them inside `tool_result` blocks because of indirect prompt injection, which matters for us since app logs are attacker-controllable. https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls

**Key constraint in both APIs:** every tool call in an assistant turn needs a matching result before the next model request. So "pause for approval" means *stopping the loop between the assistant turn and the tool results*. You save the state and resume later by appending the results: the real result if approved, or a "user declined" error result if rejected.

### 2.2 Minimal pattern: pause and resume with persisted run state (raw httpx, no framework)

```python
# agent/loop.py  - provider: Liara AI gateway (OpenAI-compatible)
import json, os, uuid, httpx
BASE = os.environ["LIARA_AI_BASE_URL"]        # https://ai.liara.ir/api/<workspaceID>/v1
KEY  = os.environ["LIARA_AI_API_KEY"]
MODEL = os.getenv("LIARA_AI_MODEL", "openai/gpt-4o-mini")

class LLM:                                    # swap with FakeLLM in tests (section 6)
    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(base_url=BASE, timeout=60,
                                           headers={"Authorization": f"Bearer {KEY}"})
    def chat(self, messages, tools) -> dict:
        r = self.http.post("/chat/completions", json={
            "model": MODEL, "messages": messages, "tools": tools,
            "tool_choice": "auto", "parallel_tool_calls": False})
        r.raise_for_status()
        return r.json()

def step(run: dict, llm: LLM, registry, emit) -> dict:
    """Advance a run until it finishes or needs approval. `run` is plain JSON (persist it)."""
    while True:
        resp = llm.chat(run["messages"], registry.openai_schemas())
        msg = resp["choices"][0]["message"]
        run["messages"].append(msg)                       # keep tool_calls verbatim
        calls = msg.get("tool_calls") or []
        if not calls:
            emit("assistant_message", {"text": msg.get("content", "")})
            run["status"] = "done"; return run
        for call in calls:
            tool = registry.get(call["function"]["name"])    # unknown -> error result
            args = json.loads(call["function"]["arguments"] or "{}")  # validate! (pydantic)
            if tool.needs_approval(args):
                preview = tool.dry_run(args)              # what WOULD change (section 4)
                run["pending"] = {"call_id": call["id"], "tool": tool.name, "args": args,
                                  "preview": preview, "nonce": uuid.uuid4().hex}
                run["status"] = "awaiting_approval"
                emit("approval_required", run["pending"]); return run   # <-- PAUSE
            run["messages"].append(execute(tool, call["id"], args, emit))

def resume(run: dict, decision: str, nonce: str, llm, registry, emit) -> dict:
    p = run["pending"]; assert nonce == p["nonce"], "stale approval"   # bind approval to exact args
    tool = registry.get(p["tool"])
    if decision == "approve":
        run["messages"].append(execute(tool, p["call_id"], p["args"], emit))
    else:
        run["messages"].append({"role": "tool", "tool_call_id": p["call_id"],
            "content": "DECLINED by user. Do not retry; offer alternatives."})
    run["pending"] = None; run["status"] = "running"
    return step(run, llm, registry, emit)                  # <-- RESUME

def execute(tool, call_id, args, emit) -> dict:
    emit("tool_started", {"tool": tool.name, "args": tool.redact(args)})
    try:
        out = tool.run(**args); ok = True
    except Exception as e:                                  # becomes a tool error result
        out = f"ERROR: {e}"; ok = False
    emit("tool_finished", {"tool": tool.name, "ok": ok, "summary": str(out)[:500]})
    return {"role": "tool", "tool_call_id": call_id, "content": json.dumps(out, ensure_ascii=False)}
```

Design notes:

- `parallel_tool_calls: False` (OpenAI) and `disable_parallel_tool_use` (Anthropic) give at most one call per turn. That keeps "one pending approval" trivially correct. Without it, you must run the auto-approved calls, hold the risky ones, and still return *all* results together before the next request. Sources: https://developers.openai.com/api/docs/guides/function-calling , https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview
- The run state is plain JSON (messages plus pending call), so pausing is just "save to disk/SQLite and return HTTP 200". The process can even restart between approval and resume.
- The approval gate lives in **code** (`needs_approval`), not in the prompt. OWASP LLM06 (Excessive Agency) says to "require a human to approve high-impact actions" and to enforce authorization in downstream systems rather than "relying on an LLM to decide if an action is allowed". https://genai.owasp.org/llmrisk/llm062025-excessive-agency/
- The nonce binds the approval to the exact `(tool, args)` shown on the card, so the model cannot swap arguments after approval.
- A Liara cookbook shows the same pause/resume idea in the Vercel AI SDK: tools without auto-execution, Yes/No buttons, and the server runs the tool or returns "user denied". https://docs.liara.ir/ai/cookbook/nextjs/human-in-the-loop/ . The upstream AI SDK now has `needsApproval: true` with `addToolApprovalResponse`. https://ai-sdk.dev/cookbook/next/human-in-the-loop
- **Anthropic variant:** use the same `step`/`resume`, but switch on `stop_reason == "tool_use"`. Append `{"role":"assistant","content": resp.content}`, then reply with `{"role":"user","content":[{"type":"tool_result","tool_use_id":id,"content":..., "is_error": declined}]}`. https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls . The Anthropic SDK's tool runner also supports approval gates: gate inside the tool function, or inspect the call before it runs. https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner . We do not need it, because Claude models are reachable through the Liara gateway in OpenAI format (`anthropic/claude-sonnet-5.5`). https://docs.liara.ir/ai/anthropic-claude/
- **SDK vs raw httpx:** the `openai` Python SDK works against Liara (`OpenAI(base_url=..., api_key=...)`). https://docs.liara.ir/ai/openai/ . But the current `openai` and `anthropic` SDKs are now built on **httpx2**, not httpx. https://github.com/openai/openai-python , https://github.com/anthropics/anthropic-sdk-python/blob/main/MIGRATION.md . That affects mocking (section 6). For one endpoint, raw `httpx` is about 15 lines and easy to fake.

---

## 3. MCP: exposing the same tools as an MCP server (Python)

### 3.1 Package and API (version gotcha)

- Install: `pip install "mcp[cli]"`. https://github.com/modelcontextprotocol/python-sdk
- Latest PyPI version is `mcp` 2.3.0 (requires Python >=3.10). The last 1.x release is 1.30.0 (2026-09-07). https://pypi.org/pypi/mcp/json
- **In v2, `FastMCP` was renamed `MCPServer`.**
  - v1: `from mcp.server.fastmcp import FastMCP`.
  - v2: `from mcp.server.mcpserver import MCPServer, Context`. The quickstart also shows `from mcp.server import MCPServer`.
  - There is no `FastMCP` alias in v2: importing `mcp.server.fastmcp` raises `ModuleNotFoundError`. Pin `mcp<2` if you follow older tutorials.
  - Transport options moved to `run()`, e.g. `mcp.run(transport="streamable-http", host=..., port=...)`.
  - https://py.sdk.modelcontextprotocol.io/migration/ , https://py.sdk.modelcontextprotocol.io/
- Tools are registered with `@mcp.tool()`. The function name becomes the tool name and the docstring the description. In v2, annotations use `from mcp.types import ToolAnnotations` with snake_case fields, e.g. `ToolAnnotations(read_only_hint=True, open_world_hint=False)`. https://py.sdk.modelcontextprotocol.io/servers/tools/

```python
# mcp_server.py - thin adapter over the SAME registry used by the web agent
from mcp.server.mcpserver import MCPServer          # v2; for mcp<2: from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from liara_tools import registry, approvals

mcp = MCPServer("liara-starcoach")

@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
def get_app_logs(app: str, since_minutes: int = 30) -> str:
    """Read recent logs of a Liara app (read-only)."""
    return registry.get("get_app_logs").run(app=app, since_minutes=since_minutes)

@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False))
def restart_app(app: str, confirm_token: str | None = None) -> str:
    """Restart a Liara app (causes brief downtime). Call WITHOUT confirm_token first to get a
    preview and a token; show the preview to the user; call again with the token only after
    the user explicitly agrees."""
    if confirm_token is None:
        return approvals.issue("restart_app", {"app": app})      # preview + one-time token
    approvals.consume(confirm_token, "restart_app", {"app": app})   # raises if invalid/expired
    return registry.get("restart_app").run(app=app)

if __name__ == "__main__":
    mcp.run()   # stdio default (unverified for v2 - section 7); or mcp.run(transport="streamable-http", port=9000)
```

### 3.2 How MCP clients handle approval

- **Spec:**
  - "there SHOULD always be a human in the loop with the ability to deny tool invocations". Applications SHOULD "Present confirmation prompts to the user for operations".
  - Clients SHOULD "Prompt for user confirmation on sensitive operations", "Show tool inputs to the user before calling the server" and "Log tool usage for audit purposes".
  - Tool execution failures go back in the result with `isError: true`. Protocol errors are JSON-RPC errors.
  - https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- **Annotations are hints only:** `readOnlyHint` (default false), `destructiveHint` (default true, meaningful only if not read-only), `idempotentHint` (default false) and `openWorldHint`. Clients "MUST consider tool annotations to be untrusted unless they come from trusted servers". https://modelcontextprotocol.io/specification/2025-06-18/schema , https://modelcontextprotocol.io/specification/2025-06-18/server/tools
  - The latest spec (2026-07-28) says: "Hosts must obtain explicit user consent before invoking any tool". https://modelcontextprotocol.io/specification/latest
- **Claude Code** (one concrete client):
  - Its permission rules name MCP tools as `mcp__<server>__<tool>`, or `mcp__<server>__*` for a whole server. Users can allow-list the read-only tools and leave the rest on "ask".
  - It asks before using project-scoped servers from `.mcp.json` in interactive sessions.
  - It does not prompt in `claude -p` / Agent SDK runs.
  - https://code.claude.com/docs/en/permissions , https://code.claude.com/docs/en/mcp
  - **So a server cannot rely on the client asking.**
- **Elicitation** (a server asking the user mid-call):
  - The spec defines `elicitation/create` with accept/decline/cancel. Servers "MUST NOT use elicitation to request sensitive information". https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation
  - The Python SDK has `await ctx.elicit(message=..., schema=PydanticModel)`, which returns `result.action`. The client must register an `elicitation_callback`, or the call fails with a protocol error.
  - In the v2 SDK it works only on "legacy" connections (spec 2025-11-25 or earlier). On 2026-07-28 connections these calls fail.
  - https://py.sdk.modelcontextprotocol.io/handlers/elicitation/
  - **Too fragile to be the only approval mechanism.**
- **Recommendation:** enforce approval *in the server*, with the **two-step confirm token** shown above. It works with every client: the first call returns a preview and a token, and only a second call with the token mutates. Also set honest annotations so that good clients can add their own prompt. This mirrors the code-level gate in section 2.

---

## 4. Risk classification, audit log, idempotency, dry-run

### 4.1 Risk tiers (enforced in the tool registry, default-deny)

| Tier | Policy | Examples (Liara) | Basis |
|---|---|---|---|
| `READ` | Run automatically; show in the status timeline | list apps, app details/status, logs, metrics (CPU/RAM), list releases, plans/prices (`GET /v1/me`), DNS/domain read, HTTP health check of the site | HTTP GET is "safe" (read-only) by definition: https://www.rfc-editor.org/rfc/rfc9110#section-9.2.1 ; MCP `readOnlyHint` (https://modelcontextprotocol.io/specification/2025-06-18/schema) |
| `SAFE_WRITE` | Run automatically with a visible notice, or optionally ask | create a DB backup, add a DNS record that doesn't exist yet, *start* a stopped app | additive changes, `destructiveHint=false` (same schema URL) |
| `MUTATING` | **Approval required**; show a preview card | restart, deploy/redeploy, rollback, env set/unset (which replaces the full set and **restarts the app**, see `01-liara-api.md`), plan resize (**cost change**), scale, add/remove domain, toggle zero-downtime | requirements.md HITL section; OWASP LLM06 "require a human to approve high-impact actions" https://genai.owasp.org/llmrisk/llm062025-excessive-agency/ |
| `DESTRUCTIVE` | **Approval plus typed confirmation** (user types the app name); never auto | delete app/DB/disk/bucket, restore backup over live data, stop app | MCP `destructiveHint=true`; same OWASP page |

Rules:

- Every tool declares its tier. Unknown tools or tiers are treated as `DESTRUCTIVE`.
- Tiers can be argument-dependent: `scale(replicas=0)` counts as `DESTRUCTIVE`, and a plan *upgrade* also carries the cost flag.
- Add orthogonal flags: `causes_downtime`, `changes_cost`, `irreversible`. The card shows them as plain-language badges.
- Least privilege: offer only the tools needed. OWASP calls this "Minimize extensions" and "Minimize permissions". https://genai.owasp.org/llmrisk/llm062025-excessive-agency/

### 4.2 Audit log: append-only JSONL

- Format: one JSON object per line (JSON Lines). https://jsonlines.org/ (unverified: not re-fetched)
- Write one event per state change: `requested -> approved|declined -> started -> succeeded|failed`. Example:
  `{"ts":"2026-10-22T10:01:02Z","run_id":"...","call_id":"call_1","actor":"agent","approver":"user","tool":"restart_app","tier":"MUTATING","args":{"app":"shop"},"event":"approved","nonce":"...","result":null,"error":null,"duration_ms":null,"prev_hash":"sha256:..."}`
- Implementation: open with `open(path, "a", encoding="utf-8")`, write `json.dumps(ev, ensure_ascii=False) + "\n"`, then `flush()` and `os.fsync()`. Never rewrite the file.
- Optional `prev_hash` chain: each line stores the SHA-256 of the previous line, which makes tampering evident. Show "Activity log" in the UI straight from this file.
- **Redaction:** never log the Liara token, env var *values* (log keys plus a masked value), or the shell WebSocket URL (it carries the token). See `01-liara-api.md`.
- The OWASP Logging Cheat Sheet covers what to log and not log (secrets, tokens). https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html (unverified: not re-fetched)
- Both the MCP spec ("Log tool usage for audit purposes", https://modelcontextprotocol.io/specification/2025-06-18/server/tools) and OWASP LLM06 ("Log and monitor the activity of LLM extensions", https://genai.owasp.org/llmrisk/llm062025-excessive-agency/) call for this.

### 4.3 Idempotency

- Pattern from Stripe: the client generates a unique key per operation, and the server saves the first response and returns it on retries. Reusing a key with *different* params is an error. GET/DELETE are idempotent by definition. https://docs.stripe.com/api/idempotent_requests
- Liara's API does not advertise idempotency keys (unverified; see `01-liara-api.md`), so we implement them **client-side**:
  - `idem_key = sha256(run_id + call_id + tool + canonical_json(args))`.
  - Keep an `executed` table in SQLite or JSONL. If the key is already present, return the stored result instead of calling Liara again. This protects against double-clicks on Approve, SSE reconnect replays and LLM retries.
- **Check-before-act** (desired state):
  - `set_env` reads current envs first. If the values already match, it returns "no change" and skips the restart.
  - `resize` to the current plan is a no-op.
  - De-duplicate env keys before the full-replace POST (`01-liara-api.md`).
- Treat Liara `409 "Another operation is already running"` as "wait and poll", not "retry blindly" (`01-liara-api.md`).

### 4.4 Dry-run and preview

- Kubernetes defines the model to copy: `?dryRun=All` runs validation but "will not be persisted in storage or have any other side effects", and returns a body "as close as possible to a non-dry-run response". https://kubernetes.io/docs/reference/using-api/api-concepts/#dry-run
- Terraform's `plan` -> `apply` split is the same idea for infra. https://developer.hashicorp.com/terraform/cli/commands/plan (unverified: not re-fetched)
- Liara has no documented dry-run (unverified), so every `MUTATING`/`DESTRUCTIVE` tool implements `dry_run(args)` by **reading current state and computing a diff**. Its output is the approval card:
  - env: `+ NEW_KEY`, `~ DB_URL (value changed)`, `- OLD_KEY`, plus "the app will restart".
  - resize: `plan g2-small -> g2-medium`, RAM/CPU before -> after, price/hour (Toman) before -> after, from `GET /v1/me` -> `plans` (`01-liara-api.md`).
  - restart: current status, last deploy time, "expected downtime: a few seconds unless zero-downtime is on".
  - delete: the resources that will disappear, and the "type the app name" field.
- **Verify after act**, which the judging criteria call "Checking the result of corrective actions" (requirements.md). After any mutation:
  - Poll app status until it is running, or time out.
  - Make an HTTP GET to the site URL and check the status code.
  - Re-read logs and metrics for the error signature.
  - Report "fixed / not fixed" with the evidence.

---

## 5. Simple UX for non-technical users

### 5.1 Minimal stack: FastAPI + plain HTML/JS + SSE

- FastAPI has **built-in SSE** since 0.135.0: `from fastapi.sse import EventSourceResponse, ServerSentEvent`. "use `yield` in your path operation function and set `response_class=EventSourceResponse`". https://fastapi.tiangolo.com/tutorial/server-sent-events/
- The browser side is `EventSource`:
  - `evtSource.addEventListener("<event>", ...)` handles named events.
  - The stream fields are `event`, `data`, `id` and `retry`.
  - The browser reconnects automatically.
  - Over HTTP/1.1 the browser allows only 6 SSE connections per domain, so use one stream per run and close it when done.
  - https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events

Endpoints:

```
POST /api/runs                      {text}            -> {run_id}   (starts step() in a background task)
GET  /api/runs/{id}/events          SSE: assistant_message | tool_started | tool_finished |
                                         approval_required | run_finished | error
POST /api/runs/{id}/approval        {nonce, decision: approve|decline, typed_name?} -> 202
GET  /api/audit?run_id=...          JSONL lines for the "Activity" panel
```

```python
from fastapi import FastAPI
from fastapi.sse import EventSourceResponse, ServerSentEvent
app = FastAPI()

@app.get("/api/runs/{run_id}/events", response_class=EventSourceResponse)
async def events(run_id: str):
    async for ev in bus.subscribe(run_id):          # asyncio.Queue per run
        yield ServerSentEvent(event=ev["type"], data=ev["data"], id=str(ev["seq"]))
```

```html
<script>
const es = new EventSource(`/api/runs/${runId}/events`);
es.addEventListener("tool_started",  e => addStep(JSON.parse(e.data), "running"));
es.addEventListener("tool_finished", e => markStep(JSON.parse(e.data)));
es.addEventListener("approval_required", e => showApprovalCard(JSON.parse(e.data)));
es.addEventListener("run_finished", () => es.close());
</script>
```

- Number the events (`id: seq`) and keep the last N per run. A reconnecting client then gets missed events replayed instead of losing an approval card. The SSE `id` field sets the last event ID (MDN page above). For the `Last-Event-ID` resend header, see the open questions.

### 5.2 Approval card and status design

- **Card content:** a title in plain Persian ("Restart site *shop*?"), what will happen, the side effects as badges (downtime, cost change with Toman/hour delta, irreversible), the dry-run diff, the evidence that led to the suggestion ("logs show `OOMKilled` 4 times in 10 min"), and the buttons **Approve** and **Reject**.
- For `DESTRUCTIVE`, Approve stays disabled until the user types the app name.
- Disable both buttons after one click (idempotency, 4.3).
- **Status timeline:** each tool call is a row with an icon (read / change / danger), a plain-language label ("Reading last 30 min of logs..."), a spinner, then a check or cross and a one-line result.
- These match the MCP spec's UI guidance: "Insert clear visual indicators when tools are invoked" and present confirmation prompts. https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- **Limitations disclosure:** when an operation is not available through the API (e.g. registrar/IRNIC steps), the agent returns a "you need to do this manually" card with numbered steps. The judging criteria include "Disclosure of API limitations" (requirements.md).
- **Prior art:**
  - The Vercel AI SDK HITL cookbook, with approve/deny buttons on `approval-requested` tool state. https://ai-sdk.dev/cookbook/next/human-in-the-loop
  - Liara's own copy of it. https://docs.liara.ir/ai/cookbook/nextjs/human-in-the-loop/
  - Claude Code's permission prompts, which show the action and Yes/No with an optional comment. https://code.claude.com/docs/en/permissions
- RTL: `<html lang="fa" dir="rtl">`, with a Vazirmatn font (or a system font). No build step.

---

## 6. Offline testing of the agent

1. **Fake LLM (scripted responses).** `FakeLLM.chat()` pops prepared Chat-Completions responses from a list, matching the shape in https://developers.openai.com/api/docs/api-reference/chat. It can also assert on the `messages` it receives, e.g. that the tool result for `call_1` is present.
   - Scenario test, "site returns 500":
     1. The script calls `get_app_logs`, then `get_app_metrics`, then `restart_app`.
     2. Assert `approval_required` fires with `restart_app`.
     3. Call `resume(approve)`.
     4. Assert the Liara mock received `POST /v1/projects/shop/actions/restart`.
     5. Assert that verification (status poll + HTTP check) ran and the final message says "fixed".
   - A second test declines and asserts that no POST was sent and the model saw `DECLINED`.
2. **Mock Liara and the LLM at the HTTP layer with `httpx.MockTransport`.** `httpx.MockTransport(handler)` maps a `Request` to a `Response`. Inject it with `httpx.Client(transport=transport)`. Transports can also be mounted per domain. https://www.python-httpx.org/advanced/transports/
   - Because our `LLM` and `LiaraClient` take an `httpx.Client`, tests pass a client with a MockTransport, with no patching.
   - The same trick works for the LLM, to test real JSON parsing of `tool_calls`, malformed `arguments`, and 429/5xx handling.
3. **respx** (route-based mocking for httpx): `@respx.mock` and `respx.post(url).mock(return_value=httpx.Response(...))`. It requires HTTPX 0.25+. https://lundberg.github.io/respx/
   - **Gotcha:** the current `openai` and `anthropic` SDKs use **httpx2**, and respx/pytest-httpx/vcrpy "can silently fail" against them. The workaround is `httpx2.alias_httpx()` in an early pytest plugin. https://github.com/anthropics/anthropic-sdk-python/blob/main/MIGRATION.md , https://github.com/openai/openai-python
   - Raw `httpx` for our own clients avoids this entirely.
4. **Recorded fixtures.** Hit the real Liara API once with a throwaway app. Save the JSON bodies to `tests/fixtures/liara/*.json` with tokens, IDs and env values redacted, and serve them from the MockTransport handler. Re-record when the API changes.
   - The fixtures double as a **demo mode** (`LIARA_FAKE=1`), so the 5-minute video does not depend on network luck. The video must still show real Liara operations for the judging points (requirements.md).
5. **Cost-free prompt checks.** Keep a tiny suite of 5-10 real-LLM "golden" conversations, run manually before the demo. Check that the model picks read tools before mutating ones, and never calls a `DESTRUCTIVE` tool without prior evidence. Each run's `usage.total_cost_toman` shows the cost. https://docs.liara.ir/ai/details/full-log-request/

---

## Recommended minimal architecture

```
Browser (HTML/JS, RTL)  --POST /api/runs-->  FastAPI  --step()/resume()-->  Agent loop (raw httpx)
   ^  SSE events / approval cards              |                               |  OpenAI-format
   |                                           |                               v
   +------------- POST /approval --------------+                     Liara AI gateway
                                               |                     https://ai.liara.ir/api/<ws>/v1
                                    Tool registry (tiers, dry_run, verify, redact)
                                               |                \
                                     LiaraClient (httpx)         audit.jsonl (append-only)
                                     https://api.liara.ir        + executed-keys (idempotency)
                                               |
                                    mcp_server.py (MCPServer adapter, confirm-token tools)
```

- **One tool registry** is the single source of truth: schema, tier, `dry_run`, `run`, `verify` and `redact`. Three thin adapters sit on top of it: OpenAI tool schemas for the web agent, MCP for Claude Code/Desktop, and the Anthropic format as an optional extra.
- **LLM:** the Liara AI gateway over Chat Completions with `parallel_tool_calls=false`. Model: `anthropic/claude-sonnet-5.5` or `openai/gpt-5.4-mini` as a cheaper option. Confirm both are in the purchased plan.
- **Gate in code**, bind approvals to the exact arguments, run dry-run before and verify after, and audit every step.

---

## Unverified / open questions

1. **Liara AI base URL order.** The quick-start shows `https://ai.liara.ir/api/v1/<id>`, but the curl docs and example `.env` show `https://ai.liara.ir/api/<id>/v1`. Copy the value from the console and test both. Sources: https://docs.liara.ir/ai/quick-start/ , https://docs.liara.ir/ai/details/full-log-request/
2. **Tool calling per model on the gateway.** The docs say some parameters "may not be supported in some models". We have not tested `tools`, `tool_choice` or `parallel_tool_calls` end-to-end through Liara for `anthropic/claude-sonnet-5.5` or `openai/gpt-5.4-mini`. Run one curl per candidate model before committing.
3. **Is `GET <baseUrl>/models` exposed?** Not documented. The model list came from the provider doc pages.
4. **Plan model counts disagree:** 58/97 in the docs vs 66/113 on the pricing page. We do not know which models each plan includes, or how token charges are deducted (wallet vs plan).
5. **Liara platform API.** We found no idempotency-key header, no dry-run, and no published rate limits. Whether `resize` restarts the app or causes downtime is also unknown (see `01-liara-api.md`).
6. **MCP Python SDK v2:**
   - The quickstart imports `from mcp.server import MCPServer`, while the migration guide uses `from mcp.server.mcpserver import MCPServer`. Check which works in 2.3.0.
   - The default `mcp.run()` transport (stdio) and the `annotations=` keyword on `@mcp.tool()` in v2 were not shown verbatim. The docs show `ToolAnnotations(read_only_hint=...)` but not the decorator keyword.
   - v1's `ToolAnnotations` field casing (camelCase `readOnlyHint`?) was not checked.
7. **MCP elicitation** in v2 works only on legacy (≤2025-11-25) connections. We have not checked how the 2026-07-28 spec replaces mid-call user input (the "Tasks" extension mentions "mid-flight input"). We also have not checked which clients (Claude Desktop, Cursor) support elicitation today.
8. **Claude Code and `readOnlyHint`:** it is not documented whether Claude Code auto-approves MCP tools that carry it. We assume no and rely on allow-rules plus the server-side confirm token.
9. **httpx2 vs respx/MockTransport.** It is unconfirmed whether `httpx2` ships `MockTransport` or whether respx supports httpx2. This only matters if we use the official SDKs; raw `httpx` avoids it.
10. **Not re-fetched this session** (cited from known stable URLs): jsonlines.org, OWASP Logging Cheat Sheet, Terraform `plan` docs, and RFC 9110 §9.2.1. The claims drawn from them are standard, but the exact wording was not checked.
11. **SSE `Last-Event-ID` resume:** MDN's page does not describe the header. The behaviour comes from the SSE spec and has not been tested with FastAPI's `EventSourceResponse`.
12. **Prompt injection through logs.** App logs are attacker-controllable and flow into tool results. The mitigations (results kept in tool messages, code-level gating, no auto-run of mutating tools) are designed but not red-teamed.
