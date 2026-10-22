import json

from fakes import FakeLiara

from starcoach import domains
from starcoach.liara import LiaraClient
from starcoach.observe import ProbeResult
from starcoach.watch import Watcher, classify


def prober_from(seq):
    it = iter(seq)

    def prober(url, tries=3, **kw):
        s = next(it, seq[-1])
        r = ProbeResult(url=url, tries=tries)
        r.statuses = [s] * tries
        r.latencies_ms = [10] * tries
        return r
    return prober


def watcher(tmp_path, seq, auto=False, now=lambda: 10_000):
    api = FakeLiara({("GET", "/v1/projects/shop"): (200, {"project": {"type": "node", "scale": 1}}),
                     ("POST", "/v1/projects/shop/actions/restart"): (200, {})})
    client = LiaraClient("tok", "https://api.test", transport=api, retry_wait=0)
    msgs = []
    w = Watcher(client, ["shop"], auto_restart=auto, state_file=tmp_path / "s.json",
                alerts_file=tmp_path / "a.jsonl", prober=prober_from(seq), notify=msgs.append, now=now)
    return w, api, msgs


def alerts(tmp_path):
    f = tmp_path / "a.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def test_alert_once_per_change(tmp_path):
    w, _, _ = watcher(tmp_path, [200, 200, 500, 500, 200])
    for _ in range(5):
        w.run_once()
    assert [(a["from"], a["to"]) for a in alerts(tmp_path)] == [("unknown", "up"), ("up", "down"), ("down", "up")]
    assert "Likely:" in alerts(tmp_path)[1]["summary"]


def test_state_survives_restart_no_duplicate_alert(tmp_path):
    w, _, _ = watcher(tmp_path, [500])
    w.run_once()
    w2, _, _ = watcher(tmp_path, [500])  # a new process, same state file
    w2.run_once()
    assert len(alerts(tmp_path)) == 1


def test_auto_restart_only_with_flag_and_cooldown(tmp_path):
    w, api, _ = watcher(tmp_path, [500])
    w.run_once()
    assert ("POST", "/v1/projects/shop/actions/restart") not in api.calls
    clock = {"t": 10_000}
    w, api, _ = watcher(tmp_path / "b", [500], auto=True, now=lambda: clock["t"])
    w.run_once()
    w.run_once()  # within the cooldown: no second restart
    clock["t"] += 3601
    w.run_once()
    assert api.calls.count(("POST", "/v1/projects/shop/actions/restart")) == 2


def test_one_failing_app_does_not_stop_the_cycle(tmp_path):
    w, _, _ = watcher(tmp_path, [200])
    ok = prober_from([200])

    def prober(url, tries=3):
        if "broken" in url:
            raise OSError("dns")
        return ok(url, tries)

    w.apps = ["shop", "broken"]
    w.prober = prober
    assert [r["status"] for r in w.run_once()] == ["up", "check-failed"]


def test_classify():
    assert classify({"ok_ratio": 1, "p50_ms": 50}) == "up"
    assert classify({"ok_ratio": 1, "p50_ms": 5000}) == "slow"
    assert classify({"ok_ratio": 0.5}) == "degraded"
    assert classify({"ok_ratio": 0}) == "down"


def test_irnic_guide_and_records():
    g = domains.guide("shop.ir", "shop.liara.run", "liara-verify=abc")
    text = " ".join(g["steps_fa"])
    assert "ns1.liara.zone" in text and "ایرنیک" in text
    assert g["records"][0]["value"] == "shop.liara.run" and g["records"][1]["value"] == "liara-verify=abc"
    assert "IRNIC" in g["registrar"] and "IRNIC" not in domains.guide("shop.com")["registrar"]


def test_add_domain_calls_api():
    api = FakeLiara({("POST", "/v1/domains"): (201, {"domain": {"_id": "d1"}}),
                     ("GET", "/v1/domains/d1/check"): (200, {"domain": {"name": "shop.ir", "status": "PENDING",
                                                                         "CNameRecord": "x.liara.run",
                                                                         "verificationCode": "v"}})})
    r = domains.add_domain(LiaraClient("tok", "https://api.test", transport=api), "shop", "shop.ir")
    assert r == {"id": "d1", "name": "shop.ir", "status": "PENDING", "ssl": None,
                 "cname_target": "x.liara.run", "txt_verification": "v"}
