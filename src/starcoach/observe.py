"""Observability: logs, events, metrics and our own HTTP probe (research 03)."""

from __future__ import annotations

import json
import os
import re
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field

from .liara import LiaraClient, _q

ERROR_RE = re.compile(r"error|exception|traceback|fatal|unhandled|refused|timeout|killed|\b5\d\d\b",
                      re.IGNORECASE)


def _ts_seconds(raw) -> float:
    """Stream timestamps are long digit strings; the first 10 digits are unix seconds (03 §1.1)."""
    s = str(raw)
    if s.isdigit() and len(s) > 10:
        return float(s[:10] + "." + s[10:16])
    try:
        return float(s)
    except ValueError:
        return 0.0


def flatten_streams(payload: dict) -> list[dict]:
    """{data: [{metaData, values: [[ts, json-or-text], ...]}]} -> sorted [{ts, type, text, release}]."""
    lines = []
    for stream in (payload or {}).get("data", []) or []:
        release = (stream.get("metaData") or {}).get("releaseId")
        for value in stream.get("values", []) or []:
            if not value:
                continue
            raw = value[1] if len(value) > 1 else ""
            kind, text = "stdout", str(raw)
            try:
                entry = json.loads(raw)
                if isinstance(entry, dict):
                    text = str(entry.get("_entry", entry.get("message", raw)))
                    kind = entry.get("type", "stdout")
            except (TypeError, ValueError):
                pass
            lines.append({"ts": _ts_seconds(value[0]), "type": kind, "text": text.rstrip(),
                          "release": release})
    lines.sort(key=lambda l: l["ts"])
    return lines


def get_logs(client: LiaraClient, app: str, minutes: int = 30, errors_only: bool = False,
             limit: int = 200) -> list[dict]:
    start = int(time.time()) - minutes * 60
    # The endpoint returns one page of ~100 lines. "forward" gives the oldest page after `start`;
    # "backward" gives the newest, which is what monitoring and diagnosis need (F19).
    payload = client.request("GET", f"/v2/projects/{_q(app)}/logs",
                             params={"start": start, "direction": "backward"})
    lines = flatten_streams(payload)
    if errors_only:
        lines = [l for l in lines if l["type"] == "stderr" or ERROR_RE.search(l["text"])]
    return lines[-limit:]


def get_events(client: LiaraClient, app: str, minutes: int = 24 * 60) -> list[dict]:
    end = int(time.time())
    payload = client.request("GET", f"/v1/projects/{_q(app)}/events",
                             params={"start": end - minutes * 60, "end": end})
    return parse_events(payload)


def parse_events(payload: dict) -> list[dict]:
    """Real shape (F20): {data: [{id, status, action, time, release, tag}]} = container lifecycle
    (create, start, kill, stop, die, oom). A `die` with no `kill` for the same container is a crash.
    The documented stream shape is also accepted."""
    items = (payload or {}).get("data", []) or []
    if items and isinstance(items[0], dict) and "values" in items[0]:
        return flatten_streams(payload)
    events = sorted((e for e in items if isinstance(e, dict)), key=lambda e: _ts_seconds(e.get("time", 0)))
    # kill, stop and die of one container often share a second, and Liara lists them newest first,
    # so pair them by container id within a window instead of trusting the order (F20).
    kills: dict = {}
    for e in events:
        if (e.get("action") or e.get("status")) == "kill":
            kills.setdefault(e.get("id"), []).append(_ts_seconds(e.get("time", 0)))
    out = []
    for e in events:
        action = str(e.get("action") or e.get("status") or "")
        ts = _ts_seconds(e.get("time", 0))
        text = f"{action} (release {e.get('tag') or e.get('release') or '?'})"
        requested = any(abs(ts - k) <= 30 for k in kills.get(e.get("id"), []))
        if action == "die" and not requested:
            text = f"crashed: container exited without a stop request (release {e.get('tag', '?')})"
        if action == "oom":
            text = f"oom: container ran out of memory (release {e.get('tag', '?')})"
        out.append({"ts": ts, "type": "event", "text": text, "action": action,
                    "tag": e.get("tag"), "release": e.get("release")})
    return out


def _series_stats(result: list[dict], live_window: float = 90) -> list[dict]:
    """Stats per instance. Every container restart starts a new series (F21), so only series that
    reported within `live_window` seconds of the newest point are kept: dead containers are history."""
    out = []
    for s in result or []:
        vals, last_ts = [], 0.0
        for point in s.get("values", []) or []:
            try:
                vals.append(float(point[1]))
                last_ts = max(last_ts, float(point[0]))
            except (TypeError, ValueError, IndexError):
                continue
        if vals:
            out.append({"instance": s.get("applet"), "last": vals[-1], "avg": statistics.fmean(vals),
                        "max": max(vals), "points": len(vals), "_last_ts": last_ts})
    newest = max((s["_last_ts"] for s in out), default=0)
    live = [s for s in out if s["_last_ts"] >= newest - live_window]
    for s in live:
        s.pop("_last_ts")
    return live


def plan_limits(client: LiaraClient, plan_id: str) -> dict:
    plan = (client.plans().get("projects") or {}).get(plan_id) or {}
    return {"plan": plan_id, "cpu_cores": (plan.get("CPU") or {}).get("amount"),
            "ram_gb": (plan.get("RAM") or {}).get("amount")}


def to_mb(value: float) -> float:
    """Memory unit is undocumented. Values above 1e5 are read as bytes (unverified, see limits)."""
    return value / 2**20 if value > 1e5 else value


def get_metrics(client: LiaraClient, app: str, minutes: int = 30) -> dict:
    since = int(time.time()) - minutes * 60
    cpu = client.request("GET", f"/v1/projects/{_q(app)}/metrics/cpu", params={"since": since})
    mem = client.request("GET", f"/v1/projects/{_q(app)}/metrics/memory", params={"since": since})
    project = client.get_app(app)
    limits = plan_limits(client, project.get("planID", ""))
    cpu_stats = _series_stats(cpu.get("result"))
    mem_stats = _series_stats(mem.get("result"))
    # Memory series of dead containers keep their last value for ~5 minutes (F21); CPU series stop
    # at once, so CPU tells which instances are alive.
    live = {s["instance"] for s in cpu_stats}
    if live and any(s["instance"] in live for s in mem_stats):
        mem_stats = [s for s in mem_stats if s["instance"] in live]
    for s in mem_stats:
        s["last_mb"], s["max_mb"] = round(to_mb(s["last"]), 1), round(to_mb(s["max"]), 1)
        if limits["ram_gb"]:
            s["max_pct_of_limit"] = round(100 * s["max_mb"] / (limits["ram_gb"] * 1024), 1)
    for s in cpu_stats:
        if limits["cpu_cores"]:
            s["max_pct_of_limit"] = round(100 * s["max"] / limits["cpu_cores"], 1)
    return {"minutes": minutes, "limits": limits, "cpu": cpu_stats, "memory": mem_stats,
            "units_note": "CPU read as cores, memory as bytes→MB. Units are not documented by Liara."}


@dataclass
class ProbeResult:
    url: str
    tries: int
    statuses: list[int] = field(default_factory=list)
    latencies_ms: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok_ratio(self) -> float:
        good = sum(1 for s in self.statuses if 200 <= s < 400)
        return good / self.tries if self.tries else 0.0

    def to_dict(self) -> dict:
        lat = sorted(self.latencies_ms)
        return {**asdict(self), "ok_ratio": round(self.ok_ratio, 2),
                "p50_ms": lat[(len(lat) - 1) // 2] if lat else None, "max_ms": lat[-1] if lat else None,
                "server_errors": sum(1 for s in self.statuses if s >= 500)}


def _probe_opener():
    """The probe measures what visitors see, so it connects directly and ignores HTTP(S)_PROXY (D8).
    A VPN proxy may not reach Iranian hosts at all (F16). STARCOACH_PROBE_PROXY=1 uses the proxy."""
    if os.environ.get("STARCOACH_PROBE_PROXY") == "1":
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(url: str, timeout: float) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": "starcoach-probe"})
    try:
        with _probe_opener().open(req, timeout=timeout) as r:
            r.read(1024)
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def probe(url: str, tries: int = 5, timeout: float = 15, pause: float = 1.0,
          getter=http_get, sleep=time.sleep) -> ProbeResult:
    result = ProbeResult(url=url, tries=tries)
    for i in range(tries):
        start = time.monotonic()
        try:
            status = getter(url, timeout)
            result.statuses.append(status)
            result.latencies_ms.append(int((time.monotonic() - start) * 1000))
        except Exception as exc:  # network errors are evidence, not crashes
            result.statuses.append(0)
            result.errors.append(f"{type(exc).__name__}: {exc}"[:200])
        if i + 1 < tries:
            sleep(pause)
    return result


def app_url(app_or_url: str) -> str:
    if app_or_url.startswith(("http://", "https://")):
        return app_or_url
    return f"https://{app_or_url}.liara.run"
