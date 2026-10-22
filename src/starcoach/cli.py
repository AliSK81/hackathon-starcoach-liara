"""`starcoach` command line. One subcommand per capability."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import load_settings
from .eventlog import EventLog
from .agent import Agent
from .liara import LiaraClient, LiaraError
from .limits import by_topic
from .llm import ChatLLM, LLMError
from .tools import build_tools


def cmd_version(args, settings, log) -> int:
    print(f"starcoach {__version__}")
    return 0


def _client(settings, log) -> LiaraClient:
    return LiaraClient(settings.liara_token, settings.liara_api_url, log=log)


def cmd_check(args, settings, log) -> int:
    client = _client(settings, log)
    user = client.me().get("user", {})
    apps = client.list_apps()
    print(f"Connected to Liara as {user.get('fullname') or 'unknown user'}. Apps: {len(apps)}.")
    return 0


def cmd_apps(args, settings, log) -> int:
    apps = _client(settings, log).list_apps()
    if not apps:
        print("No apps yet.")
        return 0
    print(f"{'NAME':<28}{'PLATFORM':<12}{'PLAN':<14}{'STATUS':<12}ON")
    for a in apps:
        on = "yes" if a.get("scale") else "no"
        print(f"{a.get('project_id', ''):<28}{a.get('type', ''):<12}"
              f"{a.get('planID', ''):<14}{a.get('status', ''):<12}{on}")
    return 0


def cmd_status(args, settings, log) -> int:
    client = _client(settings, log)
    app = client.get_app(args.app)
    print(f"App: {app.get('project_id', args.app)}  platform: {app.get('type')}  plan: {app.get('planID')}")
    print(f"Status: {app.get('status')}  turned on: {'yes' if app.get('scale') else 'no'}")
    applets = client.applets(args.app)
    items = applets if isinstance(applets, list) else applets.get("applets", [])
    for it in items:
        print(f"  instance {it.get('name', '?')}: {it.get('state', '?')} {it.get('reason') or ''}".rstrip())
    return 0


def cmd_limits(args, settings, log) -> int:
    for lim in by_topic(args.topic):
        print(f"[{lim.topic}] {lim.en}\n    {lim.fa}")
    return 0


STATUS_LINES = {
    "tool_start": lambda d: f"  ⏳ running {d['tool']} {d.get('args') or ''}",
    "tool_done": lambda d: f"  ✅ {d['tool']} done",
    "error": lambda d: f"  ❌ {d.get('tool', '')}: {d['error']}",
    "approval_needed": lambda d: f"  ⚠️  {d['tool']} needs your approval (risk: {d['risk']}) {d.get('args') or ''}",
    "approved": lambda d: f"  👍 approved: {d['tool']}",
    "rejected": lambda d: f"  ✋ not run: {d['tool']}",
}


def terminal_approver(tool, args) -> bool:
    answer = input(f"  Run {tool.name} {args}? Type yes / بله to approve: ").strip().lower()
    return answer in ("y", "yes", "بله", "آره", "ok")


def make_agent(settings, log, approver=terminal_approver, on_event=None):
    llm = ChatLLM(settings.llm_base_url, settings.llm_model, settings.llm_api_key, log=log)
    tools = build_tools(_client(settings, log))
    return Agent(llm, tools, approver, on_event=on_event, log=log)


def cmd_chat(args, settings, log) -> int:
    def show(kind, data):
        if kind in STATUS_LINES:
            print(STATUS_LINES[kind](data))

    agent = make_agent(settings, log, on_event=show)
    if args.once:
        print(agent.ask(args.once))
        return 0
    print("StarCoach — ask about your Liara apps. Empty line to quit. (سؤال خود را بنویسید)")
    while True:
        try:
            text = input("> ").strip()
        except EOFError:
            break
        if not text:
            break
        try:
            print(agent.ask(text))
        except LLMError as exc:
            log.write("error", command="chat", error=str(exc))
            print(f"error: {exc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="starcoach",
        description="Liara website assistant: deploy, monitor, diagnose, fix.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    p = sub.add_parser("version", help="show the version")
    p.set_defaults(func=cmd_version)
    p = sub.add_parser("check", help="test the Liara token and connection")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("apps", help="list your Liara apps")
    p.set_defaults(func=cmd_apps)
    p = sub.add_parser("status", help="show one app's state and instances")
    p.add_argument("app")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("limits", help="what the Liara API cannot do")
    p.add_argument("--topic", default=None)
    p.set_defaults(func=cmd_limits)
    p = sub.add_parser("chat", help="talk to the assistant (Persian or English)")
    p.add_argument("--once", metavar="TEXT", help="ask one question and exit")
    p.set_defaults(func=cmd_chat)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Persian text on Windows consoles
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    settings = load_settings()
    log = EventLog(secrets=settings.secrets())
    log.write("run", command=args.command)
    try:
        code = args.func(args, settings, log)
    except KeyboardInterrupt:
        code = 130
    except (LiaraError, LLMError) as exc:
        log.write("error", command=args.command, status=getattr(exc, "status", 0), error=str(exc))
        print(f"error: {exc}", file=sys.stderr)
        code = 2
    except Exception as exc:  # last-resort guard: log it, show one clean line
        log.write("error", command=args.command, error=f"{type(exc).__name__}: {exc}")
        print(f"error: {exc}", file=sys.stderr)
        code = 1
    log.write("exit", command=args.command, code=code)
    return code


if __name__ == "__main__":
    sys.exit(main())
