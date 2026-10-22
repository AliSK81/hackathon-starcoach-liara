import json

from fakes import FakeLiara, ScriptedLLM, call

from starcoach.agent import Agent
from starcoach.liara import LiaraClient
from starcoach.tools import build_tools

APP = {"project_id": "shop", "type": "node", "planID": "small", "status": "ACTIVE", "scale": 1,
       "envs": [{"key": "DB_PASSWORD", "value": "hunter2-secret"}]}
ROUTES = {
    ("GET", "/v1/projects"): (200, {"projects": [APP]}),
    ("GET", "/v1/projects/shop"): (200, {"project": APP}),
    ("GET", "/v1/projects/shop/applets"): (200, {"applets": [{"name": "shop-1", "state": "running"}]}),
    ("POST", "/v1/projects/shop/actions/restart"): (200, {}),
}


def setup(llm, approve=True):
    api = FakeLiara(ROUTES)
    client = LiaraClient("tok", "https://api.test", transport=api, retry_wait=0)
    events = []
    asked = []

    def approver(tool, args):
        asked.append(tool.name)
        return approve

    agent = Agent(llm, build_tools(client), approver, on_event=lambda k, d: events.append(k))
    return agent, api, events, asked


def test_read_tool_runs_without_approval():
    llm = ScriptedLLM({"content": "", "tool_calls": [call("list_apps")]},
                      {"content": "شما یک برنامه دارید: shop"})
    agent, api, events, asked = setup(llm)
    assert agent.ask("چه برنامه‌هایی دارم؟") == "شما یک برنامه دارید: shop"
    assert asked == [] and ("GET", "/v1/projects") in api.calls
    assert events == ["user", "tool_start", "tool_done", "answer"]
    tool_msg = llm.seen[1][-1]
    assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"])["apps"][0]["name"] == "shop"


def test_env_values_never_reach_llm():
    llm = ScriptedLLM({"content": "", "tool_calls": [call("app_status", {"app": "shop"})]},
                      {"content": "ok"})
    agent, *_ = setup(llm)
    agent.ask("status of shop")
    sent = json.dumps(llm.seen[1])
    assert "hunter2-secret" not in sent and "DB_PASSWORD" in sent


def test_change_tool_runs_after_yes():
    llm = ScriptedLLM({"content": "I will restart shop.", "tool_calls": [call("restart_app", {"app": "shop"})]},
                      {"content": "restarted"})
    agent, api, events, asked = setup(llm, approve=True)
    agent.ask("restart shop")
    assert asked == ["restart_app"]
    assert ("POST", "/v1/projects/shop/actions/restart") in api.calls
    assert events.index("approval_needed") < events.index("approved") < events.index("tool_start")


def test_change_tool_blocked_after_no():
    llm = ScriptedLLM({"content": "", "tool_calls": [call("restart_app", {"app": "shop"})]},
                      {"content": "ok, not restarted"})
    agent, api, events, asked = setup(llm, approve=False)
    agent.ask("restart shop")
    assert ("POST", "/v1/projects/shop/actions/restart") not in api.calls
    assert "rejected" in events and "tool_start" not in events
    assert json.loads(llm.seen[1][-1]["content"])["status"] == "rejected"


def test_tool_error_goes_back_to_llm():
    llm = ScriptedLLM({"content": "", "tool_calls": [call("app_status", {"app": "nope"})]},
                      {"content": "That app does not exist."})
    agent, api, events, _ = setup(llm)
    assert agent.ask("status of nope") == "That app does not exist."
    assert "error" in events
    assert "Not found" in json.loads(llm.seen[1][-1]["content"])["error"]
