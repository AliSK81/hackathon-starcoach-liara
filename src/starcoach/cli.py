"""`starcoach` command line. One subcommand per capability."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__, observe
from .agent import Agent
from .config import load_settings
from .deploy import Deployer
from .eventlog import EventLog
from .liara import LiaraClient, LiaraError
from .limits import by_topic
from .llm import ChatLLM, LLMError
from .recommend import hourly_cost, recommend
from .tools import APP_PREFIX, DANGER, build_tools


def cmd_version(args, settings, log) -> int:
    print(f"starcoach {__version__}")
    return 0


def _client(settings, log) -> LiaraClient:
    return LiaraClient(settings.liara_token, settings.liara_api_url, log=log, team_id=settings.liara_team_id)


def cmd_check(args, settings, log) -> int:
    client = _client(settings, log)
    user = client.me().get("user", {})
    apps = client.list_apps()
    print(f"Connected to Liara as {user.get('fullname') or 'unknown user'}. Apps: {len(apps)}.")
    try:
        bal = client.billing()
        print(f"Balance ({bal['account']} account): {bal['balance']:,.0f} Toman.")
    except LiaraError as exc:
        print(f"Balance: not available ({exc}).")
    teams = client.teams()
    if teams and not settings.liara_team_id:
        print("You are in teams: " + ", ".join(f"{t['name']} ({t['id']})" for t in teams)
              + ". Set LIARA_TEAM_ID in .env to work inside a team.")
    elif settings.liara_team_id:
        name = next((t["name"] for t in teams if t["id"] == settings.liara_team_id), "unknown team")
        print(f"Team: {name}.")
    return 0


def cmd_teams(args, settings, log) -> int:
    for t in _client(settings, log).teams():
        mark = " (in use)" if t["id"] == settings.liara_team_id else ""
        print(f"{t['id']}  {t['name']}{mark}")
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


def load_plans(settings, log) -> dict:
    """Plan catalog, or {} when there is no token or Liara is unreachable."""
    if not settings.liara_token:
        return {}
    try:
        return _client(settings, log).plans()
    except LiaraError as exc:
        log.write("warn", where="load_plans", error=str(exc))
        return {}


def cmd_recommend(args, settings, log) -> int:
    plans = load_plans(settings, log)
    advice = recommend(Path(args.dir), plans.get("projects"), plans.get("projectBundlePlans"))
    log.write("result", command="recommend", advice=advice.to_dict())
    print(f"Platform: {advice.platform}   Port: {advice.port}   RAM need: ~{advice.ram_need_mb} MB")
    for r in advice.reasons:
        print(f"  • {r}")
    if advice.plan:
        p = advice.plan
        print(f"Suggested plan: {p['id']} — {p['cpu']} CPU, {p['ram_gb']} GB RAM, "
              f"~{p['price_per_month']:,} Toman/month"
              + (f" + bundle {p['bundle']} {p['bundle_price_per_month']:,}" if p.get("bundle") else "")
              + f" = ~{p['total_per_month']:,} Toman/month (~{p['total_per_hour']:,.0f}/hour)")
    elif not plans:
        print("Plan: set LIARA_API_TOKEN to get a plan from your account's real plan list.")
    for w in advice.warnings:
        print(f"  ⚠️  {w}")
    return 0


def confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    return input(f"{question} Type yes / بله: ").strip().lower() in ("y", "yes", "بله", "آره")


def cmd_create(args, settings, log) -> int:
    name = args.name if args.name.startswith(APP_PREFIX) else APP_PREFIX + args.name
    client = _client(settings, log)
    plans = client.plans()
    per_hour = hourly_cost(plans.get("projects"), plans.get("projectBundlePlans"), args.plan, args.bundle)
    balance = client.billing().get("balance")
    cost = f"about {per_hour:,.0f} Toman/hour" if per_hour else "an hourly cost"
    if per_hour and balance is not None and balance < per_hour * 24:
        print(f"Your balance is {balance:,.0f} Toman. This app costs {cost} "
              f"(~{per_hour * 24:,.0f} per day). Liara will likely refuse it. Top up in the console first.")
        log.write("warn", command="create", balance=balance, per_hour=per_hour)
        return 6
    if not confirm(f"Create app {name} ({args.platform}, plan {args.plan}, bundle {args.bundle})? "
                   f"It costs {cost}.", args.yes):
        log.write("rejected", command="create", app=name)
        print("Not created.")
        return 1
    result = client.create_app(name, args.platform, args.plan, args.bundle, args.network)
    log.write("result", command="create", result=result)
    print(f"Created {name} on network {result['network']}.")
    return 0


def print_deploy_event(kind, data):
    if kind == "packed":
        print(f"  📦 packed {data['files']} files ({data['size_kb']} KB)")
    elif kind == "uploaded":
        print("  ⬆️  uploaded")
    elif kind == "release_created":
        print(f"  🚀 release {data['release_id']} ({data['platform']}, port {data['port']})")
    elif kind == "state":
        print(f"  ⏳ state: {data['state']}")
    elif kind == "build_log":
        for line in data["lines"]:
            print(f"     {line[:160]}")


def cmd_deploy(args, settings, log) -> int:
    if not confirm(f"Deploy {args.dir} to {args.app}? This replaces the live version.", args.yes):
        print("Not deployed.")
        return 1
    result = Deployer(_client(settings, log), on_event=print_deploy_event).deploy(
        Path(args.dir), args.app, port=args.port, message=args.message)
    log.write("result", command="deploy", result=result.to_dict())
    if result.ok:
        print(f"✅ Live: {result.url} ({result.seconds}s)")
        return 0
    print(f"❌ Deploy ended in state {result.state or 'unknown'}. {result.fail_reason}")
    if result.explanation:
        print(f"   Cause: {result.explanation['cause']}\n   Fix: {result.explanation['fix']}"
              f"\n   Evidence: {result.explanation['evidence']}")
    else:
        for line in (result.error_lines or result.last_lines)[-10:]:
            print(f"   {line}")
    print("   The previous version, if there was one, is still live.")
    return 3


def _fmt_time(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "--:--:--"


def cmd_logs(args, settings, log) -> int:
    lines = observe.get_logs(_client(settings, log), args.app, args.minutes, args.errors, args.limit)
    if not lines:
        print(f"No logs in the last {args.minutes} minutes.")
    for l in lines:
        mark = "!" if l["type"] == "stderr" else " "
        print(f"{_fmt_time(l['ts'])} {mark} {l['text'][:300]}")
    return 0


def cmd_events(args, settings, log) -> int:
    events = observe.get_events(_client(settings, log), args.app, args.minutes)
    if not events:
        print("No events.")
    for e in events:
        print(f"{_fmt_time(e['ts'])}  {e['text'][:300]}")
    return 0


def cmd_metrics(args, settings, log) -> int:
    m = observe.get_metrics(_client(settings, log), args.app, args.minutes)
    log.write("result", command="metrics", metrics=m)
    lim = m["limits"]
    print(f"Plan {lim['plan']}: {lim['cpu_cores']} CPU cores, {lim['ram_gb']} GB RAM. Last {m['minutes']} min:")
    for s in m["cpu"]:
        print(f"  CPU  {s['instance']}: last {s['last']:.3f}  max {s['max']:.3f}"
              + (f"  ({s['max_pct_of_limit']}% of limit)" if "max_pct_of_limit" in s else ""))
    for s in m["memory"]:
        print(f"  RAM  {s['instance']}: last {s['last_mb']} MB  max {s['max_mb']} MB"
              + (f"  ({s['max_pct_of_limit']}% of limit)" if "max_pct_of_limit" in s else ""))
    if not (m["cpu"] or m["memory"]):
        print("  No metric data (the app may be off or new).")
    print(f"  note: {m['units_note']}")
    return 0


def cmd_health(args, settings, log) -> int:
    r = observe.probe(observe.app_url(args.target), tries=args.tries).to_dict()
    log.write("result", command="health", probe=r)
    print(f"{r['url']}: {int(r['ok_ratio'] * 100)}% OK over {r['tries']} tries, "
          f"p50 {r['p50_ms']} ms, max {r['max_ms']} ms, statuses {r['statuses']}")
    for e in r["errors"][:3]:
        print(f"  ❌ {e}")
    return 0 if r["ok_ratio"] == 1 else 4


def print_diagnosis(result: dict) -> None:
    print(f"App {result['app']}: {result['summary'].upper()}")
    pr = result.get("probe") or {}
    if pr:
        print(f"  site: {int(pr.get('ok_ratio', 0) * 100)}% OK, statuses {pr.get('statuses')}, p50 {pr.get('p50_ms')} ms")
    for i, c in enumerate(result["causes"], 1):
        print(f"  {i}. {c['title']} — confidence {int(c['confidence'] * 100)}% [{c['id']}]")
        for e in c["evidence"][:3]:
            print(f"       evidence: {e}")
        print(f"       fix: {c['fix']}")
        if c.get("action"):
            print(f"       can do: {c['action']['tool']} {c['action']['args']}")
    for m in result.get("missing_evidence", []):
        print(f"  (could not read {m})")


def cmd_diagnose(args, settings, log) -> int:
    from . import diagnose as dg
    result = dg.diagnose(dg.gather(_client(settings, log), args.app, args.minutes))
    log.write("result", command="diagnose", result=result)
    print_diagnosis(result)
    return 0


def cmd_verify(args, settings, log) -> int:
    from . import diagnose as dg
    since = time.time() - args.since_minutes * 60
    r = dg.verify_fix(_client(settings, log), args.app, args.causes or [], since, wait_seconds=args.wait)
    log.write("result", command="verify", result=r)
    print(f"Verdict: {r['verdict']}. Site {int(r['probe']['ok_ratio'] * 100)}% OK "
          f"{r['probe']['statuses']}, {r['new_log_lines']} new log lines, waited {r['probe']['waited_seconds']}s.")
    for cid, lines in r["signatures_still_present"].items():
        print(f"  still seen {cid}: {lines[0][:160]}")
    return 0 if r["fixed"] else 5


def cmd_eval(args, settings, log) -> int:
    import json as _json

    from .evaluate import evaluate
    out = []
    for path in args.sets:
        r = evaluate(Path(path))
        out.append(r)
        print(f"{r['set']}: {r['cases']} cases — engine top-1 {r['engine_top1']:.0%}, "
              f"top-3 {r['engine_top3']:.0%}; naive baseline top-1 {r['baseline_top1']:.0%}")
        for row in r["rows"]:
            if not row["engine_top1"]:
                print(f"   miss: {row['name']}: expected {row['expect']}, got {row['engine']}")
    Path("results").mkdir(exist_ok=True)
    Path("results/diagnosis-eval.json").write_text(_json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    log.write("result", command="eval", summary=[{k: r[k] for k in ("set", "cases", "engine_top1", "baseline_top1")} for r in out])
    print("saved results/diagnosis-eval.json")
    return 0


def cmd_set_env(args, settings, log) -> int:
    if not confirm(f"Set {args.key} on {args.app}? Liara restarts the app.", args.yes):
        print("Not changed.")
        return 1
    r = _client(settings, log).set_env(args.app, args.key, args.value)
    log.write("result", command="set-env", app=args.app, key=args.key, env_count=r["env_count"])
    print(f"Set {args.key}. The app restarts now ({r['env_count']} env vars).")
    return 0


def cmd_restart(args, settings, log) -> int:
    if not confirm(f"Restart {args.app}? The site is briefly unavailable.", args.yes):
        print("Not restarted.")
        return 1
    _client(settings, log).restart(args.app)
    log.write("result", command="restart", app=args.app)
    print(f"Restart of {args.app} sent. Check it with: starcoach verify {args.app}")
    return 0


def cmd_scale(args, settings, log) -> int:
    on = args.command == "start"
    if not on:
        typed = args.app if args.yes else input(
            f"Turning {args.app} off takes the site down. Type the app name to approve: ").strip()
        if typed != args.app:
            print("Not changed.")
            return 1
    _client(settings, log).scale(args.app, on)
    print(f"{args.app} is turning {'on' if on else 'off'}.")
    return 0


def cmd_resize(args, settings, log) -> int:
    typed = args.app if args.yes else input(
        f"Move {args.app} to plan {args.plan}? This changes the cost. Type the app name to approve: ").strip()
    if typed != args.app:
        print("Not changed.")
        return 1
    _client(settings, log).resize(args.app, args.plan)
    log.write("result", command="resize", app=args.app, plan=args.plan)
    print(f"Resize of {args.app} to {args.plan} submitted.")
    return 0


def cmd_web(args, settings, log) -> int:
    from .web import serve

    def factory(approver, on_event):
        return make_agent(settings, log, approver=approver, on_event=on_event)

    server = serve(factory, args.host, args.port, log=log)
    print(f"StarCoach web chat: http://{args.host}:{args.port}  (Ctrl+C to stop)")
    if not settings.llm_base_url:
        print("  note: LLM_BASE_URL is not set; the chat will report that until .env is filled in.")
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


def cmd_watch(args, settings, log) -> int:
    from .watch import Watcher
    w = Watcher(_client(settings, log), args.apps, log=log, auto_restart=args.auto_restart)
    print(f"Watching {', '.join(args.apps)} every {args.interval}s. Alerts: results/alerts.jsonl"
          + ("  (auto-restart ON, max once per hour)" if args.auto_restart else ""))
    try:
        w.run(args.interval, cycles=1 if args.once else args.cycles)
    except KeyboardInterrupt:
        print("stopped.")
    return 0


def cmd_domain(args, settings, log) -> int:
    from . import domains
    client = _client(settings, log) if (args.add or args.check or args.ssl) else None
    info = {}
    if args.add:
        if not confirm(f"Add {args.domain} to {args.app}?", args.yes):
            print("Not added.")
            return 1
        info = domains.add_domain(client, args.app, args.domain)
        log.write("result", command="domain-add", app=args.app, domain=args.domain, status=info.get("status"))
        print(f"Added. Status: {info.get('status')}")
    elif args.check or args.ssl:
        found = [d for d in domains.list_domains(client, args.app) if d["name"] == args.domain]
        if not found:
            print(f"{args.domain} is not on {args.app} yet. Use --add first.")
            return 1
        info = domains.check_domain(client, found[0]["id"])
        print(f"Status: {info.get('status')}   SSL: {info.get('ssl')}")
        if args.ssl:
            domains.enable_ssl(client, args.domain)
            print("SSL requested (Let's Encrypt). Check again in a few minutes.")
    g = domains.guide(args.domain, info.get("cname_target"), info.get("txt_verification"))
    print(f"\nSteps you do at {g['registrar']} (the Liara API cannot do these):")
    for i, (fa, en) in enumerate(zip(g["steps_fa"], g["steps_en"], strict=True), 1):
        print(f"  {i}. {fa}\n     {en}")
    print("Records (if you keep your own DNS):")
    for r in g["records"]:
        print(f"  {r['type']:<12} {r['name']:<16} {r['value']}")
    print(g["after"])
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
    shown = tool.safe_args(args)
    if tool.risk == DANGER:  # high consequence: the user types the app name (research 05)
        typed = input(f"  ⛔ {tool.name} {shown} is high-risk. Type the app name to approve: ").strip()
        return bool(args.get("app")) and typed == args.get("app")
    answer = input(f"  Run {tool.name} {shown}? Type yes / بله to approve: ").strip().lower()
    return answer in ("y", "yes", "بله", "آره", "ok")


def make_agent(settings, log, approver=terminal_approver, on_event=None):
    llm = ChatLLM(settings.llm_base_url, settings.llm_model, settings.llm_api_key, log=log)
    tools = build_tools(_client(settings, log), on_event=on_event)
    return Agent(llm, tools, approver, on_event=on_event, log=log)


def cmd_chat(args, settings, log) -> int:
    def show(kind, data):
        if kind in STATUS_LINES:
            print(STATUS_LINES[kind](data))
        else:
            print_deploy_event(kind, data)

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
    p = sub.add_parser("teams", help="list your Liara teams (use one with LIARA_TEAM_ID)")
    p.set_defaults(func=cmd_teams)
    p = sub.add_parser("apps", help="list your Liara apps")
    p.set_defaults(func=cmd_apps)
    p = sub.add_parser("status", help="show one app's state and instances")
    p.add_argument("app")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("recommend", help="look at a project folder and suggest platform, port and plan")
    p.add_argument("dir", nargs="?", default=".")
    p.set_defaults(func=cmd_recommend)
    p = sub.add_parser("create", help="create a Liara app (asks first; costs money)")
    p.add_argument("name")
    p.add_argument("--platform", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--bundle", required=True, help="feature bundle plan id")
    p.add_argument("--network", default=None)
    p.add_argument("--yes", action="store_true", help="skip the question")
    p.set_defaults(func=cmd_create)
    p = sub.add_parser("deploy", help="upload a folder and release it (asks first)")
    p.add_argument("dir")
    p.add_argument("--app", required=True)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--message", default="")
    p.add_argument("--yes", action="store_true", help="skip the question")
    p.set_defaults(func=cmd_deploy)
    p = sub.add_parser("logs", help="recent app logs")
    p.add_argument("app")
    p.add_argument("--minutes", type=int, default=30)
    p.add_argument("--errors", action="store_true", help="only error-looking lines")
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(func=cmd_logs)
    p = sub.add_parser("events", help="app events (restarts, kills, high RAM)")
    p.add_argument("app")
    p.add_argument("--minutes", type=int, default=24 * 60)
    p.set_defaults(func=cmd_events)
    p = sub.add_parser("metrics", help="CPU and RAM against the plan limits")
    p.add_argument("app")
    p.add_argument("--minutes", type=int, default=30)
    p.set_defaults(func=cmd_metrics)
    p = sub.add_parser("health", help="probe the site URL: status codes and latency")
    p.add_argument("target", help="app name or URL")
    p.add_argument("--tries", type=int, default=5)
    p.set_defaults(func=cmd_health)
    p = sub.add_parser("diagnose", help="find probable causes of errors or slowness, with fixes")
    p.add_argument("app")
    p.add_argument("--minutes", type=int, default=30)
    p.set_defaults(func=cmd_diagnose)
    p = sub.add_parser("verify", help="after a fix: re-probe and check old errors are gone")
    p.add_argument("app")
    p.add_argument("--causes", nargs="*", help="cause ids from diagnose")
    p.add_argument("--since-minutes", type=float, default=5)
    p.add_argument("--wait", type=int, default=90, help="seconds to wait for the app to come back")
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("eval", help="score the diagnosis engine on labelled incidents vs a baseline")
    p.add_argument("sets", nargs="*", default=["evals/incidents_dev.json", "evals/incidents_holdout.json",
                                               "evals/incidents_holdout2.json"])
    p.set_defaults(func=cmd_eval)
    p = sub.add_parser("set-env", help="set one env var (asks first; restarts the app)")
    p.add_argument("app")
    p.add_argument("key")
    p.add_argument("value")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_set_env)
    p = sub.add_parser("restart", help="restart an app (asks first)")
    p.add_argument("app")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_restart)
    for name, help_text in (("start", "turn an app on"), ("stop", "turn an app off (type the name to approve)")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("app")
        p.add_argument("--yes", action="store_true")
        p.set_defaults(func=cmd_scale)
    p = sub.add_parser("resize", help="change an app's plan (type the name to approve)")
    p.add_argument("app")
    p.add_argument("plan")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_resize)
    p = sub.add_parser("web", help="open the local web chat")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8790)
    p.set_defaults(func=cmd_web)
    p = sub.add_parser("watch", help="check apps on a schedule; alert once per change; diagnose on failure")
    p.add_argument("apps", nargs="+")
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--cycles", type=int, default=None)
    p.add_argument("--once", action="store_true")
    p.add_argument("--auto-restart", action="store_true", help="restart a down app (max once per hour)")
    p.set_defaults(func=cmd_watch)
    p = sub.add_parser("domain", help="connect a custom domain: API steps plus registrar (IRNIC) guide")
    p.add_argument("app")
    p.add_argument("domain")
    p.add_argument("--add", action="store_true", help="add the domain to the app (asks first)")
    p.add_argument("--check", action="store_true", help="show the domain's DNS and SSL status")
    p.add_argument("--ssl", action="store_true", help="request a free SSL certificate")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_domain)
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
