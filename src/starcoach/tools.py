"""Tools the agent can call. Each has a risk tier (D6): read runs at once; change/danger need a yes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .deploy import Deployer, release_status
from .liara import LiaraClient
from .limits import by_topic
from .recommend import recommend

READ, CHANGE, DANGER = "read", "change", "danger"
APP_PREFIX = "starcoach-"  # D2: apps the assistant creates carry this prefix


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


def build_tools(client: LiaraClient, on_event=None) -> dict[str, Tool]:
    """`on_event(kind, data)` receives progress from long tools such as deploys."""
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

    def recommend_setup(path: str) -> dict:
        plans = {}
        try:
            plans = client.plans()
        except Exception:
            pass
        return recommend(Path(path), plans.get("projects"), plans.get("projectBundlePlans")).to_dict()

    def create_app(app: str, platform: str, plan: str, bundle: str) -> dict:
        if not app.startswith(APP_PREFIX):
            app = APP_PREFIX + app
        return {"status": "created", **client.create_app(app, platform, plan, bundle)}

    def deploy_app(path: str, app: str, port: int | None = None) -> dict:
        return Deployer(client, on_event=on_event).deploy(Path(path), app, port=port).to_dict()

    def get_release(release_id: str) -> dict:
        return release_status(client, release_id)

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
        Tool("recommend_setup", "Look at a local project folder: platform, port, plan, and problems to fix "
             "before deploying.", READ, recommend_setup,
             {"path": {"type": "string", "description": "local project folder"}}, ["path"]),
        Tool("release_status", "State of one deploy (release).", READ, get_release,
             {"release_id": {"type": "string"}}, ["release_id"]),
        Tool("create_app", "Create a new Liara app. It costs money every hour while it exists. "
             "Use the plan and bundle from recommend_setup.", CHANGE, create_app,
             {**APP, "platform": {"type": "string"}, "plan": {"type": "string"},
              "bundle": {"type": "string"}}, ["app", "platform", "plan", "bundle"]),
        Tool("deploy_app", "Upload a local project folder and release it as the new live version.",
             CHANGE, deploy_app,
             {"path": {"type": "string"}, **APP, "port": {"type": "integer"}}, ["path", "app"]),
        Tool("restart_app", "Restart an app. The site is briefly unavailable.", CHANGE, restart_app,
             APP, ["app"]),
    ]
    return {t.name: t for t in tools}
