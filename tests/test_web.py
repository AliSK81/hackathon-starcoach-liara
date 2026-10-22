import json
import threading
import time
import urllib.request

from fakes import FakeLiara, ScriptedLLM, call

from starcoach.agent import Agent
from starcoach.liara import LiaraClient
from starcoach.tools import build_tools
from starcoach.web import serve

ROUTES = {("POST", "/v1/projects/shop/actions/restart"): (200, {}),
          ("POST", "/v1/projects/shop/actions/scale"): (200, {})}


def start(llm):
    api = FakeLiara(ROUTES)
    client = LiaraClient("tok", "https://api.test", transport=api, retry_wait=0)

    def factory(approver, on_event):
        return Agent(llm, build_tools(client, on_event), approver, on_event=on_event)

    server = serve(factory, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, api, f"http://127.0.0.1:{server.server_address[1]}"


def post(base, path, data):
    req = urllib.request.Request(base + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


SEEN = {}


def events_until(base, session, kind, timeout=5):
    """Read the stream from the last seen event, like a reconnecting browser."""
    got = []
    after = SEEN.get(session, 0)
    with urllib.request.urlopen(f"{base}/api/events?session={session}&after={after}", timeout=timeout) as r:
        end = time.time() + timeout
        while time.time() < end:
            line = r.readline().decode().strip()
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                got.append(ev)
                SEEN[session] = ev["seq"]
                if ev["kind"] == kind:
                    return got
    raise AssertionError(f"no {kind} in {got}")


def test_page_served():
    server, _, base = start(ScriptedLLM())
    with urllib.request.urlopen(base + "/", timeout=5) as r:
        assert "StarCoach" in r.read().decode()
    server.shutdown()


def test_approval_card_flow():
    llm = ScriptedLLM({"content": "", "tool_calls": [call("restart_app", {"app": "shop"})]}, {"content": "انجام شد"})
    server, api, base = start(llm)
    assert post(base, "/api/chat", {"session": "s1", "text": "ری‌استارت کن"})[0] == 202
    evs = events_until(base, "s1", "approval_card")
    card = evs[-1]
    assert card["tool"] == "restart_app" and card["risk"] == "change"
    assert ("POST", "/v1/projects/shop/actions/restart") not in api.calls  # waits for the click
    assert post(base, "/api/approve", {"session": "s1", "id": card["id"], "approve": True})[1]["ok"]
    evs = events_until(base, "s1", "idle")
    assert [e["kind"] for e in evs if e["kind"] in ("approved", "tool_done", "answer")] == ["approved", "tool_done", "answer"]
    assert ("POST", "/v1/projects/shop/actions/restart") in api.calls
    # single use: the same id cannot be answered twice
    assert post(base, "/api/approve", {"session": "s1", "id": card["id"], "approve": True})[0] == 400
    server.shutdown()


def test_danger_needs_typed_name():
    llm = ScriptedLLM({"content": "", "tool_calls": [call("stop_app", {"app": "shop"})]}, {"content": "ok"})
    server, api, base = start(llm)
    post(base, "/api/chat", {"session": "s2", "text": "stop"})
    card = events_until(base, "s2", "approval_card")[-1]
    assert card["type_to_confirm"] == "shop"
    code, body = post(base, "/api/approve", {"session": "s2", "id": card["id"], "approve": True, "typed": "sho"})
    assert code == 400 and not body["ok"]
    assert post(base, "/api/approve", {"session": "s2", "id": card["id"], "approve": True, "typed": "shop"})[1]["ok"]
    events_until(base, "s2", "idle")
    assert ("POST", "/v1/projects/shop/actions/scale") in api.calls
    server.shutdown()


def test_reject_does_not_run():
    llm = ScriptedLLM({"content": "", "tool_calls": [call("restart_app", {"app": "shop"})]}, {"content": "باشد"})
    server, api, base = start(llm)
    post(base, "/api/chat", {"session": "s3", "text": "restart"})
    card = events_until(base, "s3", "approval_card")[-1]
    post(base, "/api/approve", {"session": "s3", "id": card["id"], "approve": False})
    kinds = [e["kind"] for e in events_until(base, "s3", "idle")]
    assert "rejected" in kinds and ("POST", "/v1/projects/shop/actions/restart") not in api.calls
    server.shutdown()


def test_history_trim_keeps_sequence():
    from starcoach import web
    s = web.Session(lambda approver, on_event: None)
    for i in range(web.MAX_HISTORY + 5):
        s.push("x", {"i": i})
    newest = s.events_after(web.MAX_HISTORY + 3, timeout=0)
    assert [e["i"] for e in newest] == [web.MAX_HISTORY + 3, web.MAX_HISTORY + 4]
