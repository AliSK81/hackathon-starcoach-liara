"""Tools the agent can call. Each has a risk tier (D6): read runs at once; change/danger need a yes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .liara import LiaraClient
from .limits import by_topic

READ, CHANGE, DANGER = "read", "change", "danger"


@dataclass
class Tool:
    name: str
    description: str
    risk: str
    func: Callable[..., dict]
    params: dict = field(default_factory=dict)
    required: list[str] = field(default_factory=list)

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name,
            "description": f"[risk: {self.risk}] {self.description}",
            "parameters": {"type": "object", "properties": self.params, "required": self.required},
        }}


APP = {"app": {"type": "string", "description": "the Liara app name"}}


def _app_summary(a: dict) -> dict:
    return {"name": a.get("project_id"), "platform": a.get("type"), "plan": a.get("planID"),
            "status": a.get("status"), "turned_on": bool(a.get("scale")),
            "deployed": a.get("isDeployed")}


def clean_app(app: dict) -> dict:
    """App details without secrets: env var values are dropped, only names are kept."""
    out = _app_summary(app)
    out.update({
        "env_names": [e.get("key") for e in app.get("envs", []) or []],
        "zero_downtime": app.get("zeroDowntime"),
        "created_at": app.get("created_at"),
    })
    return out


def build_tools(client: LiaraClient) -> dict[str, Tool]:
    def list_apps() -> dict:
        return {"apps": [_app_summary(a) for a in client.list_apps()]}

    def app_status(app: str) -> dict:
        details = clean_app(client.get_app(app))
        applets = client.applets(app)
        items = applets if isinstance(applets, list) else applets.get("applets", [])
        details["instances"] = [{"name": i.get("name"), "state": i.get("state"),
                                 "reason": i.get("reason")} for i in items]
        return details

    def api_limits(topic: str | None = None) -> dict:
        return {"limits": [{"topic": l.topic, "en": l.en, "fa": l.fa} for l in by_topic(topic)]}

    def restart_app(app: str) -> dict:
        client.restart(app)
        return {"status": "submitted", "message": f"Restart of {app} was sent to Liara."}

    tools = [
        Tool("list_apps", "List the user's Liara apps with platform, plan and status.", READ, list_apps),
        Tool("app_status", "Show one app's details and its running instances.", READ, app_status,
             APP, ["app"]),
        Tool("api_limits", "What the Liara API cannot do. Use it before telling the user something is impossible.",
             READ, api_limits,
             {"topic": {"type": "string", "enum": ["monitoring", "deploy", "automation", "domains"]}}),
        Tool("restart_app", "Restart an app. The site is briefly unavailable.", CHANGE, restart_app,
             APP, ["app"]),
    ]
    return {t.name: t for t in tools}
