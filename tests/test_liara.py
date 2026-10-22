import json

import pytest

from starcoach.eventlog import EventLog
from starcoach.liara import LiaraClient, LiaraError


class FakeTransport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers))
        status, payload = self.replies.pop(0)
        return status, json.dumps(payload).encode()


def make(replies, tmp_path=None):
    t = FakeTransport(replies)
    log = EventLog(tmp_path / "e.jsonl", secrets=["tok"]) if tmp_path else None
    return LiaraClient("tok", "https://api.test", transport=t, log=log, retry_wait=0), t


def test_list_apps_sends_bearer(tmp_path):
    c, t = make([(200, {"projects": [{"project_id": "a"}]})], tmp_path)
    assert c.list_apps() == [{"project_id": "a"}]
    method, url, headers = t.calls[0]
    assert (method, url) == ("GET", "https://api.test/v1/projects")
    assert headers["Authorization"] == "Bearer tok"
    assert "tok" not in (tmp_path / "e.jsonl").read_text().replace("***", "")


def test_401_gives_plain_message():
    c, _ = make([(401, {"error": "Unauthorized."})])
    with pytest.raises(LiaraError) as e:
        c.me()
    assert e.value.status == 401 and "LIARA_API_TOKEN" in str(e.value)


def test_get_retries_on_503_then_succeeds():
    c, t = make([(503, {}), (200, {"project": {"project_id": "x"}})])
    assert c.get_app("x")["project_id"] == "x"
    assert len(t.calls) == 2


def test_post_never_retries():
    c, t = make([(503, {}), (200, {})])
    with pytest.raises(LiaraError):
        c.request("POST", "/v1/projects/x/actions/restart")
    assert len(t.calls) == 1


def test_missing_token():
    with pytest.raises(LiaraError):
        LiaraClient("").list_apps()
