import json

from fakes import FakeLiara

from starcoach import observe
from starcoach.liara import LiaraClient

# Shape from research 03 §1.1 (Loki-like streams, nanosecond timestamps, JSON entries).
LOGS = {"data": [
    {"metaData": {"releaseId": "r2"}, "values": [
        ["1761100002000000000", json.dumps({"_entry": "GET / 500 3ms", "type": "stderr"})],
        ["1761100003000000000", json.dumps({"_entry": "Error: connect ECONNREFUSED 127.0.0.1:5432", "type": "stderr"})],
    ]},
    {"metaData": {"releaseId": "r2"}, "values": [
        ["1761100001000000000", json.dumps({"_entry": "demo shop listening on 0.0.0.0:3000", "type": "stdout"})],
        ["1761100004000000000", "not json at all"],
    ]},
]}
CPU = {"end": 1, "result": [{"applet": "shop-1", "values": [[1, "0.10"], [2, "0.45"], [3, "bad"]]}]}
MEM = {"end": 1, "result": [{"applet": "shop-1", "values": [[1, str(200 * 2**20)], [2, str(460 * 2**20)]]}]}
ME = {"user": {"fullname": "x", "nationalCode": "secret"},
      "plans": {"projects": {"small-g2": {"CPU": {"amount": 0.5}, "RAM": {"amount": 0.5}}}}}


def client():
    api = FakeLiara({
        ("GET", "/v2/projects/shop/logs"): (200, LOGS),
        ("GET", "/v1/projects/shop/events"): (200, {"data": [{"metaData": {}, "values": [
            ["1761100005000000000", json.dumps({"_entry": "stopped due to high RAM usage"})]]}]}),
        ("GET", "/v1/projects/shop/metrics/cpu"): (200, CPU),
        ("GET", "/v1/projects/shop/metrics/memory"): (200, MEM),
        ("GET", "/v1/projects/shop"): (200, {"project": {"planID": "small-g2"}}),
        ("GET", "/v1/me"): (200, ME),
    })
    return LiaraClient("tok", "https://api.test", transport=api, retry_wait=0)


def test_logs_flattened_sorted_and_decoded():
    lines = observe.get_logs(client(), "shop")
    assert [l["text"] for l in lines] == [
        "demo shop listening on 0.0.0.0:3000", "GET / 500 3ms",
        "Error: connect ECONNREFUSED 127.0.0.1:5432", "not json at all"]
    assert lines[0]["ts"] == 1761100001.0 and lines[1]["type"] == "stderr"


def test_error_filter():
    texts = [l["text"] for l in observe.get_logs(client(), "shop", errors_only=True)]
    assert texts == ["GET / 500 3ms", "Error: connect ECONNREFUSED 127.0.0.1:5432"]


def test_events():
    assert observe.get_events(client(), "shop")[0]["text"] == "stopped due to high RAM usage"


def test_real_event_shape_and_crash_detection():
    # Real response (F20): newest first; kill/stop/die of one container share a second.
    payload = {"data": [
        {"id": "b", "status": "start", "action": "start", "time": "1792783419", "release": "r2", "tag": "v2"},
        {"id": "a", "status": "die", "action": "die", "time": "1792783386", "release": "r1", "tag": "v1"},
        {"id": "a", "status": "stop", "action": "stop", "time": "1792783386", "release": "r1", "tag": "v1"},
        {"id": "a", "status": "kill", "action": "kill", "time": "1792783386", "release": "r1", "tag": "v1"},
        {"id": "c", "status": "die", "action": "die", "time": "1792783500", "release": "r2", "tag": "v2"},
        {"id": "d", "status": "oom", "action": "oom", "time": "1792783600", "release": "r2", "tag": "v2"},
    ]}
    texts = [e["text"] for e in observe.parse_events(payload)]
    assert not any("crashed" in t and "v1" in t for t in texts)  # a requested stop is not a crash
    assert "crashed: container exited without a stop request (release v2)" in texts
    assert texts[-1].startswith("oom:")


def test_metrics_against_plan_limits():
    m = observe.get_metrics(client(), "shop")
    assert m["limits"] == {"plan": "small-g2", "cpu_cores": 0.5, "ram_gb": 0.5}
    assert m["cpu"][0]["max"] == 0.45 and m["cpu"][0]["points"] == 2
    assert m["cpu"][0]["max_pct_of_limit"] == 90.0
    assert m["memory"][0]["max_mb"] == 460.0 and m["memory"][0]["max_pct_of_limit"] == 89.8


def test_probe_counts_errors_and_latency():
    seq = iter([200, 500, Exception("timed out"), 200])

    def getter(url, timeout):
        v = next(seq)
        if isinstance(v, Exception):
            raise v
        return v

    r = observe.probe("https://x.test", tries=4, getter=getter, sleep=lambda s: None).to_dict()
    assert r["statuses"] == [200, 500, 0, 200] and r["ok_ratio"] == 0.5
    assert r["server_errors"] == 1 and len(r["errors"]) == 1


def test_app_url():
    assert observe.app_url("shop") == "https://shop.liara.run"
    assert observe.app_url("https://a.ir") == "https://a.ir"


def test_dead_instance_series_are_dropped():
    from starcoach.observe import _series_stats
    stats = _series_stats([{"applet": "old", "values": [[100, "0.5"], [130, "0.4"]]},
                           {"applet": "new", "values": [[400, "0.01"], [430, "0.02"]]}])
    assert [s["instance"] for s in stats] == ["new"] and stats[0]["max"] == 0.02
