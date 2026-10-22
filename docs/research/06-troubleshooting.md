# 06 - Troubleshooting rule base for the diagnosis engine

Research date: 2026-10-22. This file is the rule base for StarCoach's deterministic diagnosis engine. The engine maps evidence (logs, app and release status, events, CPU/RAM vs plan limits, HTTP probes, recent releases and env changes) to a ranked list of probable causes with fixes. The LLM layer only explains the ranked result. It does not invent causes.

Conventions:
- Every claim cites a URL. Liara doc pages are in Persian; quotes are translated.
- **Design choice** marks a number or rule we chose for the engine. These come from no source and can be tuned.
- Evidence source names (`release.state`, `events`, `metrics.memory`, `logs`) refer to the API surfaces in `docs/research/03-liara-logs-metrics.md`.

---

## 1. Liara platform facts that drive diagnosis

| # | Fact | Diagnostic consequence | Source |
|---|---|---|---|
| L1 | Every request goes through Liara's reverse proxy before reaching the app, so the app sees the proxy address unless it trusts `X-Forwarded-For` / `X-Real-IP`. | 502/504 are produced by the proxy when the container does not answer. Wrong client IP, rate-limit-per-IP bugs and "https" detection issues come from missing trusted-proxy config. | https://docs.liara.ir/paas/nodejs/how-tos/configure-trusted-proxy/about/ |
| L2 | The app must listen on the port set in `liara.json` `port` (or given to `liara deploy --port`). The docs' examples use 3000, 3005 and 8000. | Port mismatch means the proxy cannot reach the app, so every request returns 502. | https://docs.liara.ir/paas/liarajson/ , https://docs.liara.ir/paas/nodejs/how-tos/deploy-app/ , https://docs.liara.ir/paas/python/how-tos/deploy-app/ |
| L3 | Liara's only explicit 502 page (.NET): the app defaults to `http://0.0.0.0:80`. If it is changed to `http://localhost:5000`, you see 502. The fix is `UseUrls("http://0.0.0.0:5000")` plus `liara deploy --port 5000`. | Generalises to every platform: bind to `0.0.0.0` (not `localhost`/`127.0.0.1`) **and** on the declared port. The generalisation is our inference, backed by the same rule on Fly.io and Render (rows G1, G2). | https://docs.liara.ir/paas/dotnet/fix-common-errors/502-bad-gateway/ |
| L4 | Docker apps expose only one HTTP port. `EXPOSE` is optional because Liara asks for the port at deploy time. | For Docker, check `liara.json` `port` against the port the process actually binds. | https://docs.liara.ir/paas/docker/how-tos/deploy-app/ |
| L5 | Health check (`liara.json` `healthCheck`: `command`, `interval`, `timeout`, `retries`, `startPeriod`). A new deploy gets no traffic until the check passes; the previous release keeps serving. If a live app fails its checks later, **Liara restarts it automatically**. | Release stuck `UNHEALTHY` with the old release still serving means a new-release problem, not an outage. Repeated restarts of a live app plus failing checks means the app hangs (event-loop block, deadlock, DB wait). | https://docs.liara.ir/paas/details/health-check/ |
| L6 | Zero-downtime deploy is on by default. A new release runs in the background; if it does not start and stay stable, the deploy is cancelled. It can be disabled in settings. **Bronze software plan has no zero-downtime deploy.** | On Bronze, a bad deploy causes a real outage, and the 502/503 window during every deploy is expected. On Silver/Gold, a failed deploy usually means "site still up on the old version". | https://docs.liara.ir/paas/details/zero-downtime-deployment/ , https://docs.liara.ir/paas/details/plans/software-plans/ |
| L7 | Event types: SIGKILL (usually after a new deploy), SIGSTOP, waiting to run, running, **app turned off** (unreachable, possibly after a severe error), **app stopped due to high RAM usage**. | The "high RAM" event is Liara's user-visible OOM-kill signal. A SIGKILL right after a deploy is normal and is not evidence of a crash. | https://docs.liara.ir/paas/details/events/ |
| L8 | Hardware plans (CPU cores / RAM GB): Earth 0.5/0.512, Mars 1/1, Jupiter 1/2, Saturn 2/4, Uranus 4/8, Neptune 8/16, Pluto 16/32. | Denominators for the "% of plan limit" metrics. | https://docs.liara.ir/paas/details/plans/hardware-plans/ |
| L9 | Software plans: max build time Bronze 5 min, Silver 10 min, Gold 20 min. Log retention 7 / 30 / 60 days. Max source upload 128 MB (Bronze) or 256 MB. Deploys per day 20 / 50 / unlimited. | A build cut off near the plan's build-time limit is a timeout, not a code error. Log lookback is capped by plan. | https://docs.liara.ir/paas/details/plans/software-plans/ |
| L10 | Hardware reports show CPU, memory, inbound and outbound traffic, up to 60 days back, with live mode. | Metric evidence is available. HTTP status and latency metrics are **not**, so the engine must probe or parse access logs (see 03, section 5). | https://docs.liara.ir/paas/details/observations/hardware/ |
| L11 | The filesystem is read-only by default. Only `tmp/` is writable (100 MB). A writable mode can be switched on in settings, but its changes are lost on restart or redeploy. Docker and Next.js are writable by default. Persistent data needs a disk. | Writes outside `tmp/` fail (EROFS / "Read-only file system" / Laravel "could not be opened in append mode"). Uploads that "disappear" after a deploy mean no disk is attached. | https://docs.liara.ir/paas/details/file-system/ |
| L12 | Liara installs packages from its own mirror. New packages may fail; turn it off with `"mirror": false` (Node, Next, Python, Django, Flask, React, Angular, Vue) or `"composerMirror": false` (Laravel, PHP). | A build failing on "package not found / no matching distribution" right after adding a new dependency means: try with the mirror off. | https://docs.liara.ir/paas/liarajson/ , https://docs.liara.ir/paas/nodejs/how-tos/deploy-app/ |
| L13 | Do not put `app` and `platform` fields in `liara.json`; the docs say this avoids deploy failures. | A deploy failing with `liara.json` that has `platform` set to the wrong value: remove the field. | https://docs.liara.ir/paas/nodejs/how-tos/deploy-app/ , https://docs.liara.ir/paas/python/how-tos/deploy-app/ |
| L14 | `build.location` (default Iran; can be `germany`) helps when packages are not reachable from Iran. | Build timeouts or 403 errors while downloading dependencies point to sanctions or network blocks. Fix: `build.location: germany` or `/paas/details/dns-server-settings/`. | https://docs.liara.ir/paas/liarajson/ , https://docs.liara.ir/paas/details/about/ |
| L15 | Apps reach databases on the private network using the app or database ID as the host. Both must be on the same private network, and that network cannot be changed after creation. | `ECONNREFUSED` / `ENOTFOUND` / timeout to the DB host after "moving" the DB means the two are on different networks or the wrong host is used. | https://docs.liara.ir/paas/details/private-network/ |
| L16 | `liara logs` flags: `-a app`, `-s/--since "1 hour ago"`, `-f/--follow`, `-t/--timestamps`, `-r/--release v2`. | `-r` lets the engine compare logs of the failing release with the last good release. | https://docs.liara.ir/references/cli/see-app-logs/ |

### Platform-specific Liara facts

| # | Platform | Fact | Source |
|---|---|---|---|
| P1 | Django / Flask | Liara runs gunicorn. The default worker timeout is 30 s; raise it with the env var `GUNICORN_TIMEOUT` (seconds). The error appears as `WORKER TIMEOUT`. | https://docs.liara.ir/paas/django/fix-common-errors/worker-timeout/ |
| P2 | Django | Default `GUNICORN_WORKERS` = 3. | https://docs.liara.ir/paas/django/how-tos/set-gunicorn-workers/ |
| P3 | Django | Liara finds `settings.py` and appends its own config (disable with `modifySettings: false`). It runs `collectstatic` on every deploy (disable with `collectStatic: false`). `requirements.txt` is required. | https://docs.liara.ir/paas/django/how-tos/deploy-app/ |
| P4 | Django | `SECRET_KEY` is created automatically when the app is created. | https://docs.liara.ir/paas/django/how-tos/set-envs/ |
| P5 | Django / Flask | The nginx in front of the app limits uploads to 1 MB by default. Fix: `liara_nginx.conf` in the project root with `client_max_body_size 250M;`, then redeploy. Symptom: 413. | https://docs.liara.ir/paas/django/fix-common-errors/upload-limit-size/ , https://docs.liara.ir/paas/flask/fix-common-errors/about/ |
| P6 | Flask | Liara runs `gunicorn app:app`. A different module name gives `ModuleNotFoundError: No module named 'app'`. Fix: rename the module, or set `{"flask": {"appModule": "name:app"}}`. | https://docs.liara.ir/paas/flask/fix-common-errors/module-not-found/ |
| P7 | Python (generic) | Default start command is `python3 main.py` unless `args` is set. | https://docs.liara.ir/paas/python/how-tos/deploy-app/ |
| P8 | Node / Next.js | `npm run build` runs if a `build` script exists; a `start` script is required. | https://docs.liara.ir/paas/nextjs/how-tos/deploy-app/ , https://docs.liara.ir/paas/nodejs/how-tos/deploy-app/ |
| P9 | Next.js | `ECONNRESET` on Liara is mainly caused by insufficient resources. Fix: upgrade the plan, then restart once. | https://docs.liara.ir/paas/nextjs/fix-common-errors/econnreset/ |
| P10 | Next.js | `Could not modify config file`: a customised `next.config.js` stops Liara from injecting its settings. Fix: add `output: 'standalone'` (Next 12.2 and later) and redeploy. | https://docs.liara.ir/paas/nextjs/fix-common-errors/modify-config-file/ |
| P11 | Laravel | Liara runs `php artisan storage:link` automatically. `configCache` / `routeCache` in `liara.json` cache config and routes (route cache fails if routes use closures). Delete `composer.lock` for a successful deploy (Liara doc advice). Dev dependencies are skipped unless `installDevDependencies: true`. | https://docs.liara.ir/paas/laravel/how-tos/deploy-app/ |
| P12 | Laravel | `419 Sorry, your session has expired` comes from CSRF/session failure. Liara's fix: `SESSION_DRIVER=cookie`. | https://docs.liara.ir/paas/laravel/fix-common-errors/419-page-expired/ |
| P13 | Laravel / PHP | Upload limit errors above 100 MB have their own fix page. | https://docs.liara.ir/paas/laravel/fix-common-errors/about/ , https://docs.liara.ir/paas/php/fix-common-errors/about/ |

---

## 2. What each HTTP status means on a PaaS container

| Status | Meaning (source) | Typical PaaS causes (ranked) |
|---|---|---|
| **500** | The app itself answered with an error. | Unhandled exception in app code; missing env var or secret (APP_KEY, DB URL); DB down; migrations not run; read-only filesystem write. The stack trace is in the app logs. |
| **502** | "a gateway or proxy got an invalid response from an upstream server" (https://developer.mozilla.org/en-US/docs/Glossary/502). | 1) The app is not listening on the expected port/address (L2, L3). 2) The app crashed or is restarting (crash loop, OOM). 3) The app closed the connection without a response (Heroku H13 analogue, https://devcenter.heroku.com/articles/error-codes). Fly.io notes intermittent 502s can indicate OOM kills (https://docs.fly.io/getting-started/troubleshooting). Render lists "never had a successful deploy" and a wrong host/port as causes (https://render.com/docs/troubleshooting-deploys). |
| **503** | "the server is not ready to handle the request"; common causes are maintenance or overload, and some apps reject with 503 when memory, CPU or connection-pool limits are met (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/503). | App stopped / scale 0 (Heroku H14 analogue), all instances failing health checks ("If all your Machines fail health checks, your users get 503s", https://docs.fly.io/getting-started/troubleshooting), boot not finished (Heroku H20), crashed app (Heroku H10, which returns status 503). |
| **504** | The proxy "did not receive any HTTP response from the origin within a certain time" (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/504). | Slow request: a slow DB query, an external API call, CPU throttling, gunicorn sync workers all busy. On Heroku the equivalent router limit is 30 s (H12, https://devcenter.heroku.com/articles/error-codes). Liara's proxy timeout is **undocumented** (see open questions). |
| **413** | Request body too large. | nginx 1 MB default on Django/Flask (P5). |
| **419** | Laravel CSRF/session. | P12. |
| **400 on every request (Django)** | With `DEBUG=False`, a missing or wrong `ALLOWED_HOSTS` makes every request return "Bad Request (400)" (https://docs.djangoproject.com/en/5.2/ref/settings/#allowed-hosts). `DisallowedHost` is a `SuspiciousOperation` and becomes `HttpResponseBadRequest` (https://docs.djangoproject.com/en/5.2/ref/exceptions/). | Custom domain added but not in `ALLOWED_HOSTS`. |

---

## 3. Rule base: log signatures, causes and fixes

Format: **ID | signature (regex, case-insensitive) | where | cause | fix | weight class | source**. Weight classes are defined in section 6.

### 3.1 Cross-platform / runtime

| ID | Signature | Cause | Fix | Class | Source |
|---|---|---|---|---|---|
| X-OOM-1 | event "stopped due to high RAM usage" (Liara event type) | Container killed for exceeding RAM | Find a leak (memory climbing over hours) or upgrade the plan; cap the runtime heap below the plan RAM | Definitive | https://docs.liara.ir/paas/details/events/ |
| X-OOM-2 | `OOMKilled` / exit code `137` in applet `reason` or state | Kernel OOM kill (K8s reason string) | Same as X-OOM-1 | Definitive | https://kubernetes.io/docs/tasks/configure-pod-container/assign-memory-resource/ |
| X-OOM-3 | memory metric at ≥ 95% of plan RAM followed by a restart or kill event within 2 min | Reactive OOM: K8s may let usage exceed the limit and kill only under memory pressure | Same | Strong | https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/ (window is a design choice) |
| X-LEAK | memory rising steadily across restarts or over hours, sawtooth pattern | "Steadily climbing memory usage typically indicates a leak" | Heap snapshot; for gunicorn use `max_requests` to recycle workers | Moderate | https://render.com/docs/troubleshooting-deploys , https://github.com/benoitc/gunicorn/blob/19.4.5/docs/source/settings.rst |
| X-CRASHLOOP | ≥ 3 restart/kill/"turned off" events in 15 min, or applet state shows back-off | Crash loop. The K8s back-off is 10 s, 20 s, 40 s … capped at 300 s, and resets after 10 min of healthy running. | Read the first error in the logs **before** each restart; that is the root cause | Strong (but only as a container rule: it needs a child cause) | https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/ |
| X-PORT-1 | probe returns 502 for every path, the process logs "listening on" with a port ≠ `liara.json` port | Port mismatch | Set `port` in `liara.json` (or `--port`) to the app's port, or make the app read the port | Definitive when both ports are known | https://docs.liara.ir/paas/liarajson/ , https://docs.liara.ir/paas/dotnet/fix-common-errors/502-bad-gateway/ |
| X-PORT-2 | logs show a bind to `127.0.0.1`, `localhost` or `::1` | Bound to loopback, so the proxy cannot reach the app | Bind `0.0.0.0` | Definitive | https://docs.liara.ir/paas/dotnet/fix-common-errors/502-bad-gateway/ , https://docs.fly.io/getting-started/troubleshooting |
| X-PORT-3 | release `UNHEALTHY` and health-check command port ≠ app port | Health check targets the wrong port ("the port in the command must match your app's port") | Fix `healthCheck.command` | Strong | https://docs.liara.ir/paas/details/health-check/ |
| X-HC-SLOW | release `UNHEALTHY`, the app logs "listening" late (after `startPeriod`) | Slow boot (migrations, DB connect, large preload) | Increase `startPeriod`; Fly suggests 15–30 s for Rails/Django/JVM | Moderate | https://docs.liara.ir/paas/details/health-check/ , https://docs.fly.io/getting-started/troubleshooting |
| X-ROFS | `EROFS`, `Read-only file system`, `Permission denied` on a path outside `/tmp` | Read-only filesystem | Write to `tmp/`, attach a disk, or enable writable FS (temporary) | Strong | https://docs.liara.ir/paas/details/file-system/ |
| X-DB-REFUSED | `ECONNREFUSED`, `Connection refused`, `could not connect to server`, `SQLSTATE[HY000] [2002]` | DB down, wrong host or port, not on the same private network | Check DB status; use the private host (DB id); join the same network | Strong | https://nodejs.org/api/errors.html#common-system-errors , https://docs.liara.ir/paas/details/private-network/ |
| X-DB-TIMEOUT | `ETIMEDOUT`, `timeout expired`, `Connection timed out` to the DB host | Network path blocked (public access disabled while the app connects over the public host), DB overloaded | Use the private network; check DB metrics | Moderate | https://nodejs.org/api/errors.html#common-system-errors , https://docs.liara.ir/paas/details/private-network/ |
| X-DB-MAXCONN | `too many clients`, `too many connections`, `remaining connection slots are reserved` | Connection pool × workers > DB `max_connections` (Postgres default is typically 100) | Lower pool size or workers, add a pooler, upgrade the DB | Strong | https://www.postgresql.org/docs/current/runtime-config-connection.html |
| X-DNS | `ENOTFOUND`, `getaddrinfo`, `Name or service not known` | Wrong host env var / DNS | Fix the host env var; Liara supports custom DNS servers | Moderate | https://docs.liara.ir/paas/details/dns-server-settings/ (linked from https://docs.liara.ir/paas/details/about/) |
| X-ENV | log mentions an undefined or missing env var right after an **env change** event or a new release | Missing or misnamed env var | Diff env vars against the last good release | Strong when correlated with a change | https://docs.liara.ir/paas/details/envs/ (temporal correlation is a design choice) |
| X-MIRROR | build log: package not found or no matching version just after a dependency change | Liara mirror lacks the package | `"mirror": false` / `"composerMirror": false` | Moderate | https://docs.liara.ir/paas/liarajson/ |
| X-BUILD-TIME | release `TIMEDOUT`, or build duration ≈ plan build-time limit (5/10/20 min) | Build-time limit | Cache deps, use `build.location`, upgrade the software plan | Strong | https://docs.liara.ir/paas/details/plans/software-plans/ , release states in 03 |
| X-SANCTION | build log: `403`, `Forbidden`, download timeouts from foreign registries | Registry blocked from Iran | `build.location: "germany"`, DNS settings | Moderate | https://docs.liara.ir/paas/liarajson/ |
| X-CONFIG-FIELDS | `liara.json` contains `platform` / `app` and the deploy failed | Conflicting fields | Remove them | Weak | https://docs.liara.ir/paas/nodejs/how-tos/deploy-app/ |
| X-UPLOAD | HTTP 413 on POST, `client intended to send too large body` in nginx log | nginx body limit | `liara_nginx.conf` `client_max_body_size` | Strong | https://docs.liara.ir/paas/django/fix-common-errors/upload-limit-size/ |

### 3.2 Node.js / Next.js

| ID | Signature | Cause | Fix | Class | Source |
|---|---|---|---|---|---|
| N-ADDRINUSE | `Error: listen EADDRINUSE` | Two servers in the process bind the same port (e.g. a second `listen()`, a cluster misconfig, a dev server running next to the app server) | One `listen()` on the configured port | Definitive | https://nodejs.org/api/errors.html#common-system-errors |
| N-MODULE | `Cannot find module`, `code: 'MODULE_NOT_FOUND'`, `ERR_MODULE_NOT_FOUND` | Dependency missing from `package.json` (in `devDependencies` only), wrong path or case (Linux is case-sensitive), build output missing (`dist/` not built) | Move the package to `dependencies`, fix the import case, make sure the `build` script runs | Definitive | https://nodejs.org/api/errors.html#module_not_found , https://render.com/docs/troubleshooting-deploys |
| N-UNHANDLED | `UnhandledPromiseRejection`, `unhandledRejection`, `[UnhandledPromiseRejection: This error originated either by throwing inside of an async function` | Since Node 15 the default `--unhandled-rejections=throw` turns an unhandled rejection into an uncaught exception, so the process exits and the container restarts | `await`/`catch` the promise; add a global handler that logs | Strong | https://nodejs.org/api/cli.html#--unhandled-rejectionsmode |
| N-HEAP | `JavaScript heap out of memory`, `Reached heap limit`, `FATAL ERROR: .* Allocation failed` | V8 old-space limit reached (V8 GCs harder as it approaches the limit). Render notes the error can mean `--max-old-space-size` is set too high for the instance's RAM. | Set `NODE_OPTIONS=--max-old-space-size=<≈75% of plan RAM in MiB>` (the Node docs give 1536 for a 2 GiB machine), fix the leak, or upgrade | Definitive | https://nodejs.org/api/cli.html#--max-old-space-sizesize-in-mib , https://render.com/docs/troubleshooting-deploys |
| N-HEAP-BUILD | N-HEAP during `next build` | Build memory | Next.js guide: `experimental.webpackMemoryOptimizations`, `next build --experimental-debug-memory-usage`, disable source maps (`productionBrowserSourceMaps:false`, `enablePrerenderSourceMaps:false`), skip type-check in build | Strong | https://nextjs.org/docs/app/guides/memory-usage |
| N-ECONNRESET | `ECONNRESET`, `socket hang up` (Next.js on Liara) | Liara: mostly insufficient resources | Upgrade the plan, then restart | Strong on Next.js | https://docs.liara.ir/paas/nextjs/fix-common-errors/econnreset/ , https://nodejs.org/api/errors.html#common-system-errors |
| N-NEXTCFG | `Could not modify config file` | Custom `next.config.js` | `output: 'standalone'` | Definitive | https://docs.liara.ir/paas/nextjs/fix-common-errors/modify-config-file/ |
| N-EMFILE | `EMFILE`, `too many open files` | File-descriptor leak (unclosed sockets or files) | Close handles; reuse HTTP agents and DB pools | Moderate | https://nodejs.org/api/errors.html#common-system-errors |
| N-NOSTART | build ok, then `Missing script: "start"` / `npm ERR! missing script: start` | No `start` script | Add `start` | Definitive | https://docs.liara.ir/paas/nextjs/how-tos/deploy-app/ |

### 3.3 Python / Django / Flask

| ID | Signature | Cause | Fix | Class | Source |
|---|---|---|---|---|---|
| PY-TRACE | `Traceback (most recent call last):` followed by `<ExceptionName>: ...` | Unhandled exception. **The last line is the cause**; classify it with the rows below | — | Container rule | https://docs.python.org/3/library/exceptions.html |
| PY-MODULE | `ModuleNotFoundError: No module named 'X'` (an `ImportError` subclass) | Package not in `requirements.txt`, wrong module path | Add it to `requirements.txt`; for Flask with X=`app` see P6 | Definitive | https://docs.python.org/3/library/exceptions.html , https://docs.liara.ir/paas/flask/fix-common-errors/module-not-found/ |
| PY-WORKER-TIMEOUT | `[CRITICAL] WORKER TIMEOUT (pid:` | A request ran past the gunicorn timeout (Liara default 30 s); the worker is killed and the request returns 502/504 | Find the slow endpoint (DB/API); raise `GUNICORN_TIMEOUT` only as a stop-gap; move long jobs to background workers | Definitive | https://docs.liara.ir/paas/django/fix-common-errors/worker-timeout/ , https://github.com/benoitc/gunicorn/blob/19.4.5/docs/source/settings.rst |
| PY-WORKER-OOM | `Worker (pid:\d+) was sent SIGKILL! Perhaps out of memory?` | Worker killed for memory | Fewer `GUNICORN_WORKERS` (each worker is a full process), `max_requests`, or upgrade | Strong | https://docs.liara.ir/paas/django/how-tos/set-gunicorn-workers/ (the log string comes from gunicorn's arbiter, see open questions) |
| PY-MEMERR | `MemoryError` | The allocation failed inside Python | As above | Strong | https://docs.python.org/3/library/exceptions.html |
| DJ-HOST | `Invalid HTTP_HOST header`, `DisallowedHost`, all probes return 400 | Domain missing from `ALLOWED_HOSTS` with `DEBUG=False` | Add the domain (Liara's subdomain and any custom domain) | Definitive | https://docs.djangoproject.com/en/5.2/ref/settings/#allowed-hosts , https://docs.djangoproject.com/en/5.2/ref/exceptions/ |
| DJ-DEBUG | Probe response body contains a Django debug page (`You're seeing this error because you have DEBUG = True`) | `DEBUG=True` in production: a security leak, and Django "will remember every SQL query", which grows memory | `DEBUG=False` | Strong (security finding plus memory growth) | https://docs.djangoproject.com/en/5.2/ref/settings/#debug |
| DJ-CSRF | `CSRF verification failed`, `Origin checking failed` | Origin is not trusted behind a proxy or custom domain | `CSRF_TRUSTED_ORIGINS = ["https://domain"]`; `SECURE_PROXY_SSL_HEADER` only if the proxy sets and strips `X-Forwarded-Proto` | Strong | https://docs.djangoproject.com/en/5.2/ref/settings/#csrf-trusted-origins , https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header |
| DJ-STATIC | 404 on `/static/*`, `collectstatic` errors in the build log | Wrong `STATIC_ROOT`, or `collectStatic:false` | Fix `STATIC_ROOT`, let Liara run collectstatic | Moderate | https://docs.liara.ir/paas/django/how-tos/deploy-app/ |
| DJ-MIGRATE | `relation "..." does not exist`, `no such table`, `OperationalError` after a release | Migrations not run | Run `python manage.py migrate` (release hook or console shell) | Strong when correlated with a release | https://docs.liara.ir/paas/details/console-shell/ (linked from https://docs.liara.ir/paas/details/about/) |

### 3.4 PHP / Laravel

| ID | Signature | Cause | Fix | Class | Source |
|---|---|---|---|---|---|
| LV-KEY | `No application encryption key has been specified.` (`MissingAppKeyException`) | `APP_KEY` env var is missing | `php artisan key:generate --show`, set `APP_KEY`. Changing the key later logs out every session; use `APP_PREVIOUS_KEYS` when rotating | Definitive | https://github.com/laravel/framework/blob/12.x/src/Illuminate/Encryption/MissingAppKeyException.php , https://laravel.com/docs/12.x/encryption |
| LV-STORAGE | `The stream or file ".*storage/logs/laravel.log" could not be opened in append mode` / `failed to open stream: Permission denied` | `storage` and `bootstrap/cache` must be writable; on Liara the FS is read-only | Log to `stderr` (`LOG_CHANNEL=stderr`), attach a disk for `storage/app`, keep caches in `tmp/` | Strong | https://raw.githubusercontent.com/Seldaek/monolog/main/src/Monolog/Handler/StreamHandler.php , https://laravel.com/docs/12.x/deployment#directory-permissions , https://docs.liara.ir/paas/details/file-system/ |
| LV-DEBUG | Probe body shows a Laravel/Ignition error page | `APP_DEBUG=true` in production exposes sensitive config | `APP_DEBUG=false` | Strong (security) | https://laravel.com/docs/12.x/deployment#debug-mode |
| LV-ENVNULL | Config values are `null` after deploy with `configCache:true`; `env()` used outside config files | Once config is cached, `.env` is not loaded and `env()` returns null | Use `env()` only in `config/*.php` | Moderate | https://laravel.com/docs/12.x/deployment#optimizing-configuration-loading , https://docs.liara.ir/paas/laravel/how-tos/deploy-app/ |
| LV-ROUTECACHE | `Unable to prepare route ... for serialization. Uses Closure.` | `routeCache:true` with closure routes | Turn off `routeCache` or convert to controllers | Strong | https://docs.liara.ir/paas/laravel/how-tos/deploy-app/ (the exact string is Laravel's, see open questions) |
| LV-419 | HTTP 419 / `Page Expired` | Session/CSRF | `SESSION_DRIVER=cookie` (Liara fix) | Strong | https://docs.liara.ir/paas/laravel/fix-common-errors/419-page-expired/ |
| PHP-FATAL | `PHP Fatal error:` | Uncaught error; classify the rest of the line | — | Container rule | https://www.php.net/manual/en/ini.core.php |
| PHP-MEM | `Allowed memory size of \d+ bytes exhausted (tried to allocate \d+ bytes)` | PHP `memory_limit` (default `128M`) hit by one request | Fix the query/loop, or raise `memory_limit` | Definitive | https://raw.githubusercontent.com/php/php-src/master/Zend/zend_alloc.c , https://www.php.net/manual/en/ini.core.php#ini.memory-limit |
| PHP-COMPOSER | Build: composer resolution errors | Stale `composer.lock` or mirror | Liara: delete `composer.lock`; `composerMirror:false` | Moderate | https://docs.liara.ir/paas/laravel/how-tos/deploy-app/ |

### 3.5 Static / SPA (React, Vue, Angular, static)

| ID | Signature | Cause | Fix | Class | Source |
|---|---|---|---|---|---|
| ST-SPA404 | `/` returns 200 but deep links (`/about`) return 404 | SPA routing has no fallback to `index.html` | Configure the SPA fallback for the platform | Moderate | General SPA behaviour; the Liara static/react docs were not fetched (see open questions) |
| ST-CORS | Browser console CORS error, backend logs show no matching request | Missing CORS headers on the API | Liara has a CORS page per platform | Moderate | https://docs.liara.ir/paas/nodejs/fix-common-errors/cors-error/about/ |

---

## 4. Slowness diagnosis

Slowness has no single log line. The engine combines latency probes with saturation signals.

| ID | Evidence | Interpretation | Fix | Source |
|---|---|---|---|---|
| S-CPU | CPU ≥ **85% of plan cores** sustained ≥ **5 min** (design choice), together with probe p95 latency above baseline | A K8s CPU limit "is a hard limit the kernel enforces" through **throttling**: the app slows down but is not killed. Brendan Gregg (USE method): problems can begin above ~70% utilisation, and 5-minute averages hide 100% bursts, so treat 85% average as "already throttling". | Profile the hot path, add caching, upgrade CPU | https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/ , https://www.brendangregg.com/usemethod.html |
| S-CPU-THROTTLE | If `cpu.stat` is available: `nr_throttled/nr_periods` > 0.2 (design choice) | Direct throttling evidence; the CFS period defaults to 100 ms | As above | https://docs.kernel.org/scheduler/sched-bwc.html |
| S-MEM | Memory ≥ **90%** of plan RAM sustained (design choice) | GC pressure (V8 "will spend more time on garbage collection" near the limit) and imminent OOM | Leak fix, heap cap, upgrade | https://nodejs.org/api/cli.html#--max-old-space-sizesize-in-mib |
| S-SWAP | Not observable on Liara (no swap metric) | On Heroku, going over quota makes the dyno swap and degrade (R14) before it is killed at about 2x (R15). Useful analogy only. | — | https://devcenter.heroku.com/articles/error-codes |
| S-DB | App logs show slow queries; DB slow log enabled (Postgres `log_min_duration_statement`, default `-1` = off; MySQL `long_query_time` default 10 s); CPU of the app is **low** while latency is high | DB-bound: the app waits on the DB, so the app's CPU stays idle | Add indexes, fix N+1 queries, pool connections; set `log_min_duration_statement=250ms` to find them | https://www.postgresql.org/docs/current/runtime-config-logging.html , https://dev.mysql.com/doc/refman/8.4/en/slow-query-log.html |
| S-WORKERS | Python: latency high, CPU moderate, `WORKER TIMEOUT` occasionally; workers = 3 | All sync workers busy (queueing). The gunicorn docs suggest `2-4 x $(NUM_CORES)` workers, bounded by RAM per worker. | Tune `GUNICORN_WORKERS`; use async/ASGI for I/O-bound apps | https://github.com/benoitc/gunicorn/blob/19.4.5/docs/source/settings.rst , https://docs.liara.ir/paas/django/how-tos/set-gunicorn-workers/ |
| S-EVENTLOOP | Node: health check fails while CPU is pinned at 100% of **one** core | Blocked event loop / accept loop | Offload CPU work to worker threads | https://docs.fly.io/getting-started/troubleshooting |
| S-COLD | The first request after a deploy or restart is slow, later ones are fast | Warm-up (JIT, caches, Next.js preloads page modules at start, which costs memory up front) | Warm-up request in the health check, keep caches warm | https://nextjs.org/docs/app/guides/memory-usage . Whether Liara ever scales idle apps to zero is **unknown** (open question). |
| S-NOCACHE | High latency on static assets, no `Cache-Control`/gzip | Missing caching or compression | Django on Liara: enable gzip, customise nginx; Laravel: `php artisan optimize` (config/route/view cache) | https://docs.liara.ir/paas/django/fix-common-errors/about/ (sidebar: enable-gzip, customize-nginx), https://laravel.com/docs/12.x/deployment#optimization |
| S-DEBUG | `DEBUG=True` (Django) | Stores every SQL query in memory | `DEBUG=False` | https://docs.djangoproject.com/en/5.2/ref/settings/#debug |

**Latency measurement.** Use p95/p99, not averages. "The 99th percentile of one backend can easily become the median response of your frontend", and p99 over 1-minute windows is an early saturation signal. Measure failed and successful requests separately ("a slow error is even worse than a fast error"). Source: https://sre.google/sre-book/monitoring-distributed-systems/

---

## 5. Verifying a fix

A fix counts as verified only when **all** of these checks pass (the windows are design choices):

1. **Re-probe.** At least 5 HTTP probes over at least 2 minutes to `/` and to the failing path; all return the expected status (2xx/3xx), and p95 latency is ≤ 1.2× the pre-incident baseline. Laravel apps can expose `/up`, which returns 200 if the app booted without exceptions and 500 otherwise (https://laravel.com/docs/12.x/deployment#the-health-route). Render recommends a simple health check, such as a basic DB query, so the check itself does not time out (https://render.com/docs/troubleshooting-deploys).
2. **Release state.** The new release is `READY`, not `UNHEALTHY`/`FAILED`/`TIMEDOUT` (states from 03 §3); with zero-downtime deploy, traffic has moved to it (https://docs.liara.ir/paas/details/zero-downtime-deployment/).
3. **Restart count stable.** No new "turned off", "high RAM" or unexpected SIGKILL events for **≥ 10 minutes**. That window matches the K8s rule that the crash-loop back-off resets after 10 min of healthy running (https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/). Liara also auto-restarts on health-check failure (https://docs.liara.ir/paas/details/health-check/), so an unchanged restart count also confirms that health checks are passing.
4. **Error rate.** 5xx lines in access logs, and matching signature hits, drop to ≤ 1% of requests (or 0 signature hits) over a 15-min window. The SRE workbook pairs a long window with a short window of 1/12 of its length so an alert "stops firing soon after the issue is resolved". Use a 5-min short window to confirm recovery quickly (https://sre.google/workbook/alerting-on-slos/).
5. **Resources.** Memory stays below 80% of plan RAM and is **not** monotonically rising over 30 min. CPU p95 stays below 85% (design choice; see §4 sources).
6. **Signature gone.** The original triggering regex has no hits in `liara logs --since` after the fix (https://docs.liara.ir/references/cli/see-app-logs/).

If 1–4 pass but 5 fails, report "mitigated, at risk" (for example, a plan upgrade masked a leak).

---

## 6. Ranked-cause scoring scheme

### 6.1 Evidence classes and weights (log-odds style, additive; all values are design choices)

| Class | Weight | Examples |
|---|---|---|
| Definitive signature | +60 | `EADDRINUSE`, `No application encryption key`, Liara high-RAM event, `OOMKilled`, `WORKER TIMEOUT`, port mismatch proven from config plus logs |
| Strong | +30 | Crash loop count, `ECONNREFUSED` to the DB, memory ≥ 95% then kill, release `UNHEALTHY` with a health-check port mismatch |
| Moderate | +15 | Mirror-type build error, CPU ≥ 85% sustained, memory rising |
| Weak / contextual | +5 | Plan is Earth/Mars, the framework commonly has this issue, `liara.json` has `platform` field |
| Temporal correlation | +20 | Onset ≤ 30 min after a release or env change **and** the signature first appears in the new release's logs (`liara logs -r`) |
| Probe pattern match | +10 to +25 | All paths 502 suggests port/crash (+25); only some paths 500 suggests code bug (+15); 504 only on one endpoint suggests a slow query (+15); 400 on every path on Django suggests ALLOWED_HOSTS (+25) |
| Contradicting evidence | −30 | "Port mismatch" while the probe returns 200; "OOM" while memory peaked < 60%; "DB down" while other DB queries succeed in the same window |
| Missing expected evidence | −10 | Cause expects a log line, but logs are available and show none |

### 6.2 Algorithm

```
for each rule R:
    score[R] = prior[R]                       # 0..10, from platform base rates (design choice)
    for each evidence item e matched by R:
        score[R] += weight(e.class) * decay(e.age)   # decay = 1 if e within incident window, 0.5 if older (design choice)
    score[R] += temporal_bonus(R) + probe_bonus(R) - contradictions(R)

collapse container rules: PY-TRACE / PHP-FATAL / X-CRASHLOOP adopt the score of their best child cause
        plus +10, never ranked on their own when a child matched.

confidence[R] = 1 / (1 + exp(-(score[R] - 40) / 12))       # logistic: 40 ~ 50 %, 60 ~ 84 %, 80 ~ 97 %
rank by score; report top 3 with confidence >= 0.3; if none, report "insufficient evidence"
    + list of missing evidence to collect (e.g. enable slow query log, add health check).
```

**Causal chain ordering.** When a resource cause and a symptom both match, rank the resource cause first and link the symptom to it. Examples: `N-HEAP` → `X-CRASHLOOP` → 502; `S-DB` → `PY-WORKER-TIMEOUT` → 504; `N-ECONNRESET` + `S-MEM` on Next.js → under-provisioned (P9).

**Priors (design choice, platform-adjusted):** port/bind 10 for brand-new apps (no successful release yet; Render lists "never had a successful deploy" as a 502 cause, https://render.com/docs/troubleshooting-deploys), 3 otherwise; OOM 8 on Earth (512 MB) and Mars, 3 on larger plans; missing env 8 within 30 min of an env change.

### 6.3 Output contract for the LLM explainer

The engine emits `{rule_id, score, confidence, matched_evidence[{source, excerpt, timestamp}], fix_steps[], verify_steps[], source_urls[]}`. The LLM only rephrases these fields in Persian or English, and must cite `source_urls`.

---

## 7. General PaaS analogues used as supporting evidence

| # | Analogue | Source |
|---|---|---|
| G1 | Fly.io: "The app is not listening on the expected address and will not be reachable by fly-proxy". Listen on `0.0.0.0`, not `localhost`/`127.0.0.1`. | https://docs.fly.io/getting-started/troubleshooting |
| G2 | Render: bind to `0.0.0.0` and `$PORT`; `Port scan timeout reached`; `Module Not Found` usually means the dependency is not listed or the path or casing is wrong. | https://render.com/docs/troubleshooting-deploys |
| G3 | Heroku: H10 app crashed (503), H12 request timeout at 30 s, H13 connection closed without response, H14 no web processes, H20 boot timeout at 75 s, R10 failed to bind `$PORT` within 60 s, R14 memory quota exceeded (swap), R15 memory quota vastly exceeded (SIGKILL). | https://devcenter.heroku.com/articles/error-codes |

---

## Unverified / open questions

1. **Liara proxy timeout.** No Liara doc gives the reverse-proxy read timeout that turns slow requests into 504. Only gunicorn's 30 s default is documented (P1). Measure it with a `/sleep?s=N` probe endpoint.
2. **Exact Liara error page bodies.** It is not documented whether Liara's proxy returns its own branded 502/503/504 page, or what text it contains. A body fingerprint would let the engine tell proxy errors from app errors. Capture one empirically.
3. **Health-check units.** The docs say ms, but their example values (30, 15, 5) read like seconds. The CLI prompts also say ms (see 03 §3). Needs a test.
4. **Whether Liara injects `PORT`.** No fetched doc says that Liara sets a `PORT` env var; the docs only describe `liara.json` `port`. The engine should compare the port the app logs against `liara.json`, not assume `$PORT`.
5. **Default port when `port` is omitted.** `liara.json` docs say a default is assigned without giving its value. The Python doc mentions 3000. Unconfirmed per platform.
6. **Does Liara's Django settings injection set `ALLOWED_HOSTS`?** Liara "appends its own configuration" to `settings.py` (P3), but the fetched pages do not list what it adds. If it adds `ALLOWED_HOSTS = ['*']`, DJ-HOST applies only with `modifySettings:false`.
7. **Exact machine strings** of Liara events (high-RAM event, turned off) and applet `state`/`reason` values are undocumented (see 03 §3). The rules match on the human text until real samples are captured.
8. **gunicorn log strings** (`[CRITICAL] WORKER TIMEOUT (pid:N)`, `Worker (pid:N) was sent SIGKILL! Perhaps out of memory?`) come from gunicorn's source and common usage; the current gunicorn docs site was unreachable during research (redirect then 404), so the settings were cited from the 19.4.5 docs snapshot on GitHub. Verify the strings against current gunicorn source.
9. **Laravel route-cache closure message** and the exact Node heap OOM line (`FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory`) are well known but were not quoted from a fetched primary source here.
10. **Cold starts / idle sleep.** No Liara doc found on scaling idle apps to zero. Liara appears to run apps continuously (scale 0/1 only, see 03), so S-COLD likely applies only after deploys or restarts.
11. **CPU throttling observability.** Liara exposes CPU usage but not `cpu.stat` throttling counters. S-CPU-THROTTLE works only if a future API exposes them. Until then, S-CPU uses % of plan cores.
12. **Does an env-var change restart the app?** The env docs do not say. This matters for the X-ENV temporal correlation.
13. **Static/SPA fallback behaviour** on Liara's static/React platforms was not researched in this pass.
14. **All thresholds** (85% CPU, 90/95% memory, 5/10/15/30-minute windows, weights, logistic midpoint) are design choices informed by the USE method and SRE sources. They are not Liara-specified and should be calibrated against real incidents.
