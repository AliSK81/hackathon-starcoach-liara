"""The demo scenario on the REAL Liara app with the REAL LLM.

Run: uv run python evals/live_scenario.py <app> --yes
1. Breaks the app on purpose: sets SHOP_DB_URL to empty (the demo app then returns 500).
2. Waits until the site returns 500.
3. Talks to the agent like a user: "my site gives 500" -> "set it to memory:// and fix it".
   The one approval card is answered "yes" by this script (that is what --yes allows).
4. Saves everything to results/live-scenario.json.
Changes a real app: use it only on the demo app.
"""
import json
import sys
import time
from pathlib import Path

from starcoach import observe
from starcoach.agent import Agent
from starcoach.config import load_settings
from starcoach.eventlog import EventLog
from starcoach.liara import LiaraClient
from starcoach.llm import ChatLLM
from starcoach.tools import build_tools

ROOT = Path(__file__).resolve().parents[1]
TURNS = ["سایت {app} خطای ۵۰۰ می‌دهد. مشکل چیه؟", "مقدارش را memory:// بگذار و درستش کن."]


def wait_for(url: str, want_ok: bool, timeout: int = 240) -> float:
    start = time.time()
    while time.time() - start < timeout:
        ok = observe.probe(url, tries=1).to_dict()["ok_ratio"] == 1
        if ok == want_ok:
            return round(time.time() - start, 1)
        time.sleep(5)
    raise SystemExit(f"site did not become {'healthy' if want_ok else 'broken'} in {timeout}s")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3 or sys.argv[2] != "--yes":
        print(__doc__)
        return 2
    app = sys.argv[1]
    s = load_settings()
    log = EventLog(secrets=s.secrets())
    client = LiaraClient(s.liara_token, s.liara_api_url, log=log, team_id=s.liara_team_id)
    url = observe.app_url(app)

    print("1. breaking the app (SHOP_DB_URL = empty)")
    client.set_env(app, "SHOP_DB_URL", "")
    broke_in = wait_for(url, want_ok=False)
    time.sleep(15)  # let a few failing requests reach the logs
    before = observe.probe(url, tries=5).to_dict()
    print(f"   broken after {broke_in}s: {before['statuses']}")

    steps, approvals = [], []

    def on_event(kind, data):
        if kind in ("tool_start", "tool_done", "error", "approval_needed", "approved", "rejected"):
            steps.append({"t": round(time.time() - started, 1), "event": kind, "tool": data.get("tool"),
                          "args": data.get("args"), "error": data.get("error")})
            print(f"   [{kind}] {data.get('tool')} {json.dumps(data.get('args') or '', ensure_ascii=False)[:120]}")

    def approver(tool, args):
        approvals.append({"tool": tool.name, "risk": tool.risk, "args": tool.safe_args(args)})
        return True

    llm = ChatLLM(s.llm_base_url, s.llm_model, s.llm_api_key, log=log)
    agent = Agent(llm, build_tools(client, on_event), approver, on_event=on_event, log=log)
    started = time.time()
    answers = []
    for text in TURNS:
        text = text.format(app=app)
        print(f"\nUSER: {text}")
        answers.append(agent.ask(text))
        print(f"ASSISTANT: {answers[-1]}")
    after = observe.probe(url, tries=5).to_dict()
    tools = [x["tool"] for x in steps if x["event"] == "tool_start"]
    result = {
        "date": time.strftime("%Y-%m-%d %H:%M"), "app": app, "model": s.llm_model.split("/")[-1],
        "seconds": round(time.time() - started, 1), "before": before["statuses"], "after": after["statuses"],
        "after_p50_ms": after["p50_ms"], "turns": TURNS, "answers": answers, "steps": steps, "approvals": approvals,
        "checks": {"site_broken_before": before["ok_ratio"] == 0, "diagnosed_first": tools[:1] == ["diagnose_app"],
                   "one_approval_set_env": [a["tool"] for a in approvals] == ["set_env"],
                   "verified_after_fix": "verify_fix" in tools, "site_fixed_after": after["ok_ratio"] == 1},
    }
    out = ROOT / "results" / "live-scenario.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{json.dumps(result['checks'])}  {result['seconds']}s -> {out}")
    return 0 if all(result["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
