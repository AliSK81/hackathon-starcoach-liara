"""The agent loop: LLM ↔ tools, with a risk gate and visible status events."""

from __future__ import annotations

import json
from typing import Callable

from .tools import READ, Tool

SYSTEM_PROMPT = """You are StarCoach, a friendly assistant for websites hosted on Liara (liara.ir).
The user may not be technical. Reply in the user's language (Persian by default if unsure).
Use short sentences and plain words. Explain technical terms briefly.

Rules:
- Use tools to get facts. Never invent app names, numbers, logs or results.
- Tools marked [risk: change] or [risk: danger] are only run after the user approves; the system asks them.
  Before calling one, say in one line what it will do and why.
- If a tool returns an error or "rejected", tell the user plainly and suggest the next step.
- If the user asks for something the Liara API cannot do, call api_limits and say so honestly,
  then tell them the exact manual steps.
- When you diagnose, list probable causes in order, with the evidence for each, and a fix.
- Never claim an action succeeded unless a tool result shows it.
"""

Event = Callable[[str, dict], None]
Approver = Callable[[Tool, dict], bool]


class Agent:
    def __init__(self, llm, tools: dict[str, Tool], approver: Approver,
                 on_event: Event | None = None, log=None, max_rounds: int = 8):
        self.llm = llm
        self.tools = tools
        self.approver = approver
        self.on_event = on_event or (lambda kind, data: None)
        self.log = log
        self.max_rounds = max_rounds
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def emit(self, kind: str, **data):
        if self.log is not None:
            self.log.write(f"agent.{kind}", **data)
        self.on_event(kind, data)

    def ask(self, text: str) -> str:
        self.messages.append({"role": "user", "content": text})
        self.emit("user", text=text)
        schemas = [t.schema() for t in self.tools.values()]
        for _ in range(self.max_rounds):
            reply = self.llm.complete(self.messages, schemas)
            calls = reply.get("tool_calls") or []
            self.messages.append({"role": "assistant", "content": reply.get("content") or "",
                                  **({"tool_calls": calls} if calls else {})})
            if not calls:
                answer = reply.get("content") or ""
                self.emit("answer", text=answer)
                return answer
            if reply.get("content"):
                self.emit("thinking", text=reply["content"])
            for call in calls:
                result = self.run_call(call)
                self.messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                      "content": json.dumps(result, ensure_ascii=False, default=str)})
        answer = "I stopped after too many steps. Please ask again in a simpler way."
        self.emit("answer", text=answer)
        return answer

    def run_call(self, call: dict) -> dict:
        fn = call.get("function", {})
        name = fn.get("name", "")
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        tool = self.tools.get(name)
        if tool is None:
            self.emit("error", tool=name, error="unknown tool")
            return {"error": f"unknown tool {name}"}
        if tool.risk != READ:
            self.emit("approval_needed", tool=name, risk=tool.risk, args=args)
            if not self.approver(tool, args):
                self.emit("rejected", tool=name, args=args)
                return {"status": "rejected", "message": "The user did not approve this action."}
            self.emit("approved", tool=name, args=args)
        self.emit("tool_start", tool=name, risk=tool.risk, args=args)
        try:
            result = tool.func(**args)
        except Exception as exc:  # a failing tool must not stop the conversation
            self.emit("error", tool=name, error=str(exc))
            return {"error": str(exc)}
        self.emit("tool_done", tool=name, ok=True)
        return result
