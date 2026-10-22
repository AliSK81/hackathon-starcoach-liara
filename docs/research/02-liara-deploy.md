# 02 - How a Liara deploy works through the API (without the Liara CLI)

Research date: 2026-10-22. No authenticated Liara endpoint was called and no token was used. Everything below comes from reading source code and docs.

## Sources and citation format

| Alias | Repository | Commit (full SHA) | Notes |
|---|---|---|---|
| `cli@14ec35f` | https://github.com/liara-cloud/cli | `14ec35f79d703a09a5e3abbb22ba59239cdde80d` | official CLI, `@liara/cli` v9.6.0 (`package.json:4`), commit dated 2026-10-18 |
| `openapi@338325a` | https://github.com/liara-cloud/openapi | `338325a42cd28d12dcee10c088840d2098504a8b` | official OpenAPI spec (PaaS = `spec/paas.yaml`) |
| `docs@13ab045` | https://github.com/liara-cloud/docs | `13ab045fa77384ef5dce46d8ff94d10cc828b3d8` | source of docs.liara.ir. A page at `src/pages/X.mdx` is served at `https://docs.liara.ir/X/` (checked for `paas/liarajson` and `paas/details/health-check`) |
| `liara-mcp@4a710ec` | https://github.com/razavioo/liara-mcp | `4a710ec7b7bdc11f01c043b220fce2027493020b` | **unofficial**, third-party MCP server. Used only as a hint for undocumented endpoints |

Citations look like `cli@14ec35f:src/commands/deploy.ts:481`, meaning repo@sha:file:line. All clones are in `C:\Users\alieb\AppData\Local\Temp\claude\research\`.

---

## 1. HTTP client basics (what every call needs)

- **Base URL:** `https://api.liara.ir` for both regions `iran` and `germany` (`cli@14ec35f:src/constants.ts:10-13`). The OpenAPI server is the same (`openapi@338325a:spec/paas.yaml:28-29`). The CLI sets `prefixUrl` from the region (`cli@14ec35f:src/base.ts:327-329`).
- **Auth header:** `Authorization: Bearer <api-token>` (`cli@14ec35f:src/base.ts:323-324`). The OpenAPI lists `jwt` / `bearerAuth` security (`openapi@338325a:spec/paas.yaml:30-32`).
- **Team scoping:** a `beforeRequest` hook adds `?teamID=<team-id>` to **every** request, or `teamID=` (empty) for the personal account (`cli@14ec35f:src/base.ts:284-293`).
- **Timeouts:** the default request timeout is 10 s, or 25 s for an image deploy (`cli@14ec35f:src/base.ts:281-283`). The upload removes the timeout (`timeout.request: undefined`) (`cli@14ec35f:src/services/upload.ts:9-12`).
- **401:** a global hook prints "Authentication failed" and exits (`cli@14ec35f:src/interceptors.ts:4-20`).
- A `User-Agent` header carries the CLI's user agent (`cli@14ec35f:src/base.ts:278-280`). It is not known whether the server needs it.

---

## 2. End-to-end deploy flow (from `liara deploy`)

Main source: `cli@14ec35f:src/commands/deploy.ts`.

### Step 0 - Local config merge and checks
- The CLI reads `liara.json` from the project path, or the file named by `--liara-json`, and lowercases `app` (`deploy.ts:822-844`, flag at `deploy.ts:100-104`). Flags override liara.json, which overrides defaults (`deploy.ts:795-820`). `--disks name:mountTo` becomes `[{name, mountTo}]`, and `--args` is split on spaces (`deploy.ts:804-811`).
- It refuses to deploy the home, Desktop or Downloads directory (`cli@14ec35f:src/utils/check-path.ts:4-43`) or an empty directory: "Directory is empty!" (`deploy.ts:736-740`).
- `healthCheck.command` is required and must be a string or an array. `build.cache` must be a boolean (`deploy.ts:747-765`).
- The build cache is on unless `--no-cache` is passed or `build.cache === false` (`deploy.ts:161`). The Dockerfile comes from `--dockerfile` or `build.dockerfile` (`deploy.ts:167`). The build location comes from `--build-location` or `build.location` (`deploy.ts:172-173`).
- Build args: `--build-arg K=V` (multiple) and `build.args: ["K=V"]` are parsed into a **map** `{K: V}`. CLI flags win (`deploy.ts:178-186`, parser at `cli@14ec35f:src/utils/build-args-parser.ts:5-13`, which splits on the first `=` only, so values that contain `=` get truncated).

### Step 1 - `GET v1/projects/{app}` (precondition)
- Called at `deploy.ts:190-192`. The response is `{project: {...}}` with fields `type, scale, bundlePlanID, network, defaultSubdomain, zeroDowntime, isDeployed, ...` (`cli@14ec35f:src/base.ts:124-153`; OpenAPI `openapi@338325a:spec/paas.yaml:93-119`).
- If `project.scale` is falsy, the CLI stops with "The {app} app isn't running. Please start the app first." (`deploy.ts:194-198`).
- **The platform is taken from `project.type`** (the platform chosen when the app was created) unless `--platform` or `liara.json.platform` is given. An image deploy forces `docker` (`deploy.ts:201-213`).
- Node only: `package.json` must have `scripts.start`, otherwise the CLI errors (`deploy.ts:846-857`).
- Port resolution: flag or liara.json, then the static default table, then an interactive prompt (`deploy.ts:214-217`). See §6.

### Step 2 - Build the JSON release body
`deploy.ts:402-417` builds:
```jsonc
{
  "build": { "cache": true, "args": {"K":"V"}, "dockerfile": "...", "location": "iran|germany" },
  "cron": ["* * * * * cmd"],
  "args": ["sh","-c","..."],          // container entrypoint args
  "port": 3000,
  "type": "node",                     // platform
  "message": "release message",
  "disks": [{"name":"media","mountTo":"/uploads/media"}],
  "envs": {"KEY":"VALUE"}
}
```
- **Image deploy:** add `"image": "nginx:1.25"` and POST it directly, with no upload and no `sourceID` (`deploy.ts:419-422`).
- **Source deploy:** the CLI also adds:
  - `gitInfo`: `{branch, message, commit, committedAt, remote, author:{email,name}, tags:[]}`, filled by shelling out to git. Each value is `null` on failure (`deploy.ts:424`, `cli@14ec35f:src/utils/collect-git-info.ts:4-37`). `committedAt` is `git log --format="%ct"`, a **unix-seconds string** (`collect-git-info.ts:16-20`).
  - `platformConfig`: the liara.json sub-object named after the platform, e.g. `liara.json.node` → `{version, timezone, mirror, ...}`, or `{}` (`deploy.ts:427`).
  - A platform version auto-detected when none is set. It goes into `platformConfig.version` for node/python/php/dotnet/go, `platformConfig.pythonVersion` for django/flask, and `platformConfig.phpVersion` for laravel (`deploy.ts:597-679`, detection logic in `cli@14ec35f:src/services/get-platform-version.ts:13-80`).
  - `healthCheck`: copied from liara.json. A **string `command` is split on spaces into an array** (`deploy.ts:430-436`).

### Step 3 - Pack the source (tar.gz)
- Temp file: `<os.tmpdir()>/liara-cli/<Date.now()>.tar.gz`. The directory is emptied first (`cli@14ec35f:src/services/tmp-dir.ts:5-11`).
- The archive is made with node-tar `create({gzip:{level:9}, cwd: projectPath, filter, file})`. The entries are the top-level items of the project dir that pass the filter, and the filter is applied recursively (`cli@14ec35f:src/utils/create-archive.ts:157-175`). **Format: gzip-compressed tar, paths relative to the project root.**
- Ignore rules (library `ignore`, case-sensitive) (`create-archive.ts:135-138`):
  - Always ignored: `.git .idea .vscode .next .dockerignore *.*~ liara.json node_modules bower_components .DS_Store` (`create-archive.ts:10-21`).
  - Python platforms (django, flask) also ignore: `venv /venv .venv .env ENV .python-version .cache __pycache__ lib lib64 *.py[cod] *$py.class pip-log.txt pip-delete-this-directory.txt celerybeat-schedule`. Django adds `*.log local_settings.py staticfiles`, and Flask adds `instance .webassets-cache` (`create-archive.ts:23-50`). Note: `python` itself has **no** entry in `platformIgnores`, so the plain `python` platform does **not** get these (`create-archive.ts:43-70`).
  - laravel and php ignore `/vendor`. dotnet ignores `Debug/Release/bin/obj/x64/x86/build/bld...` (`create-archive.ts:41-69`).
  - **Per directory**, exactly one ignore file is loaded, in priority order: `.liaraignore`, then `.dockerignore`, then `.gitignore`. Its patterns are rebased to the project root, and nested ignore files in subdirectories are honoured (`create-archive.ts:111-127`, `82-109`). The docs confirm the priority (`docs@13ab045:src/pages/paas/details/ignoring-files.mdx:30-43`, https://docs.liara.ir/paas/details/ignoring-files/). The docs also say this only applies to CLI deploys (`ignoring-files.mdx:40`).
  - `.env` is **not** ignored by default for node/next/php/etc. (only for django/flask). This is a security footgun to handle in our own packer.
  - If everything is ignored, the error is "Seems like you have ignored everything so we can't upload any of your files..." (`create-archive.ts:159-163`).
- Size check: the client limit is `MAX_SOURCE_SIZE = 256 MiB` (`cli@14ec35f:src/constants.ts:29`, check at `deploy.ts:447-465`). The server enforces the per-plan limit and returns HTTP 413 (`deploy.ts:385-392`). Plan limits: Free 128 MB, Standard 256 MB (`cli@14ec35f:src/errors/bundle-plan.ts:13-22`). The docs say Bronze 128 MB, Silver 256 MB, Gold 256 MB (`docs@13ab045:src/pages/paas/details/plans/software-plans.mdx:46`, https://docs.liara.ir/paas/details/plans/software-plans/).

### Step 4 - `POST v2/projects/{app}/sources` (upload)
- `multipart/form-data` with one field, **`file`**, holding the tar.gz stream (`cli@14ec35f:src/services/upload.ts:5-14`). The CLI tracks progress with `uploadProgress` (`deploy.ts:859-891`).
- The OpenAPI agrees: multipart with required `file` (binary, "The .gz file to deploy"). The response is `200 {"sourceID": "..."}`, and errors are 400, 401 and 404 "App does not exists." (`openapi@338325a:spec/paas.yaml:207-252`).
- The CLI deletes the temp file afterwards (`deploy.ts:887-890`).

### Step 5 - `POST v2/projects/{app}/releases` (create release)
- JSON body = the body from Step 2 plus `sourceID` (`deploy.ts:475-483`). The response is `{"releaseID": "..."}` (`cli@14ec35f:src/types/created-release.ts:1-3`; `openapi@338325a:spec/paas.yaml:253-292`).
- The OpenAPI schema `Deploy-releases` only documents `sourceID`, `port` and `type` (`openapi@338325a:spec/paas.yaml:1734-1745`). The other fields (`build`, `cron`, `args`, `message`, `disks`, `envs`, `gitInfo`, `platformConfig`, `healthCheck`, `image`) are known only from the CLI.
- `--detach`: the CLI stops here and prints "Deployment created successfully." (`deploy.ts:225-226`).

### Step 6a - Wait for the build queue: `GET v1/releases/{releaseID}`
- The CLI polls every **3 s** while `release.queue` is truthy and shows "Waiting for the build, N people(s) ahead..." (`deploy.ts:485-506`). The response is `{release: {state, status, failReason?, queue?}}` (`cli@14ec35f:src/types/release.ts:1-6`).

### Step 6b - Stream build logs: `GET v2/releases/{releaseID}/build-logs?since=<cursor>` (polling, **not** websocket)
- The CLI polls every **1 s** (`Poller` default 1000 ms, `cli@14ec35f:src/utils/poller.ts:9-16`). The cursor is the `createdAt` of the last line received (`cli@14ec35f:src/services/build-logs.ts:85-88`). On the first call `since` is uninitialised, so the CLI literally sends `since=undefined` (`build-logs.ts:20,26`).
- The response is `{release: IRelease, buildOutput: [{_id, line, stream, releaseID, createdAt}]}` (`cli@14ec35f:src/types/build-logs-response.ts:4-7`, `src/types/build-output.ts:1-7`).
- How each line is interpreted (`build-logs.ts:29-47`):
  - `stream === 'STDOUT'` is a normal line. A line starting with `Successfully tagged` means the build finished and push begins (pseudo-state `PUSHING`). A line starting with `Pushing... 100%` is `PUSHED`. Any other line starting with `Pushing...` is `PUSHING`. Everything else is `BUILDING`.
  - **Any line whose `stream` is not `STDOUT` (e.g. STDERR) is treated as a build failure.** The CLI rejects with `BuildFailed`, prints that line, and the user sees "Build failed." (`build-logs.ts:44-46`, `deploy.ts:567-571`).
- Terminal states are checked **only on polls that return no new lines** (`build-logs.ts:49-83`). See §3.
- Ctrl-C during the build calls cancel (§4). The cancel handler is removed once push starts (`deploy.ts:513-530`, `553-558`).

### Step 6c - Image deploys only: poll `GET v1/releases/{releaseID}`
- Every 1 s until `FAILED` (with `failReason`), `UNHEALTHY` or `READY` (`deploy.ts:681-724`).

### Step 7 - After success
- The default URL is `https://{app}.liara.run`, or `https://{app}.iran.liara.run` when region is `iran` and the app has no private network (`deploy.ts:236-243`).
- `GET v1/domains?project={app}` lists custom domains. `certificatesStatus === 'ACTIVE'` means https (`deploy.ts:245-259`).
- Unless `--no-app-logs` is passed, the CLI then tails runtime logs through `liara app:logs --since "10s ago" --follow` (`deploy.ts:263-280`). That command polls `GET v2/projects/{app}/logs?start=<unix>&direction=forward&last_lines=...&releaseId=...` every 1 s (`cli@14ec35f:src/commands/app/logs.ts:182-243`).

---

## 3. Release states and how success or failure is detected

Server-side `release.state` values the CLI checks (`cli@14ec35f:src/services/build-logs.ts:50-82`, `src/commands/deploy.ts:693-714`):

| state | meaning in the CLI | CLI outcome |
|---|---|---|
| `queue > 0` (a field, not a state) | waiting for a builder | spinner "people ahead" (`deploy.ts:492-500`) |
| `DEPLOYING` | image built and pushed; container is starting and its health is checked | "Checking container's health ..." (`build-logs.ts:66-69`, `deploy.ts:538-540`) |
| `READY` | **success** | resolve, "Release created." (`build-logs.ts:80-82`, `deploy.ts:565`) |
| `FAILED` | deploy failed; `failReason` may be present | `DeployException(failReason)` or "Release failed." (`build-logs.ts:58-64`) |
| `UNHEALTHY` | deployed but the health check fails | "App deployed, but the container is unhealthy. Please check its logs." / "Release is not healthy. Check logs from web panel" (`build-logs.ts:71-78`, `deploy.ts:542-546`) |
| `TIMEDOUT` | build exceeded the plan's time limit | "Build timed out. It took about 20 minutes." (`build-logs.ts:54-56`, `deploy.ts:294-296`) |
| `CANCELED` | cancelled | "Build canceled.", exit 3 (`build-logs.ts:50-52`, `deploy.ts:573-576`) |

- CLI-only pseudo-states derived from log lines: `BUILDING`, `PUSHING`, `PUSHED` (`build-logs.ts:31-42`). These are not server states.
- The release object also has a `status` field whose values are not used anywhere (`cli@14ec35f:src/types/release.ts:3`).
- `failReason` format: `"<error_name> <args...>"`. The only one the CLI knows is `disk_not_found <disk>`, shown as "Could not find disk `<disk>`." (`deploy.ts:726-734`).
- Zero-downtime: the new release receives traffic only after it is healthy. Otherwise the deploy is cancelled and the old release keeps serving (`docs@13ab045:src/pages/paas/details/zero-downtime-deployment.mdx:31-36`, https://docs.liara.ir/paas/details/zero-downtime-deployment/; `docs@13ab045:src/pages/paas/details/health-check.mdx:28`, https://docs.liara.ir/paas/details/health-check/).
- Recommended success rule for our agent: poll build-logs until `state === 'READY'`. Treat `FAILED | UNHEALTHY | TIMEDOUT | CANCELED`, or any non-STDOUT build line, as failure.

## 4. Cancel

- `POST v2/releases/{releaseID}/cancel`, with no body. The CLI retries it 3 times (`cli@14ec35f:src/services/cancel-deployment.ts:4-15`, used at `deploy.ts:513-530`). Afterwards the release reaches state `CANCELED` (`build-logs.ts:50-52`).
- The team permission "لغو عملیات استقرار" (cancel deployment) exists for the deploy/operate/manage roles (`docs@13ab045:src/pages/references/team/permissions.mdx:100`, https://docs.liara.ir/references/team/permissions/).

## 5. Rollback to an older release

- **The official CLI has no rollback command.** No `rollback` string appears in `cli@14ec35f:src`, and the official OpenAPI has no rollback path (`openapi@338325a:spec/paas.yaml` path list, lines 47-1575).
- The feature exists in the console. The plan table has a row "امکان بازگشت به استقرار قبلی" (ability to return to the previous deploy) marked available on all plans (`docs@13ab045:src/pages/paas/details/plans/software-plans.mdx:49`). The team permission "بازگشت به نسخه قبلی" (return to previous version) is granted to the deploy, operate and manage roles (`docs@13ab045:src/pages/references/team/permissions.mdx:83`). The "History" (تاریخچه) page lists every successful and failed release with its image name, port, git info and message (`docs@13ab045:src/pages/paas/details/private-registry.mdx:32-41`, https://docs.liara.ir/paas/details/private-registry/).
- Listing releases: `GET v1/projects/{app}/releases?page=1&count=10` returns `{total, currentRelease, readyReleasesCount, releases:[{_id, type, imageName, projectType, state, port, gitInfo, client, createdAt, finishedAt, tag ("v1","v2"...), sourceAvailable}], platform}` (`openapi@338325a:spec/paas.yaml:1089-1132`, `1842-1926`; the CLI uses the same endpoint at `cli@14ec35f:src/commands/app/logs.ts:304-317`, interface at `logs.ts:39-64`).
- **Unverified candidate endpoint:** the unofficial MCP calls `POST /v2/projects/{app}/releases/{releaseID}/rollback` (`liara-mcp@4a710ec:src/services/deployment.ts:107-117`). That project also uses multipart field `source` for uploads, where the official CLI and OpenAPI use `file` (`liara-mcp@4a710ec:src/services/deployment.ts:22`). So its endpoints are guesses and must be confirmed (for example in the browser network tab of console.liara.ir) before we rely on them.
- Fallback rollback (also unverified): re-create a release with the old release's `sourceID` (if `sourceAvailable === true`), port, type and config through `POST v2/projects/{app}/releases`. This creates a *new* release and rebuilds, so it is a rebuild rather than an instant swap.

## 6. Supported platforms, detection and default ports

**Platform list:** `node, laravel, php, python, django, flask, dotnet, react, angular, vue, static, docker, next, go` (`cli@14ec35f:src/constants.ts:31-46`). The docs list the same set minus `go` (`docs@13ab045:src/pages/paas/liarajson.mdx:202-214`, https://docs.liara.ir/paas/liarajson/). The detector can also return `wordpress` (`cli@14ec35f:src/utils/detect-platform.ts:160-162`).

**Where the platform comes from at deploy time:** `liara.json.platform` or `--platform` if set, otherwise the app's `project.type` from `GET v1/projects/{app}` (`deploy.ts:202-208`). The file-based detector `detectPlatform()` runs only in `liara init`, not in `deploy` (`cli@14ec35f:src/commands/init.ts:88`).

**Detection order** in `cli@14ec35f:src/utils/detect-platform.ts:9-178`. The first match wins:
1. `*.csproj` next to `Startup.cs`/`Program.cs` (searched up to depth 5): `dotnet` (an error if a `Dockerfile` also exists) (`:19-50`)
2. `composer.json`: `laravel` if `require` has `laravel/framework` or `laravel/lumen-framework`, otherwise `php` (an error if a `Dockerfile` also exists) (`:52-72`)
3. `index.php`: `php` (`:74-76`)
4. `pyproject.toml` or `poetry`: `python` (`:78-80`)
5. `requirements.txt`: `django` if it contains Django/django, `flask` if it contains Flask/flask, otherwise `python`. UTF-16 files are handled through null-interleaved matching (`:82-104`)
6. `Pipfile`: same django/flask/python logic (`:106-118`)
7. `package.json` (an error if a `Dockerfile` also exists): dependency `next` gives `next`; `@angular/core` gives `angular`; devDependency `@vue/cli-service` or (`vue` + devDependency `vite`) gives `vue`; `react-scripts`, (devDependency `vite` + `react`) or `preact` gives `react`; otherwise `node` (`:120-153`)
8. `wp-content/`: `wordpress` (`:155-162`)
9. `go.mod`: `go` (`:164-171`)
10. `Dockerfile`: `docker` (`:173-175`)
11. otherwise `static` (`:177`)

**Default ports**: `cli@14ec35f:src/utils/get-port.ts:5-28`.
- Used without asking: `static, python, react, vue, angular, laravel, wordpress, django, flask, php` → **80**. `next` → **3000** (`get-port.ts:5-20`).
- Other platforms (node, docker, dotnet, go) prompt the user. The suggested defaults are `dotnet` 80, `go` 8080, everything else 3000 (`get-port.ts:22-28`, `cli@14ec35f:src/utils/prompt-port.ts:5-15`). In the API flow we must always send `port`.
- Docs: if `port` is not set in liara.json, a default port is applied (`docs@13ab045:src/pages/paas/liarajson.mdx:241`). The docs examples use `"port": 8080` for go and docker (`docs@13ab045:src/pages/paas/go/how-tos/deploy-app.mdx:300`, `src/pages/paas/docker/how-tos/deploy-app.mdx:289`) and `"port": 80` for dotnet (`docs@13ab045:src/pages/paas/dotnet/how-tos/deploy-app.mdx:120`).

**Supported runtime versions and defaults** (`cli@14ec35f:src/utils/get-supported-versions.ts:7-52`):

| platform | default | allowed |
|---|---|---|
| node | 22 | 14, 16, 18, 20, 22, 24 |
| next (nodeVersion) | 22 | 20, 22, 24 |
| laravel (phpVersion) | 8.2 | 7.2-8.4 |
| php | 8.0 | 7.2-8.4 |
| python, django, flask | 3.12 | 3.7-3.13 |
| go | 1.24 | 1.21-1.25 |
| dotnet | 8.0 | 2.1-10.0 |

Version auto-detection reads: node `package.json engines.node`; python a local venv's `python --version`; php/laravel `composer.json`; dotnet the `.csproj` TargetFramework; go the `go` directive in `go.mod`. It falls back to the local runtime's `--version` (`cli@14ec35f:src/services/get-platform-version.ts:13-80`, `112-395`).

**Per-platform build behaviour (docs.liara.ir)**
- Node: `npm install` (dependencies and devDependencies), then `npm run build` if present, then `npm start`, which is **required** (`docs@13ab045:src/pages/paas/nodejs/how-tos/deploy-app.mdx:41-60`, https://docs.liara.ir/paas/nodejs/how-tos/deploy-app/).
- React: `npm install`, `npm run build`, and `start` if defined. Vite projects must set `build.outDir: "build"` (`docs@13ab045:src/pages/paas/react/how-tos/deploy-app.mdx:44-63`, `106-113`). Vue + Vite must set `outDir: "dist"` (`docs@13ab045:src/pages/paas/vue/how-tos/deploy-app.mdx:101-104`).
- Next: Liara edits `next.config.js` to add `output: 'standalone'`. If that fails, the error is "Could not modify config file" and the user must add it themselves (`docs@13ab045:src/pages/paas/nextjs/fix-common-errors/modify-config-file.mdx:24-50`, https://docs.liara.ir/paas/nextjs/fix-common-errors/modify-config-file/).
- Django and Flask: `requirements.txt` is required and installed with `pip install -r` (`docs@13ab045:src/pages/paas/django/how-tos/deploy-app.mdx:37`, `src/pages/paas/flask/how-tos/deploy-app.mdx:35`).
- Static: HTML, CSS and JS only (`docs@13ab045:src/pages/paas/static/how-tos/deploy-app.mdx:27`).
- Docker: the image is built on Liara and stored in the account's private registry (`docs@13ab045:src/pages/paas/docker/how-tos/deploy-app.mdx:38`).
- The console accepts a **zip** upload by drag and drop (`docs@13ab045:src/pages/paas/nodejs/how-tos/deploy-app.mdx:67`). The CLI and API path uses tar.gz.

## 7. `liara.json` fields

Typed in `cli@14ec35f:src/types/liara-json.ts:18-42`. JSON Schema in `cli@14ec35f:schemas/json/liara.json:294-368`. Docs: https://docs.liara.ir/paas/liarajson/ (`docs@13ab045:src/pages/paas/liarajson.mdx`).

| field | type | maps to API body | notes / source |
|---|---|---|---|
| `app` | string | URL path `{app}` | lowercased (`deploy.ts:836`). Ignored for GitHub deploys (`liarajson.mdx:154-175`) |
| `platform` | string | `type` | overrides `project.type` (`liarajson.mdx:180-226`) |
| `port` | number | `port` | `liarajson.mdx:231-241` |
| `args` | string[] | `args` | container entrypoint args (`liarajson.mdx:1016-1020`) |
| `cron` | string[] | `cron` | crontab lines, `$ROOT` = app dir. Documented for next, laravel, php, python, django, flask (`liarajson.mdx:746-826`) |
| `disks` | `[{name, mountTo}]` | `disks` | the disk must already exist, otherwise `failReason disk_not_found` (`liarajson.mdx:854-869`, `deploy.ts:729-731`) |
| `envs` | `{K: V}` | `envs` | **replaces all existing envs of the app** (`liarajson.mdx:878-901`) |
| `build.location` | `"iran"\|"germany"` | `build.location` | default iran. Germany has unrestricted package downloads but slow push (`docs@13ab045:src/pages/paas/details/build-location.mdx:74-84`). On some plans it fails with 428 `germany_builder_not_allowed` (`deploy.ts:339-351`) |
| `build.cache` | boolean | `build.cache` | `deploy.ts:161,762-764` |
| `build.dockerfile` | string | `build.dockerfile` | `deploy.ts:167` |
| `build.args` | `["K=V"]` | `build.args` (as an object) | `deploy.ts:178-186` |
| `healthCheck` | `{command, interval, timeout, retries, startPeriod}` | `healthCheck` | example `"CMD curl --fail http://localhost:3000 \|\| exit 1"`, 30/15/2/5 (`liarajson.mdx:831-846`). Docs claim the times are in ms (`health-check.mdx:54`), which is suspicious (see open questions). A failing check makes the release `UNHEALTHY`. A later failure triggers an auto-restart (`health-check.mdx:89-94`) |
| `team-id` | string | `?teamID=` | `liarajson.mdx:435-444`, `base.ts:284-293` |
| `<platform>` object | object | `platformConfig` | `deploy.ts:427`. Fields below |

Platform sub-objects (`cli@14ec35f:src/types/*-platfrom-config.ts`, `schemas/json/liara.json:4-292`, `liarajson.mdx:451-1041`):
- `node`: `version`, `npmAudit`, `npmCiFallback`, `timezone`, `mirror`
- `next`: `nodeVersion`, `mirror`, `modifyConfig`, `npmCiFallback`
- `laravel`: `phpVersion`, `timezone`, `npmMirror`, `composerMirror`, `routeCache`, `configCache`, `buildAssets`, `ssr`, `modifyImagickPolicy`, `installDevDependencies`, `reverb`, `reverbPath`, `modifyHtaccess`
- `php`: `version`, `timezone`, `composerMirror`
- `python`: `version`, `mirror`, `timezone`
- `django`: `pythonVersion`, `nodeVersion`, `mirror`, `timezone`, `settingsFile`, `modifySettings`, `collectStatic`, `compileMessages`, `geospatial`, `pipTimeout`. The CLI type and schema misspell the key as `djnago` (`liara-json.ts:33`, `schemas/json/liara.json:322`), but `platformConfig = config[config.platform]` reads `django`, and the docs use `django` (`liarajson.mdx:544-547`)
- `flask`: `pythonVersion`, `nodeVersion`, `mirror`, `timezone`, `appModule` (e.g. `"server:app"`)
- `dotnet`: `version`, `timezone`, `finalDllName`, `csprojectFile`
- `go`: `version`, `cgoEnabled`, `mainFile`, `timezone`
- `react` / `angular`: `mirror`, `sourceMap`. `vue`: `mirror`. `docker`: `timezone` (docs only, `liarajson.mdx:1012-1014`)
- Default timezone: Asia/Tehran (`liarajson.mdx:593`)

## 8. Common deploy failures and what they mean

From the CLI's error handler, `cli@14ec35f:src/commands/deploy.ts:282-399`, unless noted otherwise:

| trigger | message / meaning |
|---|---|
| HTTP 404 on any step | "Could not find the app." Wrong team, wrong account, app not created, or a typo in liara.json `app` (`:298-309`) |
| HTTP 400 `message: "frozen_project"` | "App is frozen (not enough balance)." Unfreeze it in the console (`:311-319`) |
| HTTP 408 | request timed out, network problem (`:321-326`) |
| HTTP 428 `data.code: "max_deployment_count_in_day"` | daily deploy limit. Free 10/day and Standard 50/day per the CLI (`:328-337`, `cli@14ec35f:src/errors/bundle-plan.ts:2-11`). The docs say Bronze 20, Silver 50, Gold unlimited (`software-plans.mdx:45`) |
| HTTP 428 `data.code: "germany_builder_not_allowed"` | plan does not allow the germany builder (`:339-351`, `bundle-plan.ts:43-48`) |
| any other 4xx with `message` | shown as `CODE <status>: <message>` (`:353-361`) |
| HTTP 401 | "Authentication failed", bad or expired token, or wrong region (`:363-375`, `interceptors.ts:8-16`) |
| HTTP 413, or archive > 256 MiB | source too large. Free 128 MB, Standard 256 MB (`:385-392`, `bundle-plan.ts:13-22`) |
| non-STDOUT build line | "Build failed." The offending log line is printed (`build-logs.ts:44-46`, `deploy.ts:567-571`) |
| state `TIMEDOUT` | "Build timed out." Plan limits are Free 5 min, Standard 10 min, Enterprise 20 min (`bundle-plan.ts:24-41`). The docs say 5/10/20 min for Bronze/Silver/Gold (`software-plans.mdx:47`) |
| state `FAILED` + `failReason` | the reason is shown verbatim. `disk_not_found X` becomes "Could not find disk `X`." (`deploy.ts:726-734`) |
| state `UNHEALTHY` | "App deployed, but the container is unhealthy." The health check failed or the app is not listening on `port` (`build-logs.ts:71-78`) |
| project `scale == 0` | "The {app} app isn't running. Please start the app first." (`:194-198`) |
| node app without a `start` script | "A NodeJS app must be runnable with 'npm start'." (`:852-855`) |
| everything ignored | "Seems like you have ignored everything..." (`create-archive.ts:159-163`) |
| empty dir / home dir | "Directory is empty!" / "You're trying to deploy your user directory." (`deploy.ts:738`, `check-path.ts:42`) |
| liara.json parse error | "Syntax error in `liara.json`!" (`deploy.ts:839`) |
| ambiguous detection (e.g. package.json + Dockerfile) | "Please specify your platform with --platform=node or docker." (`detect-platform.ts:120-123`). Only in `liara init` |

Runtime and docs-level errors to recognise in logs:
- Next.js "could not modify config file": add `output: 'standalone'` (`docs@13ab045:src/pages/paas/nextjs/fix-common-errors/modify-config-file.mdx:24-50`).
- Next.js `ECONNRESET`: the TCP connection was dropped unexpectedly (`docs@13ab045:src/pages/paas/nextjs/fix-common-errors/econnreset.mdx:24`).
- Django/Flask/Python `WORKER TIMEOUT`: a Gunicorn worker exceeded the 30 s default. The fix is through env vars (`docs@13ab045:src/pages/paas/django/fix-common-errors/worker-timeout.mdx:26-27`, https://docs.liara.ir/paas/django/fix-common-errors/worker-timeout/).
- App events after deploy: SIGKILL (normal after a new deploy), SIGSTOP, waiting-to-run, running, app turned off (unreachable), stopped due to high RAM (OOM) (`docs@13ab045:src/pages/paas/details/events.mdx:40-57`, https://docs.liara.ir/paas/details/events/). The OpenAPI exposes `GET /v1/projects/{name}/events` (`openapi@338325a:spec/paas.yaml:993`).

## 9. Minimal API-only deploy (pseudocode)

```text
H = {Authorization: "Bearer $TOKEN"}; Q = "?teamID=$TEAM"   # TEAM may be empty
1. GET  https://api.liara.ir/v1/projects/{app}{Q}               -> project.type, project.scale (must be > 0)
2. tar -czf src.tar.gz (apply ignore rules from section 3; exclude .git, node_modules, liara.json, .env...)
3. POST https://api.liara.ir/v2/projects/{app}/sources{Q}       multipart: file=@src.tar.gz -> {sourceID}
4. POST https://api.liara.ir/v2/projects/{app}/releases{Q}      JSON {sourceID, type, port, build:{cache,location,args,dockerfile},
                                                                   envs?, disks?, cron?, args?, message, gitInfo?, platformConfig, healthCheck?}
                                                                 -> {releaseID}
5. loop 3s: GET /v1/releases/{releaseID}{Q} until release.queue falsy
6. loop 1s: GET /v2/releases/{releaseID}/build-logs?since={lastCreatedAt}{Q}
            -> print buildOutput[].line; non-STDOUT => failed
            -> when no new lines: release.state in READY | FAILED(failReason) | UNHEALTHY | TIMEDOUT | CANCELED
7. (cancel) POST /v2/releases/{releaseID}/cancel{Q}
8. GET /v1/domains?project={app}{Q}; URL https://{app}.liara.run
9. tail: GET /v2/projects/{app}/logs?start=<unix>&direction=forward{Q}
```
Image deploy: skip steps 2-3, send `{image, port, type:"docker", ...}` in step 4, then poll `GET /v1/releases/{id}` instead of build-logs (`deploy.ts:419-422`, `681-724`).

---

## Unverified / open questions

1. **Rollback API.** Neither the official CLI nor the official OpenAPI documents it. `POST /v2/projects/{app}/releases/{releaseID}/rollback` comes only from an unofficial MCP (`liara-mcp@4a710ec:src/services/deployment.ts:115`) that also gets the upload field name wrong. It needs confirming with the console's network traffic. Redeploying an old `sourceID` is also unverified.
2. **Full release-body schema.** The OpenAPI documents only `sourceID`, `port` and `type` (`openapi@338325a:spec/paas.yaml:1734-1745`). Server-side validation of `build`, `envs`, `cron`, `disks`, `healthCheck`, `platformConfig` and `gitInfo` is known only from what the CLI sends. Whether `gitInfo` is optional, and whether `committedAt` should be unix seconds (as sent) or ISO date-time (as the OpenAPI response says, `paas.yaml:1890-1893`), is not known.
3. **Whether `envs` in the release body replaces all app envs** (the docs say so for liara.json, `liarajson.mdx:900-901`), and whether omitting `envs` keeps the existing ones. This must be tested before the agent sends `envs`.
4. **Exact set of server `state` values.** The CLI only checks `DEPLOYING, READY, FAILED, UNHEALTHY, TIMEDOUT, CANCELED`, plus the `queue` field. Intermediate states such as BUILDING/QUEUED/PUSHING may exist server-side, and the meaning of the `status` field is unknown.
5. **The `since` parameter on the first build-logs call.** The CLI sends the literal string `undefined`. Whether omitting it is equivalent, and which timestamp format `createdAt` uses, is not known.
6. **Whether non-STDOUT always means failure.** The CLI treats any non-`STDOUT` stream as fatal. Whether the server ever sends benign STDERR (e.g. npm warnings) on that stream, and what other `stream` values exist, is not known.
7. **Whether zip is accepted by `/v2/projects/{app}/sources`.** The console accepts zip, but the OpenAPI says ".gz file". Upload content-type and filename requirements are also not known.
8. **Server-side upload limit.** 128 vs 256 MB per plan comes from the CLI and the docs. The exact 413 payload is unknown.
9. **Plan-limit discrepancies.** The CLI's free plan allows 10 deploys/day; the docs' Bronze plan allows 20/day. The plan IDs (`free/standard/enterprise` in the CLI vs Bronze/Silver/Gold in the docs) need mapping.
10. **Health-check units.** The docs say ms (`health-check.mdx:54`), but the example values (30/15/5) only make sense as seconds, and Docker HEALTHCHECK uses durations. This needs verifying.
11. **Release-list endpoint version.** The CLI and OpenAPI use `GET v1/projects/{app}/releases`; the unofficial MCP uses `v2`. Whether a `GET .../releases/{id}` detail endpoint exists beyond `GET v1/releases/{id}` is unknown.
12. **Default port when `port` is omitted in the API call** for node/docker/go/dotnet. The CLI always sends one, and server behaviour without it is unknown.
13. **WebSocket.** The only websocket in the PaaS spec is the shell (`wss://api.liara.ir?token=...&cmd=/bin/bash&project_id=...`, `openapi@338325a:spec/paas.yaml:6-18`). No websocket for build logs was found, and polling is the documented CLI behaviour.
