# 01 - Liara REST API surface for apps ("projects")

Researched 2026-10-22. No Liara endpoint was called with a token (the only network checks were downloading public docs and specs, plus DNS lookups).

## Sources and citation keys

| Key | Source | Notes |
|---|---|---|
| `CLI` | `liara-cloud/cli@14ec35f79d703a09a5e3abbb22ba59239cdde80d` (package `@liara/cli` v9.6.0, commit dated 2026-10-18) | Official CLI. Most reliable source for what the server actually accepts. Cited as `CLI:path:line`. |
| `SPEC-PAAS` | https://developers.liara.ir/spec/paas.yaml | Official OpenAPI 3.0.1 spec for PaaS (2039 lines). Cited as `SPEC-PAAS:line`. |
| `SPEC-ME` | https://developers.liara.ir/spec/me.yaml | Official OpenAPI spec for `/v1/me*`. |
| `SPEC-BILLING` | https://developers.liara.ir/spec/billing.yaml | Official OpenAPI spec for `/v1/billing`. |
| `DEVDOCS` | https://developers.liara.ir/ and its index https://developers.liara.ir/llms.txt | Official developer portal (Mintlify). Lists every endpoint page and all specs (llms.txt lines 212-234). |
| `DOCS` | https://docs.liara.ir/ (Persian user docs) | Product behavior: plans, zero-downtime, static IP. |
| `MCP` | `razavioo/liara-mcp@4a710ec7b7bdc11f01c043b220fce2027493020b` (last commit 2025-12-29) | **Unofficial** community MCP server. Some endpoints in it are guesses (see the warnings below). Cited as `MCP:path:line`. |

Other OpenAPI specs on the same portal: `dbaas`, `dns`, `file-browser`, `Iaas`, `mail`, `object-storage`, `ai-*`, `database-inspector` (DEVDOCS llms.txt:214-234).

---

## 1. Base URL, regions, auth

### Base URL
- **Use `https://api.liara.ir`.** It is the `servers[0].url` in the official spec (SPEC-PAAS:28-29; SPEC-ME:8-9; SPEC-BILLING:8-9), and the developer portal lists it as the PaaS and DBaaS base URL (DEVDOCS home page).
- The CLI maps **both** regions to the same host: `REGIONS_API_URL = { iran: 'https://api.liara.ir', germany: 'https://api.liara.ir' }` (CLI:src/constants.ts:10-13). The fallback region is `iran` (CLI:src/constants.ts:27). The base URL is set as the got `prefixUrl`, so CLI paths are relative, e.g. `v1/projects` (CLI:src/base.ts:326-329).
- **History:** the `iran` region was `https://api.iran.liara.ir` from 2020-09-30 (commit `60d742b`, "Add multi region support"). Commit `cfa2826` "Change api base url (#216)" on 2025-03-03 changed it to `https://api.liara.ir` (verified via `git log -L` on src/constants.ts).
- The legacy host `https://api.iran.liara.ir` still exists. The CLI keeps it as `API_IR_URL` (CLI:src/constants.ts:15) and uses it **only** for the shell WebSocket (`wss://api.iran.liara.ir/v1/exec?...`, CLI:src/commands/app/shell.ts:63-70). Many community projects still call `https://api.iran.liara.ir/v1/projects...` (GitHub code search: `liara-cloud/desktop:src/utility/get-apps.utlis.js`, `mohammadhasanii/Liara-Adjust-Scale-Python:main.py`, `PicoPlus/NovinCRM:Infrastructure/Liara/LiaraApiService.cs@ac56bf1`). The unofficial MCP defaults to it (MCP:src/api/client.ts:25). DNS lookups on 2026-10-22 resolved both `api.liara.ir` and `api.iran.liara.ir` to `185.208.181.175`, so they are very likely the same backend.
- **The "germany" region is effectively gone.** The `--region` flag is commented out in the CLI (CLI:src/base.ts:233-236), and both region keys point to the same URL. The only Germany-related concept left is a *build location* ("germany builder"), which is gated by the feature bundle plan (CLI:src/commands/deploy.ts:339-351; CLI:src/errors/bundle-plan.ts:43-48).
- Other service hosts (not needed for apps): IaaS `https://iaas-api.liara.ir`, mail `https://mail-service.liara.ir`, object storage `https://storage-service.liara.ir` (CLI:src/constants.ts:17-23), DNS `https://dns-service.iran.liara.ir` (CLI:src/commands/zone/list.ts:12; the portal lists `https://dns-service.liara.ir`, DEVDOCS home).
- Default app URL after a deploy: `https://<app>.iran.liara.run` when region is iran and the app has no `network`, otherwise `https://<app>.liara.run` (CLI:src/commands/deploy.ts:236-243).

### Auth header
- `Authorization: Bearer <token>` (CLI:src/base.ts:323-324; SPEC-PAAS:2031-2039 declares `bearerAuth` type http, scheme bearer, format JWT). DOCS gives the same example: `curl --url https://api.liara.ir/v1/me --header "Authorization: Bearer TOKEN"` (https://docs.liara.ir/references/api/get-info/).
- The CLI also sends `User-Agent: <oclif userAgent>` and a 10 s request timeout, or 25 s when deploying an image (CLI:src/base.ts:277-283). Neither is required by the API.

### Teams
- Team context is a **query parameter `teamID`**, not a header. The CLI adds `?teamID=<id>` to **every** request, with an empty string meaning the personal account (CLI:src/base.ts:284-294). DOCS says the same: switch to the team first, create the key from the API menu, and send `teamID` (https://docs.liara.ir/references/api/about/).
- Team list endpoint: `GET v2/teams` is paginated with `page` and `count`; the response has `teams[]` and `totalTeams` (CLI:src/team-command.ts:128-155).

### Where users get a token
- Console path: **https://console.liara.ir/API**. Open the "API" menu, choose a validity period, and click "ساخت کلید جدید" (Create new key) (https://docs.liara.ir/references/api/about/). The CLI error text points to the same page: "please get your api token from https://console.liara.ir/API" (CLI:src/commands/account/add.ts:55).
- The MCP README says expiry options are 1 hour, 1 day, 7 days, 1 month, 6 months or 1 year, and that the token is shown only once (MCP:README.md:98-99; also visible on https://glama.ai/mcp/servers/razavioo/liara-mcp). This is not confirmed in official docs.
- Password login (`POST v1/login?expiresIn=1y` with `{email,password,twoFAType?,totp?}`) returns `api_token`, and `POST v1/login/check-if-exists` takes `{email}` (CLI:src/commands/account/add.ts:103-175). **We should not use these.** We should only accept user-pasted API tokens.

---

## 2. Account / connection test

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/me` | Best connection test. 200 returns `{ user, team?, databaseVersions, defaultDatabaseVersions, featureFlags, plans }`; 401 means unauthorized (SPEC-ME:15-34, 141-157). The CLI uses it for `whoami` and to validate a pasted token (CLI:src/commands/whoami.ts:56-58; CLI:src/commands/account/add.ts:266-272). |
| GET | `/v1/me/subscription` | `{ currentSubscriptionPlan }` (SPEC-ME:36-53, 290-294) |
| GET | `/v1/me/free-credit` | `{ remainingFreeCredit }` (SPEC-ME:74-91, 306-310) |
| GET | `/v1/billing` | `{ user: { balance, accountType, minCreditAmount, isManualMinCredit, minCreditLastNotifiedAt } }` (SPEC-BILLING:18-80). Useful for "not enough balance" troubleshooting. |

`user` fields include `_id, fullname, email, phone, isVerified, isTeam, accountType, privateNetworkFeature, legacyNetworkFeature, storage{namespace,status,planID,accessKey,secretKey}`, and more (SPEC-ME:159-218). **Security warning:** `/v1/me` returns object-storage `accessKey`/`secretKey` and national ID. DOCS warns not to log or share it (https://docs.liara.ir/references/api/get-info/). The assistant must strip these fields before passing the response to the LLM or writing logs.

---

## 3. Apps ("projects")

The path parameter `{name}` is the app's **name** (`project_id`, e.g. `my-site`), **not** its Mongo `_id`, unless noted otherwise. See the `{id}` caveat in section 6.

### List apps
- `GET /v1/projects` returns `{ projects: [ { _id, project_id, type, status, scale, planID, bundlePlanID, created_at, isDeployed, network?{_id,name} } ] }` (SPEC-PAAS:47-66, 1691-1722; CLI:src/base.ts:77-95; CLI:src/commands/app/list.ts:20-39).
- Apps without `network` are on the "old infrastructure", and the current CLI refuses logs and shell for them (CLI:src/commands/app/logs.ts:135-144; CLI:src/commands/app/shell.ts:46-61).

### Get app details
- `GET /v1/projects/{name}` returns `{ project: { _id, project_id, type, status, defaultSubdomain, zeroDowntime, scale, envs:[{key,value,encrypted,_id}], planID, bundlePlanID, fixedIPStatus, created_at, hourlyPrice, node:{_id,IP}, isDeployed, reservedDiskSpace, readOnlyRootFilesystem, network:{_id,name} } }`. 404 means the app does not exist (SPEC-PAAS:93-119, 1621-1690; CLI:src/base.ts:117-153).
- `scale == 0` means stopped. The CLI refuses to deploy to an app with `!project.scale` (CLI:src/commands/deploy.ts:194-198).

### Create app
- `POST /v1/projects` (the CLI posts to `v1/projects/` with a trailing slash, CLI:src/commands/app/create.ts:80). JSON body (CLI:src/commands/app/create.ts:80-89; SPEC-PAAS:67-92, 1603-1620):
  ```json
  { "name": "my-site", "planID": "<hardware plan id>", "platform": "node",
    "bundlePlanID": "<feature plan id>", "network": "<network _id>",
    "readOnlyRootFilesystem": false }
  ```
  - The spec schema lists `name, planID, platform, readOnlyRootFilesystem, network` and **omits `bundlePlanID`**, but the official CLI always sends it, so treat it as required in practice.
  - **Network:** the CLI always resolves a network (`--network` or a prompt). It errors out if the user has none and tells them to run `liara network:create` (CLI:src/base.ts:457-505; CLI:src/commands/app/create.ts:62-64). Networks: `GET /v1/networks` returns `{ networks: [{_id,name}] }`, and `POST /v1/networks` takes `{ networkName }` (CLI:src/base.ts:462-463; CLI:src/commands/network/create.ts:28).
  - **Name rule:** the client checks `/^[a-z0-9][a-z0-9\-]+[a-z0-9]$/` and length > 2 (CLI:src/utils/name-regex.ts:1-4; CLI:src/commands/app/create.ts:263-276).
  - **Platforms** (`platform` / `type`): `node, laravel, php, python, django, flask, dotnet, react, angular, vue, static, docker, next, go` (CLI:src/constants.ts:31-46).
  - **Plan ids:** the CLI only offers `free` or ids containing `g2` where `plans.projects[id].available && region === 'iran'` (CLI:src/commands/app/create.ts:200-209). Bundle plan ids are the keys of `plans.projectBundlePlans[planID]`, filtered by `.available`: `free`, `basic` (Bronze), `standard` (Silver), `pro` (Gold) (CLI:src/commands/app/create.ts:158-175; CLI:src/utils/set-bundle-plan-names.ts:1-14). The `free` plan only allows the `free` bundle (CLI:src/commands/app/create.ts:76-78).
- **Errors** (CLI:src/commands/app/create.ts:94-141):
  - 400 with `message` containing `bundlePlan is not available for free plan.`
  - 402 for not enough balance
  - 403 with `data.code` = `free_plan_platform` or `free_plan_count` (only one free app allowed)
  - 409 when the app name already exists (the spec also lists 409, SPEC-PAAS:89-91)
  - 404 when the app could not be created

### Delete app
- `DELETE /v1/projects/{name}` returns 200 ("request submitted") or 204 ("App deleted"); 404 means the app does not exist (SPEC-PAAS:120-145). The CLI maps 409 to "Another operation is already running" (CLI:src/commands/app/delete.ts:30-46).

### Start / stop / scale
- `POST /v1/projects/{name}/actions/scale` with body `{ "scale": 1 }` to start or `{ "scale": 0 }` to stop (SPEC-PAAS:146-182; CLI:src/commands/app/start.ts:27-29; CLI:src/commands/app/stop.ts:27-29). The spec only documents 0 and 1 ("1 to turn on or 0 to turn off"). The MCP sends arbitrary `replicas` (MCP:src/services/apps.ts:114), but that is **unverified**.
- 409 means another operation is running (CLI:src/commands/app/start.ts:42-44).

### Restart
- `POST /v1/projects/{name}/actions/restart` with no body (SPEC-PAAS:183-206; CLI:src/commands/app/restart.ts:27). 409 means another operation is running (CLI:src/commands/app/restart.ts:40-42).

### Change plan / resize
- `POST /v1/projects/{name}/resize` with body `{ "planID": "<hardware plan id>" }` (SPEC-PAAS:472-511). The official CLI has no resize command. The MCP and community scripts use the same path (MCP:src/services/apps.ts:138; `mohammadhasanii/Liara-Adjust-Scale-Python:main.py`).
- DOCS: the new hardware plan must fit all of the app's disks. Downgrading the feature bundle requires meeting that bundle's limits first (for example, removing extra domains) (https://docs.liara.ir/paas/details/change-plan/).
- How to change only the **bundle** plan (e.g. a `bundlePlanID` field on the same endpoint) is not documented. See the open questions.

### Change port (redeploys)
- `POST /v1/projects/update-port` with body `{ "port": 3000, "project": "<name>" }`. The CLI prints "deployed with port", which implies a redeploy (CLI:src/commands/app/update-port.ts:33-37). This endpoint is not in the spec.

---

## 4. Environment variables

- **Read:** there is no dedicated endpoint. Envs are in `GET /v1/projects/{name}` as `project.envs[]` (`{key,value,encrypted,_id}`) (CLI:src/commands/env/list.ts:23-33; SPEC-PAAS:1651-1664).
- **Write:** `POST /v1/projects/update-envs` with body `{ "project": "<name>", "variables": [ {"key":"K","value":"V"}, ... ] }`. The response is `{ message }` (SPEC-PAAS:439-471, 1746-1763).
  - **It replaces the full set.** The CLI fetches the current envs, merges in the new ones, and posts the whole list for `env:set` (CLI:src/commands/env/set.ts:46-54). For `env:unset` it posts the filtered list (CLI:src/commands/env/unset.ts:39-46). Any key we leave out is deleted.
  - Note that `set` appends with `[...appliedEnvs, ...env]` without de-duplicating keys (CLI:src/commands/env/set.ts:48). Our implementation should de-duplicate by key (last one wins) before posting.
- **Setting envs restarts the app.** The CLI confirmation says "Your app will be restarted due to these configuration changes", and on success it prints "Configuration variable applied and restarting <app>" (CLI:src/commands/env/set.ts:55, 105-114; CLI:src/commands/env/unset.ts:47, 67-76). The DOCS env page does not say this either way (https://docs.liara.ir/paas/details/envs/).
- **Encrypted envs:** `encrypted: true` exists on read. Whether `value` is masked for encrypted entries, and so whether a merge-and-post would overwrite secrets with masked values, is **unverified**.
- Envs can also be passed at deploy time in the release body (`envs`, CLI:src/commands/deploy.ts:403-417).

---

## 5. App settings (toggles)

All four use `POST` with **no body**, where `{status}` is `enable` or `disable` (SPEC-PAAS:293-438):

| Setting | Path | Response |
|---|---|---|
| Zero-downtime deploy | `POST /v1/projects/{id}/zero-downtime/{status}` | 200 / 400 / 404 / 409 |
| Default subdomain (`*.liara.run`) | `POST /v1/projects/{id}/default-subdomain/{status}` | 200 / 400 / 404 / 409 |
| Fixed (static outbound) IP | `POST /v1/projects/{id}/fixed-ip/{status}` | 200 returns `{ IP }` |
| Read-only root filesystem | `POST /v1/projects/{id}/read-only/{status}` | 200 / 400 / 404 / 409 |

- The path parameter is named `{id}` in the spec with no description. The MCP passes the app **name** and comments "API uses project ID, but we'll use name" (MCP:src/services/settings.ts:15-19), so **which identifier works is unverified**.
- Current state is visible in project details as `zeroDowntime`, `defaultSubdomain`, `fixedIPStatus`, `readOnlyRootFilesystem` (SPEC-PAAS:1639-1670).
- DOCS: zero-downtime is **on by default** for new apps. A new release only receives traffic once healthy, and if its health check fails the deployment is cancelled (https://docs.liara.ir/paas/details/zero-downtime-deployment/). It requires the Silver or Gold feature bundle (not Bronze) (https://docs.liara.ir/paas/details/plans/software-plans/).
- DOCS: the fixed IP is a **shared, outbound-only** IP meant for whitelisting (payment gateways, SMS providers) (https://docs.liara.ir/paas/details/static-ip/).

---

## 6. Disks

| Method | Path | Body / response | Source |
|---|---|---|---|
| GET | `/v1/projects/{id}/disks` | `{ disks:[{_id,name,size,updatedAt,createdAt}], mounts:[{name,mountedTo}] }` | SPEC-PAAS:629-658, 1927-1951 |
| POST | `/v1/projects/{name}/disks` | `{ name, size }` (size in GB; the spec types it as string, a number also works) -> 201 | SPEC-PAAS:818-860; CLI:src/commands/disk/create.ts:50 |
| POST | `/v1/projects/{name}/disks/{dname}/resize` | `{ size }` | SPEC-PAAS:772-817 |
| DELETE | `/v1/projects/{id}/disks/{name}` | 200 / 409 | SPEC-PAAS:861-896 |
| GET/POST | `/v1/projects/{id}/disks/{name}/backups` | list `{backups:[{name,lastModified,etag,size}]}` / create | SPEC-PAAS:659-726, 1952-1967 |
| POST | `/v1/projects/{id}/disks/{dname}/backups/{bname}/download` | `{ link }` | SPEC-PAAS:727-771 |
| GET/POST | `/v1/projects/{name}/disks/{dname}/ftp` | list `{accesses[],host}` / create `{username, readOnly}` -> `{username,password,host}` | SPEC-PAAS:512-628 |
| DELETE | `/v1/ftp/{fname}` | | SPEC-PAAS:897-926 |

- **`{id}` vs `{name}` caveat:** the official CLI's `init` command calls `GET v1/projects/${project._id}/disks` with the **Mongo `_id`** (CLI:src/commands/init.ts:404-410), while `disk:create` uses the app **name** (CLI:src/commands/disk/create.ts:50). So `{id}` paths may really require `_id`. The safe approach is to resolve `_id` from `GET /v1/projects/{name}` and use it wherever the spec says `{id}`.
- Disk create errors (CLI:src/commands/disk/create.ts:55-92): 400 `not_enough_storage_space`, 400 `"size" must be a number`, 428 with `message === 'max_disks_reached'`. Feature bundle limits: Bronze 2, Silver 5, Gold 10 disks (https://docs.liara.ir/paas/details/plans/software-plans/). The CLI error text says "Free plan 1 disk" (CLI:src/errors/bundle-plan.ts:61-71).
- Disks are mounted via `liara.json` / the release body `disks: [{name, mountTo}]` (CLI:src/types/disk.ts:1-4; CLI:src/commands/deploy.ts:415). A missing disk fails the release with `failReason` `disk_not_found <name>` (CLI:src/commands/deploy.ts:726-733).

---

## 7. Domains (custom domain, DNS check, SSL)

| Method | Path | Body / response | Source |
|---|---|---|---|
| GET | `/v1/domains?project=<name>` | `{ domains:[{_id,name,type,project:{_id,project_id},status,certificatesStatus,redirectTo,redirectStatus,created_at,CNameRecord}] }` | SPEC-PAAS:1347-1376, 1764-1808; CLI:src/commands/deploy.ts:245-259 |
| POST | `/v1/domains` | `{ name, project, type:"PROJECT" }` -> 201 `{ domain:{_id} }`; 409 if it already exists | SPEC-PAAS:1377-1427 |
| GET | `/v1/domains/{id}/check` | DNS/verification check. Returns `{ domain:{ _id,name,status,certificatesStatus,CNameRecord,verificationCode,punycodeName,issuedAt,... } }` | SPEC-PAAS:927-956, 1988-2030 |
| POST | `/v1/domains/set-project` | `{ domainID, projectID }` (move a domain to another app) | SPEC-PAAS:1428-1463 |
| POST | `/v1/domains/{id}/set-redirect` | `{ redirectStatus: 301|302, redirectTo }` | SPEC-PAAS:1464-1507 |
| POST | `/v1/domains/provision-ssl-certs` | `{ domain }` -> `{ code }` (enable / issue free SSL) | SPEC-PAAS:1535-1573 |
| POST | `/v1/domains/{id}/ssl/disable` | 204 | SPEC-PAAS:1508-1534 |
| DELETE | `/v1/domains/{id}` | | SPEC-PAAS:1574-1600 |

- The `project` field in the POST body and the `project` query parameter are the **app name** ("The name of your app", SPEC-PAAS:1355-1360).
- `certificatesStatus === 'ACTIVE'` means HTTPS is live. The CLI uses this to choose between https and http when printing URLs (CLI:src/commands/deploy.ts:254-258).
- The DNS setup the user must do (CNAME target in `CNameRecord`, TXT verification in `verificationCode`) can be read from the check response. The exact meaning of the `status` values is **unverified** (no enum in the spec).
- **Note:** the CLI has **no** PaaS-domain commands. `liara zone create` / "create-domain" in the CLI docs refers to the separate **DNS zone** service on `dns-service` (https://docs.liara.ir/references/cli/create-domain/; CLI:src/commands/zone/create.ts:10-12).

---

## 8. Deploy, releases, rollback

### Deploy (source upload)
1. `POST /v2/projects/{name}/sources`, `multipart/form-data`, with field **`file`** containing a `.tar.gz` of the source. Returns `{ sourceID }` (SPEC-PAAS:207-252; CLI:src/services/upload.ts:5-14). The CLI disables the request timeout for this call. Client-side cap: 256 MiB (CLI:src/constants.ts:29). The server returns 413 when the bundle limit is exceeded (Free/Bronze 128 MB, Silver/Gold 256 MB) (CLI:src/commands/deploy.ts:385-392; https://docs.liara.ir/paas/details/plans/software-plans/). Warning: the MCP uses form field `source` (MCP:src/services/deployment.ts:22), which contradicts both the spec and the CLI, so use `file`.
2. `POST /v2/projects/{name}/releases` with JSON body. Returns `{ releaseID }` (SPEC-PAAS:253-292; CLI:src/commands/deploy.ts:479-483). Body as sent by the CLI (CLI:src/commands/deploy.ts:402-476):
   ```json
   { "sourceID": "...", "type": "node", "port": 3000, "message": "optional",
     "build": { "cache": true, "args": {}, "dockerfile": null, "location": null },
     "cron": [], "args": [], "disks": [{"name":"d1","mountTo":"/data"}], "envs": {},
     "gitInfo": {...}, "platformConfig": { "version": "20" },
     "healthCheck": { "command": ["..."], "interval": 0, "timeout": 0, "retries": 0, "startPeriod": 0 } }
   ```
   For a Docker image deploy, send `image: "<registry/image:tag>"` instead of `sourceID` (CLI:src/commands/deploy.ts:419-422). The spec only documents `sourceID, port, type` (SPEC-PAAS:1734-1745).

### Track a release
- `GET /v1/releases/{releaseID}` returns `{ release: { state, status, failReason?, queue? } }` (CLI:src/commands/deploy.ts:488-506; CLI:src/types/release.ts:1-6). It is polled every ~1-3 s. States seen in the CLI: `BUILDING`, `PUSHING`, `PUSHED`, `DEPLOYING`, `READY`, `UNHEALTHY`, `FAILED`, `CANCELED`, `TIMEDOUT` (CLI:src/services/build-logs.ts:29-83; CLI:src/commands/deploy.ts:693-714).
- `GET /v2/releases/{releaseID}/build-logs?since=<createdAt>` returns `{ release, buildOutput:[{_id,line,stream:'STDOUT'|'STDERR',releaseID,createdAt}] }`. A non-STDOUT line means the build failed (CLI:src/services/build-logs.ts:25-46; CLI:src/types/build-output.ts:1-7).
- `POST /v2/releases/{releaseID}/cancel` cancels a build (CLI:src/services/cancel-deployment.ts:13).

### List releases
- `GET /v1/projects/{name}/releases?page=1&count=10` returns `{ total, currentRelease, readyReleasesCount, platform, releases:[{_id,type,imageName,projectType,state,port,gitInfo,client,createdAt,finishedAt,tag,sourceAvailable}] }` (SPEC-PAAS:1089-1132, 1842-1926; CLI:src/commands/app/logs.ts:39-64, 304-317, which uses `count: 100`). `currentRelease` is the `_id` of the live release.

### Rollback
- **There is no rollback endpoint in the official spec or the official CLI** (searched the spec paths, CLI HEAD, and CLI git history). DOCS says rollback to a previous deployment ("بازگشت به استقرار قبلی") is available on all feature bundles (https://docs.liara.ir/paas/details/plans/software-plans/), and the console "History" tab lists past deployments (https://docs.liara.ir/paas/details/private-registry/). So the feature exists in the console, but its API is undocumented.
- The MCP uses `POST /v2/projects/{name}/releases/{releaseID}/rollback` (MCP:src/services/deployment.ts:107-117). This is **unverified** and may be a guess (the same file also uses `GET /v2/projects/{name}/releases`, which differs from the spec's v1 path).
- **Fallback that is documented:** redeploy an old release's image with `POST /v2/projects/{name}/releases` and `{ "image": "<release.imageName>", "port": <release.port>, "type": "<platform>" }`. Every listed release has `imageName` and `port`. This is a plausible but untested rollback path. `sourceAvailable` may also let us re-release with the old source.

---

## 9. Logs, events, metrics (for monitoring and troubleshooting)

- **Logs (current CLI):** `GET /v2/projects/{name}/logs?start=<unix sec>&direction=forward&last_lines=<bool>&releaseId=<optional>` returns `{ data: [ { metaData:{releaseId}, values:[ ["<ns timestamp>", "<json string {_entry, type:'stdout'|'stderr'}>"] ] } ] }` (CLI:src/commands/app/logs.ts:15-24, 218-283, 387-405). Timeout is 20 s. The CLI re-polls every 1 s.
- Logs (spec, older): `GET /v1/projects/{name}/logs?since=<ts>` returns `[{type,datetime,message}]` (SPEC-PAAS:957-992, 1723-1733). **Prefer the v2 CLI form.**
- Retention depends on the bundle plan: `plans.projectBundlePlans[planID][bundlePlanID].maxLogsRetention` (in days) from `/v1/me` (CLI:src/commands/app/logs.ts:146-163). Values: Bronze 7 days, Silver 30, Gold 60 (https://docs.liara.ir/paas/details/plans/software-plans/). The CLI text says 1 hour for Free (CLI:src/errors/bundle-plan.ts:50-58).
- **Events:** `GET /v1/projects/{name}/events?search=&start=<unix>&end=<unix>` returns `{ data:[{metaData, values:[[...]]}] }` (SPEC-PAAS:993-1058).
- **Applets (containers/pods):** `GET /v1/projects/{name}/applets` returns `{ applets:[{id,name,timestamp,state,reason,release:{releaseID,tag}}] }` (SPEC-PAAS:1059-1088, 1809-1841). Good for "why is it crashing" checks.
- **Metrics:** `GET /v1/projects/{name}/metrics/summary` returns `{ cpuUsage[], memoryUsage[], disksUsage[{size,usage,reportedAt,name}] }` (SPEC-PAAS:1133-1202). Also `.../metrics/{cpu|memory|network-receive|network-transmit}?since=<unix>` returns `{ end, result:[{values:[[ts,val]], applet}] }` (SPEC-PAAS:1203-1346, 1968-1987).
- **Shell:** WebSocket `wss://api.iran.liara.ir/v1/exec?token=<token>&cmd=<cmd>&project_id=<name>&teamID=<id>`. Send `{"action":"start","cols","rows"}`, then `{"type":"input","data"}` / `{"type":"resize",...}` (CLI:src/commands/app/shell.ts:63-108). The spec writes the URL as `wss://api.liara.ir?token=...&cmd=/bin/bash&project_id=...` (SPEC-PAAS:7-14). The token goes **in the query string**, so do not log these URLs.

---

## 10. Plans and pricing

- **No dedicated plans endpoint is documented.** Plans and prices come from **`GET /v1/me`** -> `plans` (SPEC-ME:156-157, 423-450). The official CLI's `plan:list` reads only this (CLI:src/commands/plan/list.ts:21).
  - `plans.projects[<planID>] = { available, region, RAM:{amount}, CPU:{amount}, volume, price, storageClass? }`. `price` is **per hour in Tomans**; the CLI multiplies by 720 to show Tomans/month (CLI:src/commands/plan/list.ts:41-46; CLI:src/commands/app/create.ts:211-215).
  - `plans.projectBundlePlans[<planID>][<bundleId>] = { available, displayPrice, maxLogsRetention, ... }`, where bundle ids are `free|basic|standard|pro` (CLI:src/commands/plan/list.ts:31-39; CLI:src/commands/app/create.ts:158-171).
  - Filter used by the CLI: `(id === 'free' || id.includes('g2')) && available && region === 'iran'` (CLI:src/commands/plan/list.ts:22-28).
- The MCP calls `GET /v1/plans` and `GET /v1/plans/{id}` (MCP:src/services/plans.ts:16, 27). These are **unverified** and not in any official source.
- Per-app actual cost: `project.hourlyPrice` (SPEC-PAAS:1682-1684).
- DOCS hardware tiers (names only; ids not shown): Earth 0.5 CPU / 0.5 GB / 5 GB, Mars 1/1/10, Jupiter 1/2/20, Saturn 2/4/40, Uranus 4/8/80, Neptune 8/16/160, Pluto 16/32/320 (https://docs.liara.ir/paas/details/plans/hardware-plans/).
- DOCS feature bundles (Bronze/Silver/Gold): deploys per day 20/50/unlimited, build time 5/10/20 min, zero-downtime no/yes/yes, domains 5/5/unlimited, disks 2/5/10 (https://docs.liara.ir/paas/details/plans/software-plans/). The CLI error strings disagree slightly ("10 deploys/day on Free", CLI:src/errors/bundle-plan.ts:2-11), so treat the server error as authoritative.

---

## 11. Error format, status codes, rate limits

### Error body shape
JSON with `statusCode`, `message`, and sometimes `data.code`. Examples:
- `err.statusCode === 400 && err.message.includes(...)` (CLI:src/commands/app/create.ts:94-108)
- `err.data.code === 'free_plan_platform'` (CLI:src/commands/app/create.ts:124-134)
- `responseBody.message === 'frozen_project'` (CLI:src/commands/deploy.ts:311-319)
- `responseBody.data.code === 'max_deployment_count_in_day'` (CLI:src/commands/deploy.ts:328-337)
- Team routes return `{ code?, data?:{code?}, message? }` and are read as `data?.code ?? code` (CLI:src/team-command.ts:78-103)

This looks like a Hapi/Boom shape (`{statusCode, error, message, data?}`), but that is inferred, not documented.

### Status codes and what the assistant should say
| Code | Meaning (source) |
|---|---|
| 401 | Bad or expired token, or wrong account (CLI:src/base.ts:256-263; CLI:src/interceptors.ts:4-16) |
| 402 | Not enough balance (CLI:src/commands/app/create.ts:110-112) |
| 400 `frozen_project` | App frozen for low balance; unfreeze in the console (CLI:src/commands/deploy.ts:311-319) |
| 403 | Plan/permission restriction, e.g. `free_plan_platform`, `free_plan_count`; team `no_permission` (CLI:src/commands/app/create.ts:124-134; CLI:src/team-command.ts:49) |
| 404 | App not found; often the wrong team, so check `teamID` (CLI:src/commands/deploy.ts:298-309) |
| 408 | Request timed out (CLI:src/commands/deploy.ts:321-326) |
| 409 | Name conflict on create, or "Another operation is already running" on start/stop/restart/delete (CLI:src/commands/app/create.ts:118-122; CLI:src/commands/app/restart.ts:40-42) |
| 413 | Source too large for the bundle (CLI:src/commands/deploy.ts:385-392) |
| 428 | Plan limit reached: `max_deployment_count_in_day`, `germany_builder_not_allowed`, `max_disks_reached` (CLI:src/commands/deploy.ts:328-351; CLI:src/commands/disk/create.ts:80-86) |

### Rate limits
**No official rate-limit documentation was found**: not on DOCS (https://docs.liara.ir/references/api/about/), the DEVDOCS overview, or the specs. The official CLI has no 429 handling. The unofficial MCP retries 429 and 5xx with exponential backoff (1 s, 2 s, 4 s; 3 retries) (MCP:src/api/client.ts:56-80, 105-107). We should do the same. The only documented quota is the per-day **deployment** limit returned as 428 (see above).

---

## 12. Quick reference for our tool layer

```
BASE = https://api.liara.ir          (header: Authorization: Bearer <token>; query: teamID=<id> optional)
GET    /v1/me                                       connection test + plans/prices
GET    /v1/projects                                 list apps
POST   /v1/projects                                 create {name,planID,platform,bundlePlanID,network,readOnlyRootFilesystem?}
GET    /v1/projects/{name}                          details (+ envs, settings flags, scale)
DELETE /v1/projects/{name}                          delete
POST   /v1/projects/{name}/actions/scale            {scale:0|1}
POST   /v1/projects/{name}/actions/restart
POST   /v1/projects/{name}/resize                   {planID}
POST   /v1/projects/update-envs                     {project,variables:[{key,value}]}  FULL REPLACE, restarts app
POST   /v1/projects/{id}/{zero-downtime|default-subdomain|fixed-ip|read-only}/{enable|disable}
GET    /v1/projects/{id}/disks   POST /v1/projects/{name}/disks {name,size}
GET    /v1/domains?project={name}   POST /v1/domains {name,project,type:"PROJECT"}
GET    /v1/domains/{id}/check   POST /v1/domains/provision-ssl-certs {domain}   DELETE /v1/domains/{id}
POST   /v2/projects/{name}/sources  (multipart "file")  ->  POST /v2/projects/{name}/releases -> {releaseID}
GET    /v1/releases/{releaseID}   GET /v2/releases/{releaseID}/build-logs?since=   POST /v2/releases/{id}/cancel
GET    /v1/projects/{name}/releases?page=&count=
GET    /v2/projects/{name}/logs?start=&direction=forward
GET    /v1/projects/{name}/applets   /events   /metrics/summary
GET    /v1/networks
```

---

## Unverified / open questions

1. **Rollback API.** The console supports rollback, but no endpoint is in the official spec or CLI. `POST /v2/projects/{name}/releases/{releaseID}/rollback` (MCP) is unverified. Fallback: re-release with `{image: <old release.imageName>, port, type}`. Needs a test against a real app, or capturing the console's network calls.
2. **`{id}` vs `{name}`** on settings toggles, disk list/delete/backups, and domain-by-id routes. The CLI uses `_id` for `GET /v1/projects/{id}/disks` (CLI:src/commands/init.ts:409), but the MCP passes the name for settings. We need to test which identifier each route accepts. The safe default is `_id` for `{id}` routes.
3. **`api.liara.ir` vs `api.iran.liara.ir`.** Both resolve to the same IP, and the official CLI moved to `api.liara.ir` in March 2025. We assume they are interchangeable for now. Make it configurable (`LIARA_API_BASE_URL`).
4. **Scale > 1.** Whether `actions/scale` accepts values above 1 (horizontal scaling) is undocumented.
5. **Changing only the feature bundle plan** (e.g. `bundlePlanID` on `/resize`, or another route) is undocumented. Also, whether `/resize` restarts the app or causes downtime.
6. **Encrypted envs.** Does `GET /v1/projects/{name}` return real values for `encrypted: true` envs? If they are masked, a merge-and-post `update-envs` could corrupt secrets. We must test before automating env edits.
7. **Response shapes of action endpoints** (scale, restart, resize, settings toggles) are `content: {}` in the spec. We should expect `{message}` or an empty body and not depend on the content.
8. **Domain `status` / `certificatesStatus` enums.** Only `ACTIVE` is confirmed for certificates (CLI:src/commands/deploy.ts:256). The `provision-ssl-certs` response `code` values are undocumented.
9. **Rate limits.** None are documented. Assume they exist, back off on 429 and 5xx, and poll at 1 s or slower.
10. **Plans endpoint.** `GET /v1/plans` (MCP) is unverified. Use `/v1/me` -> `plans`. The mapping from DOCS tier names (Earth, Mars, ...) to plan ids (`free`, `*g2*`) must be read from `/v1/me` at runtime.
11. **Token expiry options** (1h ... 1y) come only from the unofficial MCP README. The official DOCS only say "choose a validity period".
12. **Network requirement on create.** The CLI always sends `network`, but the spec marks no field as required. We do not know whether create works without a network on accounts that only have `legacyNetworkFeature`.
13. **Error body schema.** `{statusCode, message, data:{code}}` is inferred from CLI parsing (a Boom-like shape) and not documented.
