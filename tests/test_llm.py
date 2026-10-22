import json

import pytest
from fakes import ScriptedLLM

from starcoach.agent import Agent
from starcoach.llm import ChatLLM, LLMError
from starcoach.tools import READ, Tool

OK = {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}


def transport(replies, seen):
    def send(method, url, headers, body, timeout):
        seen.append((url, headers, json.loads(body)))
        status, payload = replies.pop(0)
        return status, json.dumps(payload).encode()
    return send


def test_request_shape_and_retry_on_429():
    seen = []
    llm = ChatLLM("https://llm.test/v1", "m", "key", transport=transport([(429, {}), (200, OK)], seen), retry_wait=0)
    assert llm.complete([{"role": "user", "content": "x"}], [{"type": "function"}])["content"] == "hi"
    url, headers, body = seen[-1]
    assert url == "https://llm.test/v1/chat/completions" and headers["Authorization"] == "Bearer key"
    assert body["model"] == "m" and body["tools"] == [{"type": "function"}] and len(seen) == 2


def test_client_error_is_not_retried():
    seen = []
    llm = ChatLLM("https://llm.test/v1", "m", "k", transport=transport([(400, {"error": "bad"})], seen), retry_wait=0)
    with pytest.raises(LLMError, match="400"):
        llm.complete([])
    assert len(seen) == 1


def test_object_arguments_and_null_content():
    got = {}
    tool = Tool("echo", "echo", READ, lambda text: got.update(text=text) or {"ok": True},
                {"text": {"type": "string"}}, ["text"])
    llm = ScriptedLLM({"content": None, "tool_calls": [{"id": "1", "type": "function",
                                                        "function": {"name": "echo", "arguments": {"text": "سلام"}}}]},
                      {"content": "done"})
    Agent(llm, {"echo": tool}, lambda t, a: True).ask("x")
    assert got == {"text": "سلام"}
    assert llm.seen[1][-2]["content"] is None and llm.seen[1][-2]["tool_calls"]
