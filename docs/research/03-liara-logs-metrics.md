# 03 - Liara observability data available by API (logs, metrics, status, events)

Research date: 2026-10-22. No Liara endpoint was called and no token was used. Everything below comes from public source code and docs.

## Sources and pinned revisions

| Short name | Repo / URL | Revision |
|---|---|---|
| `cli` | https://github.com/liara-cloud/cli (official CLI, `@liara/cli` 9.6.0, `package.json:4`) | `14ec35f79d703a09a5e3abbb22ba59239cdde80d` |
| `openapi` | https://github.com/liara-cloud/openapi (official OpenAPI specs behind https://openapi.liara.ir) | `338325a42cd28d12dcee10c088840d2098504a8b` |
| `docs` | https://github.com/liara-cloud/docs (source of https://docs.liara.ir) | `13ab045fa77384ef5dce46d8ff94d10cc828b3d8` |
| `liara-mcp` | https://github.com/razavioo/liara-mcp (**unofficial**, third party) | `4a710ec7b7bdc11f01c043b220fce2027493020b` |

Citations use `repo@sha7:path:line`, for example `cli@14ec35f:src/commands/app/logs.ts:227`.

## 0. Common API facts

- **Base URL.** The CLI sends PaaS calls to `https://api.liara.ir` for both regions (`cli@14ec35f:src/constants.ts:10-13`, `src/base.ts:328-329`). The OpenAPI spec also lists `https://api.liara.ir` as its server (`openapi@338325a:spec/paas.yaml:28-29`). Generated community SDKs use `https://api.iran.liara.ir` (for example `jarqvi/node-sdk:doc/paas/ReportsApi.md`, found with GitHub code search). The CLI also uses `https://api.iran.liara.ir` for the websocket shell (`cli@14ec35f:src/constants.ts:15`, `src/commands/app/shell.ts:63-69`).
- **Auth.** Every request sends `Authorization: Bearer <api-token>` (`cli@14ec35f:src/base.ts:323-324`).
- **Teams.** A `teamID` query parameter is added to every request (it is empty for the personal account) (`cli@14ec35f:src/base.ts:284-293`).
- **Timeouts.** The CLI's default request timeout is 10 s, or 25 s for image deploys (`cli@14ec35f:src/base.ts:281-283`). The logs call overrides this to 20 s (`src/commands/app/logs.ts:238-242`).
- **App identifier.** The `{name}` path segment is the app's `project_id` (its slug), lower-cased by the CLI (`cli@14ec35f:src/commands/app/logs.ts:71-75`, `:126-133`).

## 1. Logs (runtime logs)

### 1.1 Endpoint the current CLI uses: `GET /v2/projects/{app}/logs` (HTTP polling, no websocket)

- **URL.** `v2/projects/${appName}/logs` (`cli@14ec35f:src/commands/app/logs.ts:227`).
- **Query parameters** (`cli@14ec35f:src/commands/app/logs.ts:228-236`):
  - `start`: Unix time in **seconds**. The default is `now - maxLogsRetention*86400` (`:115`, `:148-154`). `--since "1 hour ago"` is parsed client-side with chrono-node into Unix seconds (`:429-433`).
  - `direction`: always `forward` in the CLI (`:230`).
  - `last_lines`: boolean. Added in Nov 2025 with commit `5aa18c97a8` "Add last lines log option" (seen with `gh api repos/liara-cloud/cli/commits/5aa18c97a8`). When it is true the CLI makes one request and stops (`:200-202`). The server-side line count is not documented.
  - `releaseId` (optional): the Mongo `_id` of a release. The CLI resolves it from a tag such as `v3` through `GET v1/projects/{app}/releases?page=1&count=100` (`:165-180`, `:304-317`, `:336-356`).
  - There is **no `end`/`until` and no `limit`** parameter in the official CLI. The only bounds are `start`, `direction` and `last_lines`.
- **Follow mode is client-side polling.** The CLI loops: fetch, print, sleep 1000 ms, fetch again from `lastLogTimestampSeconds + 1` (`cli@14ec35f:src/commands/app/logs.ts:182-215`). Without `-f` it stops on the first empty page (`:192-194`). The CLI does **not** use a websocket for logs. The only websocket in the CLI is the interactive shell `wss://api.iran.liara.ir/v1/exec?token=...&cmd=...&project_id=...&teamID=...` (`cli@14ec35f:src/commands/app/shell.ts:63-70`; also documented at `openapi@338325a:spec/paas.yaml:7-20`).
- **Response shape** (`cli@14ec35f:src/commands/app/logs.ts:15-24`, `:245-283`, `:387-406`):

  ```jsonc
  {
    "data": [                         // several "streams"; each is sorted, but not sorted against the others
      {
        "metaData": { "releaseId": "<release _id>" },
        "values": [
          ["<timestamp string, first 10 digits = unix seconds>", "<JSON string>"]
        ]
      }
    ]
  }
  // the inner JSON string decodes to { "_entry": "<log line>", "type": "stdout" | "stderr", ... }
  ```

  The client must flatten every `values` array and sort the result by timestamp. The CLI compares timestamps as `BigInt` (`:276-281`), which means the strings are longer than JavaScript's safe-integer range, probably nanoseconds. The line text is `JSON.parse(v[1])._entry`, and `type === 'stderr'` sends the line to stderr (`:388`, `:403-405`). The `--timestamps` flag formats `v[0].substring(0,10)` as seconds (`:393-401`).
  *Inference:* the `{metaData, values:[[ts, line]]}` shape and the nanosecond string timestamps match Grafana Loki's stream format. Liara does not document this.
- **Errors.** 404 means the app was not found (`:285-289`). Any other error gives a generic message (`:291-300`).
- **Old infrastructure.** If `project.network` is missing, the CLI refuses and asks the user to install `@liara/cli@8.1.0` (`:135-144`).
- **History.** By 2024-06 (`05ffa2d608`) the CLI already called `v2/projects/${project}/logs?start=${since}` (seen with `gh api .../contents/src/commands/app/logs.ts?ref=05ffa2d608`, lines 87-88).

### 1.2 Documented v1 endpoint: `GET /v1/projects/{name}/logs`

- The OpenAPI spec documents `GET /v1/projects/{name}/logs` with a required `since` (string) query parameter (`openapi@338325a:spec/paas.yaml:957-992`).
- Its `Logs` schema is an array of `{type, datetime, message}` (`openapi@338325a:spec/paas.yaml:1723-1733`). That does **not** match the v2 shape the CLI parses.
- The unofficial MCP calls this v1 path with `limit`/`since`/`until` (`liara-mcp@4a710ec:src/services/observability.ts:31-57`). Nothing official confirms that those parameters exist.
- **Recommendation:** build on the v2 endpoint the official CLI uses.

### 1.3 Build logs (deployment-time)

- `GET /v2/releases/{releaseID}/build-logs?since=<createdAt of last line>` returns `{ release: {state, status, failReason?, queue?}, buildOutput: [{_id, line, stream: "STDOUT"|..., releaseID, createdAt}] }` (`cli@14ec35f:src/services/build-logs.ts:25-27`, `src/types/build-logs-response.ts:4-7`, `src/types/build-output.ts:1-7`, `src/types/release.ts:1-6`).
- The CLI polls it every 1 s (`cli@14ec35f:src/utils/poller.ts:9-16`).
- Any stream other than `STDOUT` is treated as a build failure (`src/services/build-logs.ts:29-46`).

### 1.4 Log retention

- **Runtime value (authoritative).** The CLI reads `GET /v1/me` → `plans.projectBundlePlans[planID][bundlePlanID].maxLogsRetention`, in **days** (`cli@14ec35f:src/commands/app/logs.ts:146-150`). A `--since` value older than that is rejected before any request is sent (`:156-163`).
- **CLI error strings.** "Free plan: past 1 hour", "Standard: past 30 days" (`cli@14ec35f:src/errors/bundle-plan.ts:50-58`). The legacy-infra text says 7 days (`:73-75`).
- **Docs.** The feature-bundle table says log retention is Bronze 7 days, Silver 30 days, Gold 60 days. Resource charts follow the same tiers (`docs@13ab045:src/pages/paas/details/plans/software-plans.mdx:67-73`; https://docs.liara.ir/paas/details/plans/software-plans/). This differs from the CLI's "1 hour" for free, so read `maxLogsRetention` at runtime.
- The console log viewer has search, a time-range picker and a "live" mode (`docs@13ab045:src/pages/paas/details/observations/software.mdx:31-38`; https://docs.liara.ir/paas/details/observations/software/). Whether the API also supports server-side search for logs is undocumented (the events endpoint has `search`, see section 4).

## 2. Metrics (CPU, memory, network, disk)

The official CLI exposes **no** metrics command. A grep of `cli@14ec35f:src` for `metric` finds nothing in the PaaS commands. The endpoints are documented in the official OpenAPI spec under the tag "Reports" (`openapi@338325a:spec/paas.yaml:44-45`). The console "Reports" page (CPU, memory, inbound and outbound traffic, live updates, up to 60 days back) uses the same data (`docs@13ab045:src/pages/paas/details/observations/hardware.mdx:31-36`; https://docs.liara.ir/paas/details/observations/hardware/). That the console calls exactly these endpoints is an inference; the console's source is not public.

| Endpoint | Params | Response | Spec |
|---|---|---|---|
| `GET /v1/projects/{name}/metrics/cpu` | `since` (number, required) | `Reports` | `openapi@338325a:spec/paas.yaml:1203-1238` |
| `GET /v1/projects/{name}/metrics/memory` | `since` (number, required) | `Reports` | `:1239-1274` |
| `GET /v1/projects/{name}/metrics/network-receive` | `since` (number, required) | `Reports` | `:1275-1310` |
| `GET /v1/projects/{name}/metrics/network-transmit` | `since` (number, required) | `Reports` | `:1311-1346` |
| `GET /v1/projects/{name}/metrics/summary` | none | see below | `:1133-1202` |

- **`Reports` schema** (`openapi@338325a:spec/paas.yaml:1968-1987`):

  ```jsonc
  { "end": <number>,
    "result": [ { "applet": "<instance/pod name>", "values": [ [<number|string>, <number|string>], ... ] } ] }
  ```

- **`metrics/summary`** (`openapi@338325a:spec/paas.yaml:1153-1193`):

  ```jsonc
  { "cpuUsage":    [ { "applet": "...", "value": [<number|string>, ...] } ],
    "memoryUsage": [ { "applet": "...", "value": [<number|string>, ...] } ],
    "disksUsage":  [ { "name": "...", "size": "<string>", "usage": "<string>", "reportedAt": "<string>" } ] }
  ```

- *Inference:* `values: [[ts, "v"], ...]` looks like a Prometheus range-query matrix, and `value: [ts, "v"]` like an instant vector. There is one series per `applet` (instance), so an app with scale > 1 gets several series. **Units are not documented** for CPU (cores or %?), memory (bytes?) or network (bytes/s?). The **step/resolution** and the units of `since` (Unix seconds?) are also undocumented.
- **Time range.** Only `since` is documented, with no `until`/`step`. The response carries `end`. The console allows up to 60 days back depending on the bundle (`docs@13ab045:.../software-plans.mdx:71`, `.../observations/hardware.mdx:36`).
- **Disk usage** comes only through `summary.disksUsage` (per-disk `size`/`usage`/`reportedAt`). Disk metadata is at `GET /v1/projects/{id}/disks` (`openapi@338325a:spec/paas.yaml:629-649`, schema `Get-disks` at `:1927-1951`).
- **Plan limits are NOT included in metrics responses** (see the schemas above). Join them yourself:
  1. `GET /v1/projects/{name}` → `project.planID`, `bundlePlanID`, `scale` (`cli@14ec35f:src/base.ts:124-153`; `openapi@338325a:spec/paas.yaml:1621-1690`).
  2. `GET /v1/me` → `plans.projects[planID].CPU.amount` (cores), `.RAM.amount` (GB), `.volume` (GB disk) (`cli@14ec35f:src/commands/plan/list.ts:21`, `:41-44`, `:62-65`; field overview at `docs@13ab045:src/pages/references/api/get-info.mdx:84`, `:460-467`).
- **Same pattern for databases.** `GET /v1/databases/{id}/metrics/{cpu|memory|network-receive|network-transmit|summary}` (`openapi@338325a:spec/dbaas.yaml:434-645`).
- **The unofficial MCP** calls only `metrics/summary` and passes a `period` parameter (`liara-mcp@4a710ec:src/services/observability.ts:11-23`). Its TypeScript response type `{period, metrics:{cpu,memory,disk,network,requests}}` (`src/api/types.ts:334-348`) does not match the official schema and looks invented, so do not rely on it.

## 3. App status and health

- **App-level status.** `GET /v1/projects` and `GET /v1/projects/{name}` return `status` (string), `scale` (number, 0 = off, 1 = on) and `isDeployed` (`cli@14ec35f:src/base.ts:77-91`, `:124-149`; `openapi@338325a:spec/paas.yaml:1636-1650`, `:1685-1687`). The CLI just prints `project.status` (`cli@14ec35f:src/commands/app/list.ts:35-36`). **The spec has no enum** for `status`: a grep of `spec/paas.yaml` for `enum` finds nothing. The unofficial MCP guesses `'RUNNING'|'STOPPED'|'DEPLOYING'|'FAILED'|'CREATING'` (`liara-mcp@4a710ec:src/api/types.ts:82`), but that is unverified. For comparison, the CLI maps database `status === 'RUNNING'` to OK (`cli@14ec35f:src/commands/db/list.ts:35`).
- **Instance (pod) level: "applets".** `GET /v1/projects/{name}/applets` returns `{ applets: [{ id, name, timestamp, state, reason, release: { releaseID, tag } }] }` (`openapi@338325a:spec/paas.yaml:1059-1088`, `:1809-1841`). This is the closest thing to per-instance status (crashed or restarting) plus a `reason`. The values of `state` and `reason` are not documented. Whether `reason` carries `OOMKilled`/`CrashLoopBackOff`-style strings is unverified.
- **Restart counts.** No `restartCount` field appears in any documented schema (ProjectAllDetails, Applets and Releases at `openapi@338325a:spec/paas.yaml:1621-1925`). Derive it by counting restart and kill events (section 4).
- **OOM signal.** The docs list an event "app stopped due to high RAM consumption", meaning the app is shut down when it uses too much RAM (`docs@13ab045:src/pages/paas/details/events.mdx:56-57`; https://docs.liara.ir/paas/details/events/). That event is the user-visible OOM-kill signal. Its exact machine string is not documented. Compare it with memory metrics against `plans.projects[planID].RAM.amount`.
- **Release / deploy state machine.** Release `state` takes the values `BUILDING`, `PUSHING`, `PUSHED`, `DEPLOYING`, `READY`, `UNHEALTHY`, `FAILED` (with `failReason`), `CANCELED` and `TIMEDOUT`. They are read from `GET /v1/releases/{id}` and `GET /v2/releases/{id}/build-logs` (`cli@14ec35f:src/services/build-logs.ts:50-82`, `src/commands/deploy.ts:681-714`). `UNHEALTHY` means "app deployed, but the container is unhealthy" (`src/commands/deploy.ts:702-705`). `GET /v1/projects/{name}/releases?page&count` returns `currentRelease`, `readyReleasesCount` and `releases[].state` (`openapi@338325a:spec/paas.yaml:1089-1132`, `:1842-1926`).
- **Health-check config.** It lives in `liara.json` → `healthCheck: { command (string|string[]), interval, timeout, retries, startPeriod }` (`cli@14ec35f:src/types/health-config.ts:1-7`, `src/types/liara-json.ts:26`). It is sent in the deploy body (`src/commands/deploy.ts:430-435`), and `command` is required (`:748-759`). The `liara init` prompts label interval, timeout and startPeriod as **ms** (`src/commands/init.ts:553-571`). The docs also say ms, but their example uses `interval: 30, timeout: 15` (`docs@13ab045:src/pages/paas/details/health-check.mdx:39-46`, `:54`).
  - **Behaviour:** traffic does not move to a new release until its health check passes (`docs@13ab045:src/pages/paas/details/health-check.mdx:93`). If a running release later fails its health check, **Liara restarts the app automatically** (`docs@13ab045:src/pages/paas/details/health-check.mdx:94`; https://docs.liara.ir/paas/details/health-check/).
  - No API endpoint returns the current health-check pass/fail result. The visible results are release `UNHEALTHY` and events.
- **Control actions** (for remediation): `POST /v1/projects/{name}/actions/restart` and `POST /v1/projects/{name}/actions/scale {scale: 0|1}`. Both return 409 when "another operation is already running" (`cli@14ec35f:src/commands/app/restart.ts:27`, `:40`; `src/commands/app/start.ts:27-29`, `:42-44`; `openapi@338325a:spec/paas.yaml:146-206`).

## 4. Events / activity / notifications

- **App events.** `GET /v1/projects/{name}/events?search=&start=&end=`, where `start` and `end` are Unix-second numbers (example `1704028315`) (`openapi@338325a:spec/paas.yaml:993-1058`). The response is `{ data: [ { metaData: {}, values: [ [string, ...] ] } ] }`, the same stream-style shape as logs. The official CLI does not use it.
- **Documented event types.** SIGKILL (usually after a new deploy), SIGSTOP, "waiting to run", "running", "app turned off" (possibly after a crash) and "stopped due to high RAM". The events list is sorted by the most recent change. With zero-downtime deploys, the new version starts before the old one is killed (`docs@13ab045:src/pages/paas/details/events.mdx:28-57`).
- **Database events.** `GET /v1/databases/{name}/events` (`openapi@338325a:spec/dbaas.yaml:646-660`).
- **Account notifications.** These exist only in the console: a bell icon, plus per-user notification settings (`docs@13ab045:src/pages/references/console/see-notifs.mdx:23-30`, `set-notifs.mdx:23-32`). No public API or webhook for them was found in any `openapi@338325a:spec/*.yaml`. `billing.yaml:77` only mentions a "last minimum credit notification time" field.

## 5. HTTP-level metrics (requests, status codes, latency)

- **Not exposed.** No documented endpoint returns request counts, status-code rates or response times. The full PaaS path list (`openapi@338325a:spec/paas.yaml`, `grep "^  /"`) has only cpu, memory, network-receive, network-transmit and summary under `metrics`. The console Reports page lists only CPU, memory, inbound and outbound traffic (`docs@13ab045:src/pages/paas/details/observations/hardware.mdx:32`). (The `requests?` field in the unofficial MCP type is not backed by the spec: `liara-mcp@4a710ec:src/api/types.ts:342`.)
- **What we must do instead:**
  1. Run synthetic probes ourselves against the app URL: `https://<app>.liara.run`, or `.iran.liara.run` for old-infra Iran apps (`cli@14ec35f:src/commands/deploy.ts:235-242`), or custom domains, using https when `certificatesStatus === 'ACTIVE'` (`:254-259`).
  2. Parse access-log lines from the logs endpoint. Platform web servers (nginx/Apache) emit access logs whose method and status the CLI colour-codes by regex, e.g. `GET 5xx` (`cli@14ec35f:src/commands/app/logs.ts:436-472`). From those lines we can derive request counts, a 5xx rate and nginx `[error]` lines. Latency is not present unless the app logs it.

## 6. Limits

- **Rate limits.** Undocumented. The OpenAPI landing page only says "API requests are subject to rate limiting" and points to per-service docs (`openapi@338325a:index.mdx:65-67`). No PaaS doc gives numbers. The unofficial MCP retries on 429 with exponential backoff of 1 s, 2 s, 4 s (`liara-mcp@4a710ec:src/api/client.ts:59-79`), which suggests 429 is the throttling signal (unverified). The CLI polls logs at about 1 request/s plus up to 1 extra releases call per unknown releaseId (`cli@14ec35f:src/commands/app/logs.ts:210`, `:257-265`), so about 1 req/s/app is a reasonable ceiling.
- **Log and chart retention.** See 1.4: `maxLogsRetention` (days) per bundle; the docs say 7, 30 or 60 days, and the CLI text says 1 hour for free.
- **Other.** Deploys per day are 20, 50 or unlimited, and build time is 5, 10 or 20 min per bundle (`docs@13ab045:src/pages/paas/details/plans/software-plans.mdx:42-52`).

## Unverified / open questions

1. **Metric units and resolution.** CPU (cores vs %), memory (bytes vs MB) and network (bytes/s vs cumulative) are unknown, as are the `since` units (seconds assumed) and the step. Whether `until`/`end`/`step` query parameters are accepted is also unknown. Needs one authenticated call to settle.
2. **Rough edges in the v2 logs endpoint.** How many lines one page returns (max page size), how many lines `last_lines=true` returns, whether `end`/`limit`/`direction=backward` are supported, and the exact precision of the timestamp string (nanoseconds assumed from the BigInt use). The `/v2/.../logs` path is used by the CLI but **absent from the OpenAPI spec**, which documents only `/v1/.../logs` with a different shape.
3. **Status enums.** The values of `project.status`, `applets[].state` and `applets[].reason` are undocumented. Whether `reason` exposes `OOMKilled`, `Error` or `CrashLoopBackOff` is unknown.
4. **Event payloads.** The exact machine strings for the event types (SIGKILL, high-RAM stop, and so on) and what `metaData` contains.
5. **Log retention conflict.** The CLI says the free plan keeps 1 hour; the docs say Bronze keeps 7 days. Mapping `free` to "Bronze" is likely but unconfirmed. Use `maxLogsRetention` from `/v1/me`.
6. **Health-check units.** The docs and CLI say ms, but the docs' own example (`interval: 30`) reads like seconds.
7. **Base host.** Whether `api.liara.ir` and `api.iran.liara.ir` are interchangeable for every PaaS endpoint. The CLI uses `api.liara.ir` for REST and `api.iran.liara.ir` for the websocket.
8. **Rate-limit numbers** and whether 429 is the throttling status. No public source found.
9. **Console endpoints.** Whether the console's charts call exactly `/v1/projects/{name}/metrics/*` was not observed directly; the console is closed-source.
10. **Event and notification push.** No webhook or websocket for events or notifications is documented, so events must be polled.
