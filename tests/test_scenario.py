"""The demo scenario end to end, offline: 500 → diagnose → approve set_env → restart → verify fixed."""

import json

from fakes import ScriptedLLM, call

from starcoach import observe
from starcoach.agent import Agent
from starcoach.liara import LiaraClient
from starcoach.observe import ProbeResult
from starcoach.tools import build_tools


class ShopOnLiara:
    """A fake Liara whose app is broken until SHOP_DB_URL is set."""

    def __init__(self):
        self.envs = []
        self.calls = []

    @property
    def fixed(self):
        return any(e["key"] == "SHOP_DB_URL" for e in self.envs)

    def __call__(self, method, url, headers, body, timeout):
        path = "/" + url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
        self.calls.append((method, path))
        if path == "/v1/projects/starcoach-shop":
            return 200, json.dumps({"project": {"type": "node", "scale": 1, "planID": "small-g2",
                                                "envs": self.envs}}).encode()
        if path == "/v2/projects/starcoach-shop/logs":
            lines = ([["9999999990000000000", json.dumps({"_entry": "demo shop listening on 0.0.0.0:3000"})]]
                     if self.fixed else
                     [["1761100001000000000", json.dumps({"_entry": "SHOP_DB_URL is not set; using default 127.0.0.1:5432", "type": "stderr"})],
                      ["1761100002000000000", json.dumps({"_entry": "Error: connect ECONNREFUSED 127.0.0.1:5432", "type": "stderr"})]])
            return 200, json.dumps({"data": [{"metaData": {}, "values": lines}]}).encode()
        if path == "/v1/projects/update-envs":
            self.envs = json.loads(body)["variables"]
            return 200, b'{"message":"ok"}'
        return 404, b'{"message":"not found"}'


def test_full_demo_scenario(monkeypatch):
    liara = ShopOnLiara()

    def fake_probe(url, tries=5, **kw):
        r = ProbeResult(url=url, tries=tries)
        r.statuses = [200 if liara.fixed else 500] * tries
        r.latencies_ms = [12] * tries
        return r

    monkeypatch.setattr(observe, "probe", fake_probe)
    client = LiaraClient("tok", "https://api.test", transport=liara, retry_wait=0)
    llm = ScriptedLLM(
        {"content": "", "tool_calls": [call("diagnose_app", {"app": "starcoach-shop"}, id="1")]},
        {"content": "SHOP_DB_URL is missing. I will set it.",
         "tool_calls": [call("set_env", {"app": "starcoach-shop", "key": "SHOP_DB_URL", "value": "memory://"}, id="2")]},
        {"content": "", "tool_calls": [call("verify_fix", {"app": "starcoach-shop", "cause_ids": ["X-ENV-MISSING", "X-DB-REFUSED"],
                                                           "since": 1761100003, "wait_seconds": 0}, id="3")]},
        {"content": "مشکل حل شد: ۵ از ۵ درخواست موفق."},
    )
    approvals, events = [], []
    agent = Agent(llm, build_tools(client), lambda tool, args: approvals.append(tool.name) or True,
                  on_event=lambda k, d: events.append((k, d)))

    answer = agent.ask("سایت starcoach-shop خطای ۵۰۰ می‌دهد")

    diagnosis = json.loads(llm.seen[1][-1]["content"])
    assert diagnosis["summary"] == "problem"
    assert diagnosis["causes"][0]["id"] == "X-ENV-MISSING"
    assert diagnosis["causes"][0]["action"]["args"]["key"] == "SHOP_DB_URL"
    assert approvals == ["set_env"]  # only the change needed approval
    assert ("POST", "/v1/projects/update-envs") in liara.calls
    verdict = json.loads(llm.seen[3][-1]["content"])
    assert verdict["fixed"] and verdict["probe"]["statuses"] == [200] * 5
    assert answer.startswith("مشکل حل شد")
    assert "memory://" not in json.dumps([d for _, d in events], ensure_ascii=False)
