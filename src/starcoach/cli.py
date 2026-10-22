"""`starcoach` command line. One subcommand per capability."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import load_settings
from .eventlog import EventLog
from .liara import LiaraClient, LiaraError
from .limits import by_topic


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
    except LiaraError as exc:
        log.write("error", command=args.command, status=exc.status, error=str(exc))
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
