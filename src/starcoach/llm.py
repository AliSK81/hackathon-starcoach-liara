"""OpenAI-compatible chat-completions client with tool calling. Stdlib only."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from .liara import Transport, urllib_transport


class LLMError(Exception):
    pass


@dataclass
class ChatLLM:
    base_url: str
    model: str
    api_key: str
    transport: Transport = urllib_transport
    log: object | None = None
    timeout: float = 120.0

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Return the assistant message: {"role", "content", "tool_calls"?}."""
        if not (self.base_url and self.model):
            raise LLMError("No LLM configured. Set LLM_BASE_URL, LLM_MODEL and LLM_API_KEY in .env.")
        body = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            body["tools"] = tools
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        start = time.monotonic()
        try:
            status, content = self.transport("POST", self.base_url + "/chat/completions", headers,
                                             json.dumps(body).encode(), self.timeout)
        except OSError as exc:
            raise LLMError(f"Cannot reach the LLM provider: {exc}") from exc
        if self.log is not None:
            self.log.write("llm", status=status, ms=int((time.monotonic() - start) * 1000),
                           model=self.model, messages=len(messages))
        if status >= 400:
            raise LLMError(f"The LLM provider returned {status}: {content[:300].decode('utf-8', 'replace')}")
        try:
            data = json.loads(content)
            return data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMError("The LLM provider sent an unexpected reply.") from exc
