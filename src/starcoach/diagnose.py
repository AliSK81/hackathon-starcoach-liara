"""Rule-based diagnosis: evidence -> ranked probable causes with fixes (research 06 §3-6).

Deterministic on purpose. The LLM only explains the result; it does not invent causes.
Weights and thresholds are design choices from research 06 §6.1, to be tuned on real incidents.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field

DEFINITIVE, STRONG, MODERATE, WEAK = 60, 30, 15, 5


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: str            # regex over log/event lines ("" for metric/probe rules)
    weight: int
    title_en: str
    title_fa: str
    fix_en: str
    fix_fa: str
    source: str
    platforms: tuple = ()   # empty = all
    action: str = ""        # suggested tool name, if a fix can be applied through the API
    container: bool = False  # symptom rule (crash loop, traceback): never ranked above its child cause


R = Rule
LOG_RULES = [
    R("X-OOM-EVENT", r"stopped due to high ram|high memory usage|oomkilled|exit code:? ?137", DEFINITIVE,
      "The app ran out of memory and Liara stopped it",
      "حافظهٔ برنامه تمام شد و لیارا آن را متوقف کرد",
      "Find the memory leak, or move to a plan with more RAM.",
      "نشتی حافظه را پیدا کنید یا به پلنی با RAM بیشتر بروید.",
      "https://docs.liara.ir/paas/details/events/", action="resize_app"),
    R("N-HEAP", r"javascript heap out of memory|reached heap limit|allocation failed", DEFINITIVE,
      "Node.js ran out of heap memory", "حافظهٔ heap در Node.js تمام شد",
      "Set NODE_OPTIONS=--max-old-space-size to about 75% of plan RAM, fix the leak, or upgrade the plan.",
      "متغیر NODE_OPTIONS=--max-old-space-size را حدود ۷۵٪ RAM پلن بگذارید، نشتی را رفع کنید یا پلن را ارتقا دهید.",
      "https://nodejs.org/api/cli.html#--max-old-space-sizesize-in-mib", ("node", "next"), "resize_app"),
    R("X-ENV-MISSING", r"\b([A-Z][A-Z0-9_]{2,})\b (?:is not set|is missing|not defined|is undefined|is required)",
      STRONG, "A required environment variable is missing", "یک متغیر محیطی لازم تنظیم نشده است",
      "Set the missing variable in the app's environment variables.",
      "متغیر جاافتاده را در تنظیمات متغیرهای محیطی برنامه وارد کنید.",
      "https://docs.liara.ir/paas/details/envs/", action="set_env"),
    R("X-DB-REFUSED", r"econnrefused|connection refused|could not connect to server|sqlstate\[hy000\] \[2002\]",
      STRONG, "The app cannot connect to its database (connection refused)",
      "برنامه به پایگاه داده وصل نمی‌شود (اتصال رد شد)",
      "Check the database is running and the host/port env vars point to it (use the private network host).",
      "بررسی کنید پایگاه داده روشن است و متغیرهای host/port درست به آن اشاره می‌کنند (از شبکهٔ خصوصی استفاده کنید).",
      "https://docs.liara.ir/paas/details/private-network/", action="set_env"),
    R("X-DB-TIMEOUT", r"etimedout|timeout expired|connection timed out", MODERATE,
      "Connections to a backend service time out", "اتصال به یک سرویس پشتیبان timeout می‌شود",
      "Use the private network address; check the database load.",
      "از آدرس شبکهٔ خصوصی استفاده کنید و بار پایگاه داده را بررسی کنید.",
      "https://nodejs.org/api/errors.html#common-system-errors"),
    R("X-DB-MAXCONN", r"too many (?:clients|connections)|remaining connection slots", STRONG,
      "The database has run out of connections", "اتصال‌های پایگاه داده پر شده است",
      "Lower the connection pool size or worker count, or upgrade the database.",
      "اندازهٔ pool یا تعداد workerها را کم کنید یا پایگاه داده را ارتقا دهید.",
      "https://www.postgresql.org/docs/current/runtime-config-connection.html"),
    R("X-DNS", r"enotfound|getaddrinfo|name or service not known", MODERATE,
      "A host name cannot be resolved", "نام یک میزبان پیدا نمی‌شود",
      "Fix the host name in the env vars.", "نام میزبان را در متغیرهای محیطی اصلاح کنید.",
      "https://nodejs.org/api/errors.html#common-system-errors", action="set_env"),
    R("X-PORT-BIND", r"(?:listening|running) on (?:https?://)?(?:127\.0\.0\.1|localhost|\[?::1\]?)[:\s]", DEFINITIVE,
      "The app listens only on localhost, so Liara cannot reach it",
      "برنامه فقط روی localhost گوش می‌دهد و لیارا به آن دسترسی ندارد",
      "Bind the server to 0.0.0.0.", "سرور را روی 0.0.0.0 اجرا کنید.",
      "https://docs.liara.ir/paas/dotnet/fix-common-errors/502-bad-gateway/"),
    R("X-ROFS", r"erofs|read-only file system", STRONG,
      "The app writes to the read-only file system", "برنامه روی فایل‌سیستم فقط‌خواندنی می‌نویسد",
      "Write to tmp/ or attach a disk.", "در پوشهٔ tmp/ بنویسید یا یک دیسک متصل کنید.",
      "https://docs.liara.ir/paas/details/file-system/"),
    R("N-ADDRINUSE", r"eaddrinuse", DEFINITIVE,
      "Two servers try to use the same port", "دو سرور می‌خواهند از یک پورت استفاده کنند",
      "Keep one listen() on the configured port.", "فقط یک listen() روی پورت تنظیم‌شده نگه دارید.",
      "https://nodejs.org/api/errors.html#common-system-errors", ("node", "next")),
    R("N-MODULE", r"cannot find module|module_not_found|err_module_not_found", DEFINITIVE,
      "A Node.js package or file is missing", "یک پکیج یا فایل Node.js پیدا نمی‌شود",
      "Move the package to dependencies, fix the import path case, make sure the build ran.",
      "پکیج را به dependencies منتقل کنید، حروف مسیر import را اصلاح کنید و مطمئن شوید build اجرا شده است.",
      "https://nodejs.org/api/errors.html#module_not_found", ("node", "next", "react", "vue", "angular"),
      "deploy_app"),
    R("N-UNHANDLED", r"unhandledpromiserejection|unhandled ?rejection", STRONG,
      "An unhandled promise rejection crashes the app", "یک promise مدیریت‌نشده برنامه را از کار می‌اندازد",
      "Add await/catch for the failing promise and a global handler that logs.",
      "برای promise خطادار await/catch و یک handler سراسری اضافه کنید.",
      "https://nodejs.org/api/cli.html#--unhandled-rejectionsmode", ("node", "next")),
    R("N-ECONNRESET", r"econnreset|socket hang up", MODERATE,
      "Connections are reset (on Next.js, usually not enough resources)",
      "اتصال‌ها قطع می‌شوند (در Next.js معمولاً کمبود منابع)",
      "Upgrade the plan, then restart.", "پلن را ارتقا دهید و برنامه را ری‌استارت کنید.",
      "https://docs.liara.ir/paas/nextjs/fix-common-errors/econnreset/", (), "resize_app"),
    R("N-NOSTART", r"missing script:? \"?start", DEFINITIVE,
      "package.json has no start script", "فایل package.json اسکریپت start ندارد",
      "Add a \"start\" script.", "یک اسکریپت start اضافه کنید.",
      "https://docs.liara.ir/paas/nodejs/how-tos/deploy-app/", ("node", "next"), "deploy_app"),
    R("PY-MODULE", r"modulenotfounderror: no module named", DEFINITIVE,
      "A Python package is missing", "یک پکیج پایتون نصب نشده است",
      "Add it to requirements.txt and redeploy.", "آن را به requirements.txt اضافه و دوباره دیپلوی کنید.",
      "https://docs.liara.ir/paas/flask/fix-common-errors/module-not-found/",
      ("python", "django", "flask"), "deploy_app"),
    R("PY-WORKER-TIMEOUT", r"worker timeout", DEFINITIVE,
      "A request took longer than the gunicorn timeout", "یک درخواست بیشتر از timeout گانیکورن طول کشید",
      "Find the slow endpoint; raise GUNICORN_TIMEOUT only as a stop-gap.",
      "endpoint کند را پیدا کنید؛ افزایش GUNICORN_TIMEOUT فقط راه موقت است.",
      "https://docs.liara.ir/paas/django/fix-common-errors/worker-timeout/", ("python", "django", "flask"),
      "set_env"),
    R("PY-WORKER-OOM", r"was sent sigkill! perhaps out of memory", STRONG,
      "A gunicorn worker was killed for memory", "یک worker گانیکورن به‌خاطر حافظه کشته شد",
      "Lower GUNICORN_WORKERS or upgrade the plan.", "GUNICORN_WORKERS را کم کنید یا پلن را ارتقا دهید.",
      "https://docs.liara.ir/paas/django/how-tos/set-gunicorn-workers/", ("python", "django", "flask"),
      "resize_app"),
    R("DJ-HOST", r"invalid http_host header|disallowedhost", DEFINITIVE,
      "Django rejects the domain (ALLOWED_HOSTS)", "جنگو دامنه را رد می‌کند (ALLOWED_HOSTS)",
      "Add the Liara subdomain and custom domains to ALLOWED_HOSTS.",
      "زیردامنهٔ لیارا و دامنه‌های خود را به ALLOWED_HOSTS اضافه کنید.",
      "https://docs.djangoproject.com/en/5.2/ref/settings/#allowed-hosts", ("django",)),
    R("DJ-MIGRATE", r"relation \"[^\"]+\" does not exist|no such table", STRONG,
      "Database migrations were not run", "مایگریشن‌های پایگاه داده اجرا نشده‌اند",
      "Run python manage.py migrate.", "دستور python manage.py migrate را اجرا کنید.",
      "https://docs.liara.ir/paas/details/console-shell/", ("django", "python", "flask")),
    R("LV-KEY", r"no application encryption key", DEFINITIVE,
      "Laravel APP_KEY is missing", "کلید APP_KEY لاراول تنظیم نشده است",
      "Run php artisan key:generate --show and set APP_KEY.",
      "دستور php artisan key:generate --show را اجرا و APP_KEY را تنظیم کنید.",
      "https://laravel.com/docs/12.x/encryption", ("laravel",), "set_env"),
    R("LV-STORAGE", r"could not be opened in append mode|failed to open stream: permission denied", STRONG,
      "Laravel cannot write its log or storage files", "لاراول نمی‌تواند فایل لاگ یا storage را بنویسد",
      "Set LOG_CHANNEL=stderr; attach a disk for storage/app.",
      "متغیر LOG_CHANNEL=stderr را بگذارید؛ برای storage/app دیسک متصل کنید.",
      "https://docs.liara.ir/paas/details/file-system/", ("laravel", "php"), "set_env"),
    R("PHP-MEM", r"allowed memory size of \d+ bytes exhausted", DEFINITIVE,
      "One PHP request used more than memory_limit", "یک درخواست PHP از memory_limit بیشتر حافظه مصرف کرد",
      "Fix the heavy query or loop, or raise memory_limit.",
      "کوئری یا حلقهٔ سنگین را اصلاح کنید یا memory_limit را بالا ببرید.",
      "https://www.php.net/manual/en/ini.core.php#ini.memory-limit", ("php", "laravel")),
    R("X-CRASH", r"traceback \(most recent call last\)|php fatal error|uncaught exception|^\s+at .+\(.+:\d+:\d+\)",
      WEAK, "The app throws unhandled errors", "برنامه خطاهای مدیریت‌نشده دارد",
      "Read the first error line before each crash; that is the root cause.",
      "اولین خطا پیش از هر crash را بخوانید؛ علت اصلی همان است.",
      "https://docs.python.org/3/library/exceptions.html", container=True),
]

SYMPTOMS_5XX = re.compile(r"\b(?:GET|POST|PUT|DELETE|PATCH|HEAD)\s+\S+\s+(5\d\d)\b")


@dataclass
class Evidence:
    """Everything the engine looks at. Any part may be missing."""
    app: str = ""
    platform: str = ""
    turned_on: bool = True
    log_lines: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    probe: dict | None = None
    metrics: dict | None = None
    release_state: str = ""
    missing: list[str] = field(default_factory=list)  # sources we could not read


@dataclass
class Cause:
    id: str
    title: str
    title_fa: str
    score: float
    confidence: float
    evidence: list[str]
    fix: str
    fix_fa: str
    source: str
    action: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def confidence(score: float) -> float:
    return round(1 / (1 + math.exp(-(score - 40) / 12)), 2)


def _probe_facts(probe: dict | None) -> dict:
    if not probe:
        return {}
    statuses = probe.get("statuses", [])
    n = len(statuses) or 1
    return {"all_5xx": statuses and all(s >= 500 for s in statuses),
            "all_502": statuses and all(s in (502, 503) for s in statuses),
            "some_5xx": any(s >= 500 for s in statuses),
            "unreachable": statuses and all(s == 0 for s in statuses),
            "ok_ratio": sum(1 for s in statuses if 200 <= s < 400) / n,
            "all_400": statuses and all(s == 400 for s in statuses),
            "p50": probe.get("p50_ms")}


def _peak_pct(metrics: dict | None, kind: str) -> float | None:
    vals = [s.get("max_pct_of_limit") for s in (metrics or {}).get(kind, []) if s.get("max_pct_of_limit") is not None]
    return max(vals) if vals else None


def diagnose(ev: Evidence) -> dict:
    lines = ev.log_lines + ev.events
    probe = _probe_facts(ev.probe)
    mem_pct, cpu_pct = _peak_pct(ev.metrics, "memory"), _peak_pct(ev.metrics, "cpu")
    found: list[Cause] = []

    def add(rule: Rule, score: float, evidence: list[str], action: dict | None = None):
        found.append(Cause(rule.id, rule.title_en, rule.title_fa, score, confidence(score), evidence,
                           rule.fix_en, rule.fix_fa, rule.source, action))

    for rule in LOG_RULES:
        if rule.platforms and ev.platform and ev.platform not in rule.platforms:
            continue
        rx = re.compile(rule.pattern, re.IGNORECASE | re.MULTILINE)
        hits = [l for l in lines if rx.search(l)]
        if not hits:
            continue
        score = rule.weight + min(len(hits), 5) * 2
        if probe.get("some_5xx"):
            score += 10
        action = {"tool": rule.action, "args": {"app": ev.app}} if rule.action else None
        if rule.id == "X-ENV-MISSING":
            name = re.search(rule.pattern, hits[0]).group(1)
            action = {"tool": "set_env", "args": {"app": ev.app, "key": name, "value": "<ask the user>"}}
        if rule.id in ("X-OOM-EVENT", "N-HEAP") and mem_pct is not None and mem_pct < 60:
            score -= 30  # contradicting: memory never got close to the limit
        add(rule, score, [f"log: {h.strip()[:200]}" for h in hits[:3]] + [f"({len(hits)} matching lines)"], action)

    if not ev.turned_on:
        add(Rule("X-OFF", "", DEFINITIVE, "The app is turned off", "برنامه خاموش است",
                 "Turn the app on.", "برنامه را روشن کنید.", "https://docs.liara.ir/paas/details/events/"),
            DEFINITIVE + 20, ["app status: turned off (scale 0)"], {"tool": "start_app", "args": {"app": ev.app}})

    if ev.release_state in ("UNHEALTHY", "FAILED", "TIMEDOUT"):
        add(Rule("X-RELEASE", "", STRONG, f"The last deploy ended as {ev.release_state}",
                 f"آخرین دیپلوی با وضعیت {ev.release_state} تمام شد",
                 "Read the build/runtime logs of that release; fix and redeploy.",
                 "لاگ‌های آن ریلیز را بخوانید، مشکل را رفع و دوباره دیپلوی کنید.",
                 "https://docs.liara.ir/paas/details/health-check/"),
            STRONG, [f"release state: {ev.release_state}"])

    if mem_pct is not None and mem_pct >= 90:
        add(Rule("S-MEM", "", MODERATE, "Memory is near the plan limit", "مصرف حافظه نزدیک سقف پلن است",
                 "Fix leaks or upgrade to a plan with more RAM.", "نشتی را رفع کنید یا پلن با RAM بیشتر بگیرید.",
                 "https://nodejs.org/api/cli.html#--max-old-space-sizesize-in-mib"),
            MODERATE + (15 if mem_pct >= 95 else 0), [f"memory peak {mem_pct}% of plan RAM"],
            {"tool": "resize_app", "args": {"app": ev.app}})
    if cpu_pct is not None and cpu_pct >= 85:
        slow = probe.get("p50") and probe["p50"] > 1500
        add(Rule("S-CPU", "", MODERATE, "CPU is at the plan limit (the app is throttled)",
                 "پردازنده به سقف پلن رسیده (برنامه کند می‌شود)",
                 "Profile the hot path, add caching, or upgrade CPU.",
                 "بخش پرمصرف کد را پیدا کنید، کش اضافه کنید یا CPU را ارتقا دهید.",
                 "https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/"),
            MODERATE + (15 if slow else 0), [f"CPU peak {cpu_pct}% of plan cores"]
            + ([f"median response {probe['p50']} ms"] if slow else []),
            {"tool": "resize_app", "args": {"app": ev.app}})

    # 502 everywhere with no specific cause in the logs: the proxy cannot reach the app.
    if probe.get("all_502") and not any(c.id != "X-CRASH" for c in found):
        add(Rule("X-PORT", "", STRONG, "Liara cannot reach the app (wrong port or the app crashed at start)",
                 "لیارا به برنامه نمی‌رسد (پورت اشتباه یا crash هنگام شروع)",
                 "Make the app listen on 0.0.0.0 and the port set in Liara; check startup logs.",
                 "برنامه را روی 0.0.0.0 و پورت تنظیم‌شده در لیارا اجرا کنید؛ لاگ شروع را ببینید.",
                 "https://docs.liara.ir/paas/liarajson/"),
            STRONG + 25, ["every probe returned 502/503"])
    if probe.get("all_400") and ev.platform == "django":
        for c in found:
            if c.id == "DJ-HOST":
                c.score += 25
                c.confidence = confidence(c.score)

    # 5xx seen but no specific signature: say so instead of guessing.
    access_5xx = [l for l in ev.log_lines if SYMPTOMS_5XX.search(l)]
    specific = [c for c in found if c.id != "X-CRASH"]
    if (probe.get("some_5xx") or access_5xx) and not specific:
        add(Rule("X-APP-ERROR", "", WEAK, "The app returns server errors, cause not identified from logs",
                 "برنامه خطای سرور می‌دهد ولی علت از لاگ‌ها مشخص نیست",
                 "Look at the full error lines in the logs; add logging around the failing route.",
                 "خطاهای کامل را در لاگ ببینید و برای مسیر خطادار لاگ بیشتری اضافه کنید.",
                 "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500"),
            WEAK + 20, [f"{len(access_5xx)} access-log lines with 5xx"] if access_5xx else ["probe saw 5xx"])

    # Container rule: a crash symptom is never ranked above a specific cause.
    if specific:
        found = [c for c in found if c.id != "X-CRASH"]
    found.sort(key=lambda c: c.score, reverse=True)
    # The best cause is always reported (with its confidence) so a weak but real signal is not hidden;
    # further causes only when reasonably likely.
    ranked = found[:1] + [c for c in found[1:] if c.confidence >= 0.3][:2]

    # Site fully up and nothing likely: healthy. Low-confidence findings stay listed as warnings.
    healthy = (probe.get("ok_ratio", 0) == 1 and ev.turned_on
               and (not ranked or ranked[0].confidence < 0.3))
    summary = ("healthy" if healthy else "problem" if ranked else "unclear")
    return {"app": ev.app, "summary": summary,
            "causes": [c.to_dict() for c in ranked],
            "probe": ev.probe, "memory_peak_pct": mem_pct, "cpu_peak_pct": cpu_pct,
            "missing_evidence": ev.missing,
            "verify_steps": ["re-probe the site 5 times: all 2xx", "no new matching error lines after the fix",
                             "no new 'high RAM' or restart events", "memory below 80% of the plan"]}


def gather(client, app: str, minutes: int = 30, probe_tries: int = 5, prober=None) -> Evidence:
    """Collect evidence from every source. A failing source is noted, never fatal."""
    from . import observe

    ev = Evidence(app=app)
    try:
        project = client.get_app(app)
        ev.platform = project.get("type", "")
        ev.turned_on = bool(project.get("scale", 1))
    except Exception as exc:
        ev.missing.append(f"app details: {exc}")
    for name, fetch in (("logs", lambda: observe.get_logs(client, app, minutes, limit=400)),
                        ("events", lambda: observe.get_events(client, app, max(minutes, 120)))):
        try:
            texts = [l["text"] for l in fetch()]
            if name == "logs":
                ev.log_lines = texts
            else:
                ev.events = texts
        except Exception as exc:
            ev.missing.append(f"{name}: {exc}")
    try:
        ev.metrics = observe.get_metrics(client, app, minutes)
    except Exception as exc:
        ev.missing.append(f"metrics: {exc}")
    try:
        releases = client.request("GET", f"/v1/projects/{app}/releases", params={"page": 1, "count": 1})
        items = releases.get("releases") or []
        ev.release_state = (items[0] or {}).get("state", "") if items else ""
    except Exception as exc:
        ev.missing.append(f"releases: {exc}")
    url = observe.app_url(app)
    ev.probe = (prober or observe.probe)(url, tries=probe_tries).to_dict()
    return ev


def verify_fix(client, app: str, cause_ids: list[str], since: float, probe_tries: int = 5,
               prober=None, wait_seconds: float = 90, sleep=None) -> dict:
    """After a fix: wait until the site answers (the app may be restarting), re-probe,
    and look for the old error signatures in logs written after `since`."""
    import time as _time

    from . import observe

    prober = prober or observe.probe
    sleep = sleep or _time.sleep
    url = observe.app_url(app)
    deadline = _time.monotonic() + wait_seconds
    waited = 0
    while _time.monotonic() < deadline:
        if prober(url, tries=1).to_dict()["ok_ratio"] == 1:
            break
        sleep(10)
        waited += 10
    probe = prober(url, tries=probe_tries).to_dict()
    probe["waited_seconds"] = waited
    minutes = max(1, int((_time.time() - since) / 60) + 1)
    try:
        lines = [l for l in observe.get_logs(client, app, minutes, limit=400) if l["ts"] >= since]
    except Exception as exc:
        lines, probe["log_error"] = [], str(exc)
    rules = {r.id: r for r in LOG_RULES}
    still = {}
    for cid in cause_ids:
        rule = rules.get(cid)
        if rule and rule.pattern:
            rx = re.compile(rule.pattern, re.IGNORECASE)
            hits = [l["text"] for l in lines if rx.search(l["text"])]
            if hits:
                still[cid] = hits[:2]
    ok = probe["ok_ratio"] == 1 and not still
    return {"app": app, "fixed": ok,
            "verdict": "fixed" if ok else ("site ok, errors still in logs" if probe["ok_ratio"] == 1
                                           else "not fixed"),
            "probe": probe, "new_log_lines": len(lines), "signatures_still_present": still}
