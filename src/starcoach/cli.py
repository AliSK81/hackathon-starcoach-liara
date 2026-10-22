"""`starcoach` command line. One subcommand per capability."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import load_settings
from .eventlog import EventLog


def cmd_version(args, settings, log) -> int:
    print(f"starcoach {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="starcoach",
        description="Liara website assistant: deploy, monitor, diagnose, fix.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    p = sub.add_parser("version", help="show the version")
    p.set_defaults(func=cmd_version)
    return parser


def main(argv: list[str] | None = None) -> int:
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
    except Exception as exc:  # last-resort guard: log it, show one clean line
        log.write("error", command=args.command, error=f"{type(exc).__name__}: {exc}")
        print(f"error: {exc}", file=sys.stderr)
        code = 1
    log.write("exit", command=args.command, code=code)
    return code


if __name__ == "__main__":
    sys.exit(main())
