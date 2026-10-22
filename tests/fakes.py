"""Offline fakes: a scripted LLM and a fake Liara API."""

import json


def call(name, args=None, id="c1"):
    return {"id": id, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args or {})}}


class ScriptedLLM:
    """Replays assistant messages in order and records what it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    def complete(self, messages, tools=None):
        self.seen.append(json.loads(json.dumps(messages)))
        return self.replies.pop(0)


class FakeLiara:
    """Routes (method, path) to canned JSON replies. Records every call."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        path = url.split("://", 1)[1].split("/", 1)[1]
        path = "/" + path.split("?", 1)[0]
        self.calls.append((method, path))
        status, payload = self.routes.get((method, path), (404, {"message": "not found"}))
        return status, json.dumps(payload).encode()
