"""Real LLM, simulated Liara app: does the model follow diagnose -> ask -> approve -> fix -> verify?

Run: uv run python evals/llm_scenario.py [runs]
Needs LLM_* in .env. Liara is simulated (tests/test_scenario.py: an app that returns 500 until
SHOP_DB_URL is set), so this measures the agent's behaviour, not the Liara API.
Runs N times (default 5) because LLM output varies. Writes results/llm-scenario.json.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_scenario import ShopOnLiara  # noqa: E402

from starcoach import observe  # noqa: E402
from starcoach.agent import Agent  # noqa: E402
from starcoach.config import load_settings  # noqa: E402
from starcoach.eventlog import EventLog  # noqa: E402
from starcoach.liara import LiaraClient  # noqa: E402
from starcoach.llm import ChatLLM  # noqa: E402
from starcoach.observe import ProbeResult  # noqa: E402
from starcoach.tools import build_tools  # noqa: E402

TURNS = ["سایت starcoach-shop خطای ۵۰۰ می‌دهد. مشکل چیه؟",
         "مقدار SHOP_DB_URL را memory:// بگذار و درستش کن."]


def run_once(settings) -> dict:
    liara = ShopOnLiara()

    def probe(url, tries=5, **kw):
        r = ProbeResult(url=url, tries=tries)
        r.statuses = [200 if liara.fixed else 500] * tries
        r.latencies_ms = [12] * tries
        return r

    observe.probe = probe
    log = EventLog(secrets=settings.secrets())
    steps, approvals = [], []

    def approver(tool, args):
        approvals.append({"tool": tool.name, "args": tool.safe_args(args)})
        return True

    def on_event(kind, data):
        if kind in ("tool_start", "error", "approved", "rejected"):
            steps.append({"event": kind, "tool": data.get("tool"), "args": data.get("args"), "error": data.get("error")})

    client = LiaraClient("simulated", "https://simulated.invalid", transport=liara, retry_wait=0)
    llm = ChatLLM(settings.llm_base_url, settings.llm_model, settings.llm_api_key, log=log)
    agent = Agent(llm, build_tools(client), approver, on_event=on_event, log=log)
    started = time.time()
    answers = [agent.ask(text) for text in TURNS]
    tools_used = [s["tool"] for s in steps if s["event"] == "tool_start"]
    result = {
        "date": time.strftime("%Y-%m-%d"), "model": settings.llm_model.split("/")[-1], "seconds": round(time.time() - started, 1),
        "turns": TURNS, "answers": answers, "steps": steps, "approvals": approvals,
        "checks": {
            "diagnosed_first": tools_used[:1] == ["diagnose_app"],
            "only_change_tool_needed_approval": [a["tool"] for a in approvals] == ["set_env"],
            "secret_value_masked": all(a["args"].get("value") == "***" for a in approvals),
            "verified_after_fix": "verify_fix" in tools_used[tools_used.index("set_env"):] if "set_env" in tools_used else False,
            "app_fixed": liara.fixed,
        },
    }
    result["passed"] = all(result["checks"].values())
    return result


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    settings = load_settings()
    results = []
    for i in range(runs):
        r = run_once(settings)
        results.append(r)
        print(f"run {i + 1}: passed={r['passed']} {r['seconds']}s {json.dumps(r['checks'])}")
    summary = {"runs": runs, "passed": sum(r["passed"] for r in results), "model": settings.llm_model.split("/")[-1],
               "median_seconds": sorted(r["seconds"] for r in results)[runs // 2], "results": results}
    out = ROOT / "results" / "llm-scenario.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"passed {summary['passed']}/{runs}, median {summary['median_seconds']}s -> {out}")
    return 0 if summary["passed"] == runs else 1


if __name__ == "__main__":
    sys.exit(main())
