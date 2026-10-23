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
    attempts: int = 3
    retry_wait: float = 2.0

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """Return the assistant message: {"role", "content", "tool_calls"?}."""
        if not (self.base_url and self.model):
            raise LLMError("No LLM configured. Set LLM_BASE_URL, LLM_MODEL and LLM_API_KEY in .env.")
        if self.api_key.startswith("fake-") or "example.com" in self.base_url:
            raise LLMError("The LLM settings in .env are still the example placeholders.")
        body = {"model": self.model, "messages": messages, "temperature": 0.2}
        if tools:
            body["tools"] = tools
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        for attempt in range(self.attempts):
            start = time.monotonic()
            try:
                status, content = self.transport("POST", self.base_url + "/chat/completions", headers,
                                                 json.dumps(body).encode(), self.timeout)
            except OSError as exc:
                if attempt + 1 < self.attempts:
                    time.sleep(self.retry_wait * (attempt + 1))
                    continue
                raise LLMError(f"Cannot reach the LLM provider: {exc}") from exc
            if self.log is not None:
                self.log.write("llm", status=status, ms=int((time.monotonic() - start) * 1000),
                               model=self.model, messages=len(messages), attempt=attempt + 1)
            if status in (429, 500, 502, 503, 504) and attempt + 1 < self.attempts:
                time.sleep(self.retry_wait * (attempt + 1))
                continue
            break
        if status >= 400:
            raise LLMError(f"The LLM provider returned {status}: {content[:300].decode('utf-8', 'replace')}")
        try:
            data = json.loads(content)
            return data["choices"][0]["message"]
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMError("The LLM provider sent an unexpected reply.") from exc
