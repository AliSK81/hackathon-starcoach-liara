import json
from pathlib import Path

import pytest
from fakes import FakeLiara, ScriptedLLM, call

from starcoach.agent import Agent
from starcoach.diagnose import Evidence, diagnose, gather, verify_fix
from starcoach.evaluate import evaluate
from starcoach.liara import LiaraClient, LiaraError
from starcoach.observe import ProbeResult
from starcoach.tools import build_tools

ROOT = Path(__file__).resolve().parents[1]


def test_eval_sets_beat_baseline():
    for name in ("incidents_dev.json", "incidents_holdout.json", "incidents_holdout2.json"):
        r = evaluate(ROOT / "evals" / name)
        assert r["engine_top1"] >= 0.9, (name, [x for x in r["rows"] if not x["engine_top1"]])
        assert r["engine_top1"] >= r["baseline_top1"]


def test_demo_incident_suggests_env_fix():
    ev = Evidence(app="shop", platform="node",
                  log_lines=["SHOP_DB_URL is not set; using default 127.0.0.1:5432", "GET / 500 2ms",
                             "Error: connect ECONNREFUSED 127.0.0.1:5432"],
                  probe={"statuses": [500] * 5, "p50_ms": 3})
    r = diagnose(ev)
    top = r["causes"][0]
    assert r["summary"] == "problem" and top["id"] == "X-ENV-MISSING"
    assert top["action"] == {"tool": "set_env", "args": {"app": "shop", "key": "SHOP_DB_URL", "value": "<ask the user>"}}
    assert "X-DB-REFUSED" in [c["id"] for c in r["causes"]]
    assert top["title_fa"]


def test_oom_event_not_lowered_by_sampled_memory():
    # Real incident (F26): Liara reported `oom` while the 30 s memory samples peaked at 54%.
    ev = Evidence(app="lab", platform="node", events=["oom: container ran out of memory (release v3)",
                                                      "crashed: container exited without a stop request (release v3)"],
                  probe={"statuses": [200, 502, 200]}, metrics={"memory": [{"max_pct_of_limit": 54}], "cpu": []})
    top = diagnose(ev)["causes"][0]
    assert top["id"] == "X-OOM-EVENT" and top["confidence"] >= 0.8


def fake_probe(statuses):
    seq = iter(statuses)

    def prober(url, tries=5, **kw):
        r = ProbeResult(url=url, tries=tries)
        for _ in range(tries):
            s = next(seq, statuses[-1])
            r.statuses.append(s)
            r.latencies_ms.append(5)
        return r
    return prober


def test_gather_survives_failing_sources():
    api = FakeLiara({("GET", "/v1/projects/shop"): (200, {"project": {"type": "node", "scale": 1}})})
    client = LiaraClient("tok", "https://api.test", transport=api, retry_wait=0)
    ev = gather(client, "shop", prober=fake_probe([200]))
    assert ev.platform == "node" and len(ev.missing) >= 3
    assert diagnose(ev)["summary"] == "healthy"


LOG_AFTER = {"data": [{"metaData": {}, "values": [
    ["9999999990000000000", json.dumps({"_entry": "demo shop listening on 0.0.0.0:3000"})]]}]}
LOG_STILL = {"data": [{"metaData": {}, "values": [
    ["9999999990000000000", json.dumps({"_entry": "Error: connect ECONNREFUSED 127.0.0.1:5432"})]]}]}


def test_verify_fixed_after_restart_wait():
    client = LiaraClient("tok", "https://api.test", retry_wait=0,
                         transport=FakeLiara({("GET", "/v2/projects/shop/logs"): (200, LOG_AFTER)}))
    r = verify_fix(client, "shop", ["X-DB-REFUSED"], since=1, prober=fake_probe([502, 502, 200]),
                   wait_seconds=60, sleep=lambda s: None)
    assert r["fixed"] and r["verdict"] == "fixed" and r["probe"]["waited_seconds"] == 20


def test_verify_not_fixed_when_signature_remains():
    client = LiaraClient("tok", "https://api.test", retry_wait=0,
                         transport=FakeLiara({("GET", "/v2/projects/shop/logs"): (200, LOG_STILL)}))
    r = verify_fix(client, "shop", ["X-DB-REFUSED"], since=1, prober=fake_probe([200]), sleep=lambda s: None)
    assert not r["fixed"] and "X-DB-REFUSED" in r["signatures_still_present"]


class EnvAPI(FakeLiara):
    def __init__(self, envs):
        super().__init__({("GET", "/v1/projects/shop"): (200, {"project": {"envs": envs}}),
                          ("POST", "/v1/projects/update-envs"): (200, {"message": "ok"})})
        self.bodies = []

    def __call__(self, method, url, headers, body, timeout):
        if body:
            self.bodies.append(json.loads(body))
        return super().__call__(method, url, headers, body, timeout)


def test_set_env_merges_and_dedupes():
    api = EnvAPI([{"key": "A", "value": "1"}, {"key": "SHOP_DB_URL", "value": "old"}])
    LiaraClient("tok", "https://api.test", transport=api).set_env("shop", "SHOP_DB_URL", "memory://")
    assert api.bodies[-1] == {"project": "shop", "variables": [{"key": "A", "value": "1"},
                                                               {"key": "SHOP_DB_URL", "value": "memory://"}]}


def test_set_env_refuses_when_encrypted_envs_exist():
    api = EnvAPI([{"key": "SECRET", "value": "****", "encrypted": True}])
    with pytest.raises(LiaraError, match="encrypted"):
        LiaraClient("tok", "https://api.test", transport=api).set_env("shop", "X", "1")
    assert ("POST", "/v1/projects/update-envs") not in api.calls


def test_env_value_masked_in_events():
    api = EnvAPI([])
    client = LiaraClient("tok", "https://api.test", transport=api)
    events = []
    llm = ScriptedLLM({"content": "", "tool_calls": [call("set_env", {"app": "shop", "key": "K", "value": "p4ss"})]},
                      {"content": "done"})
    Agent(llm, build_tools(client), lambda t, a: True, on_event=lambda k, d: events.append(d)).ask("set K")
    assert "p4ss" not in json.dumps(events) and api.bodies[-1]["variables"] == [{"key": "K", "value": "p4ss"}]


def test_danger_tool_needs_typed_name(monkeypatch):
    from starcoach import cli
    tool = build_tools(LiaraClient("tok"))["stop_app"]
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    assert cli.terminal_approver(tool, {"app": "shop"}) is False
    monkeypatch.setattr("builtins.input", lambda prompt: "shop")
    assert cli.terminal_approver(tool, {"app": "shop"}) is True


def test_verify_ignores_old_container_lines_before_healthy(monkeypatch):
    import time as _t
    now = _t.time()
    old_line = str(int((now + 5) * 1e9))   # logged after the fix was sent, before the site came back
    logs = {"data": [{"metaData": {}, "values": [
        [old_line, json.dumps({"_entry": "Error: connect ECONNREFUSED 127.0.0.1:5432"})]]}]}
    client = LiaraClient("tok", "https://api.test", retry_wait=0,
                         transport=FakeLiara({("GET", "/v2/projects/shop/logs"): (200, logs)}))
    clock = {"t": now}
    monkeypatch.setattr(_t, "time", lambda: clock["t"])

    def sleep(s):
        clock["t"] += s

    # site answers 500 twice (old container), then 200 from the new one at now+20
    r = verify_fix(client, "shop", ["X-DB-REFUSED"], since=now, prober=fake_probe([500, 500, 200]),
                   wait_seconds=60, sleep=sleep)
    assert r["fixed"] and r["signatures_still_present"] == {}


def test_verify_reports_a_restart_blip_honestly():
    client = LiaraClient("tok", "https://api.test", retry_wait=0,
                         transport=FakeLiara({("GET", "/v2/projects/shop/logs"): (200, LOG_AFTER)}))
    seq = iter([200, 502, 200, 200, 200, 200])  # first ok, then one blip in the stability window

    def prober(url, tries=5, **kw):
        r = ProbeResult(url=url, tries=tries)
        r.statuses = [next(seq) for _ in range(tries)]
        r.latencies_ms = [5] * tries
        return r

    r = verify_fix(client, "shop", ["X-DB-REFUSED"], since=1, prober=prober, sleep=lambda s: None)
    assert r["fixed"] and r["blips"] == 1 and "blip" in r["verdict"]
