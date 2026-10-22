"""`watch`: check apps on a schedule, alert once per state change, diagnose when something breaks.

State survives restarts (results/watch-state.json), so the same alert is never written twice.
One failing check is logged and the loop goes on.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import diagnose, observe

STATE_FILE = Path("results") / "watch-state.json"
ALERTS_FILE = Path("results") / "alerts.jsonl"
RESTART_COOLDOWN = 3600


def classify(probe: dict) -> str:
    ratio = probe.get("ok_ratio", 0)
    if ratio == 1:
        return "slow" if (probe.get("p50_ms") or 0) > 3000 else "up"
    return "down" if ratio == 0 else "degraded"


class Watcher:
    def __init__(self, client, apps: list[str], log=None, auto_restart: bool = False,
                 state_file: Path = STATE_FILE, alerts_file: Path = ALERTS_FILE,
                 prober=None, notify=print, now=time.time):
        self.client = client
        self.apps = apps
        self.log = log
        self.auto_restart = auto_restart
        self.state_file = Path(state_file)
        self.alerts_file = Path(alerts_file)
        self.prober = prober or observe.probe
        self.notify = notify
        self.now = now
        self.state = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        tmp.replace(self.state_file)  # atomic: a crash never leaves half a state file

    def _alert(self, app: str, record: dict):
        self.alerts_file.parent.mkdir(parents=True, exist_ok=True)
        with self.alerts_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        if self.log is not None:
            self.log.write("watch.alert", **record)
        self.notify(f"[{record['time']}] {app}: {record['from']} → {record['to']}. {record.get('summary', '')}")

    def check(self, app: str) -> dict:
        probe = self.prober(observe.app_url(app), tries=3).to_dict()
        status = classify(probe)
        prev = self.state.get(app, {})
        result = {"app": app, "status": status, "ok_ratio": probe["ok_ratio"], "p50_ms": probe["p50_ms"]}
        if status != prev.get("status"):
            record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "app": app,
                      "from": prev.get("status", "unknown"), "to": status, "probe": probe}
            if status != "up":
                found = diagnose.diagnose(diagnose.gather(self.client, app, 15, prober=lambda u, tries: self.prober(u, tries=tries)))
                top = (found["causes"] or [{}])[0]
                record["summary"] = f"Likely: {top.get('title', 'unclear')} — fix: {top.get('fix', 'see diagnose')}"
                record["causes"] = [c["id"] for c in found["causes"]]
            # Write the new state before the alert: if we crash after this, the alert is not repeated.
            self.state[app] = {**prev, "status": status, "since": self.now()}
            self._save()
            self._alert(app, record)
        if status == "down" and self.auto_restart:
            last = self.state.get(app, {}).get("last_auto_restart", 0)
            if self.now() - last >= RESTART_COOLDOWN:
                self.state[app]["last_auto_restart"] = self.now()
                self._save()
                self.client.restart(app)
                result["action"] = "auto-restart"
                if self.log is not None:
                    self.log.write("watch.auto_restart", app=app)
                self.notify(f"{app}: down → automatic restart (allowed by --auto-restart, max once per hour)")
        return result

    def run_once(self) -> list[dict]:
        results = []
        for app in self.apps:
            try:
                results.append(self.check(app))
            except Exception as exc:  # one bad app or network blip never stops the watch
                if self.log is not None:
                    self.log.write("watch.error", app=app, error=str(exc))
                results.append({"app": app, "status": "check-failed", "error": str(exc)})
        if self.log is not None:
            self.log.write("watch.cycle", results=results)
        return results

    def run(self, interval: float, cycles: int | None = None, sleep=time.sleep):
        n = 0
        while cycles is None or n < cycles:
            for r in self.run_once():
                self.notify(f"  {r['app']}: {r['status']}" + (f" ({r['p50_ms']} ms)" if r.get("p50_ms") else ""))
            n += 1
            if cycles is None or n < cycles:
                sleep(interval)
