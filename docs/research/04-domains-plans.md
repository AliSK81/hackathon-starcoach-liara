# 04 - Liara plans, resource selection, and domains

Research date: 2026-10-22. No authenticated Liara endpoint was called.

Code citations use `repo@sha:file:line`:
- CLI: `liara-cloud/cli@14ec35f79d703a09a5e3abbb22ba59239cdde80d` (v9.6.0, commit 2026-10-18), shortened to `cli@14ec35f`.
- Docs source: `liara-cloud/docs@13ab045fa77384ef5dce46d8ff94d10cc828b3d8` (commit 2026-10-20), shortened to `docs@13ab045`. This repo builds docs.liara.ir, so a `src/pages/X.mdx` path is published at `https://docs.liara.ir/X/`.

Both repos are cloned under `C:\Users\alieb\AppData\Local\Temp\claude\research\`.

---

## Topic A - Plans and resource selection

### A.1 Two plan axes: hardware plan plus feature bundle

Every app (and every database) has two independent plans:
- **Hardware plan** (`planID`): CPU, RAM and disk.
- **Software plan / feature bundle** (`bundlePlanID`): limits and features such as deploys per day, build time, backups, log retention and number of domains.

Sources: https://docs.liara.ir/paas/details/plans/about/, and `cli@14ec35f:src/commands/app/create.ts:66-68,80-89`, which POSTs `{name, planID, platform, bundlePlanID, network, readOnlyRootFilesystem}` to `v1/projects/`.

### A.2 Hardware plans (PaaS), with prices from liara.ir/pricing (read 2026-10-22)

| Persian name (EN) | vCPU | RAM | Disk (SSD) | Toman / month | Toman / hour |
|---|---|---|---|---|---|
| زمین (Earth) | 0.5 | 512 MB | 5 GB | 750,000 | 1,041 |
| مریخ (Mars) | 1 | 1 GB | 10 GB | 1,300,000 | 1,805 |
| مشتری (Jupiter) | 1 | 2 GB | 20 GB | 2,300,000 | 3,194 |
| زحل (Saturn) | 2 | 4 GB | 40 GB | 4,125,000 | 5,729 |
| اورانوس (Uranus) | 4 | 8 GB | 80 GB | 7,250,000 | 10,069 |
| نپتون (Neptune) | 8 | 16 GB | 160 GB | 12,600,000 | 17,500 |
| پلوتون (Pluto) | 16 | 32 GB | 320 GB | 22,000,000 | 30,555 |

Sources:
- Specs: `docs@13ab045:src/pages/paas/details/plans/hardware-plans.mdx:48-52` (https://docs.liara.ir/paas/details/plans/hardware-plans/).
- Prices: https://liara.ir/pricing/. Prices appear there in Persian digits, and the docs page lists no prices.
- In the pricing table, monthly price ≈ hourly price × 720. The CLI does the same thing: it shows `availablePlan.price * 720` as "Tomans/Month" (`cli@14ec35f:src/commands/app/create.ts:215`, `src/commands/plan/list.ts:45`). **The API's `price` field is therefore the hourly price in Toman.**
- Plan guidance from the docs: Earth is "economical, moderate traffic". Jupiter and Saturn are "standard / standard plus" for semi-professional use. Uranus and Neptune are "pro / pro plus" for high traffic and AI. Pluto is the top plan (`hardware-plans.mdx:62-77`).
- The pricing page shows the same seven names and prices for DBaaS (https://liara.ir/pricing/).

### A.3 Plan IDs (machine names) used by the API and CLI

- The CLI hard-codes **no** plan list. It reads plans at runtime from `GET https://api.liara.ir/v1/me` → `plans.projects`.
- The CLI only shows plans where `(id === 'free' || id.includes('g2')) && available && region === 'iran'` (`cli@14ec35f:src/commands/app/create.ts:191-206`; same filter in `src/commands/plan/list.ts:21-28`; for databases, `src/commands/db/create.ts:246-252`, which also checks `supports.includes(type)`).
- Fields per plan: `RAM.amount`, `CPU.amount`, `volume` (disk GB), `price` (hourly), `storageClass`, `available`, `region` (`create.ts:211-216`).
- The only concrete IDs visible in source are `small-g2` and `medium-g2` in unit tests (`cli@14ec35f:test/app/create.unit.test.ts:22,38`), plus the special ID `free`. The mapping from IDs to Persian names (for example, is `small-g2` Earth?) is **not documented**. See open questions.
- Bundle plan IDs: `free`, `basic` (Bronze), `standard` (Silver), `pro` (Gold) (`cli@14ec35f:src/utils/set-bundle-plan-names.ts:1-14`). Bundle prices come from `plans.projectBundlePlans[planID][bundleID].displayPrice`, in Toman per month (`create.ts:149-170`). Bundle prices therefore **depend on the hardware plan**.
- The CLI's `liara plan list` (alias `plan ls`) prints this table (`cli@14ec35f:src/commands/plan/list.ts`).

### A.4 Is there an API that lists plans?

Yes, but it needs authentication. `GET https://api.liara.ir/v1/me` with `Authorization: Bearer <API key>` returns `plans` with these keys:
`projects`, `databases`, `objectStorage`, `mail`, `projectBundlePlans`, `databaseBundlePlans`, `subscription`.
The docs give a `jq '.plans.projects | with_entries(select(.value.available == true))'` example for listing orderable plans (`docs@13ab045:src/pages/references/api/get-info.mdx:467-557,623-639`; https://docs.liara.ir/references/api/get-info/).

Related endpoints:
- Billing: `GET https://api.liara.ir/v1/billing` returns credit balance in Toman, account type and low-credit alert threshold (https://docs.liara.ir/references/api/billing/).
- Free credit: `GET /v1/me/free-credit` returns `remainingFreeCredit` (https://developers.liara.ir/account/user/get-remaining-free-credit.md).
- Subscription: `GET /v1/me/subscription` (get-info doc).
- Change an app's plan: `POST https://api.liara.ir/v1/projects/{name}/resize` with body `{planID}` (https://developers.liara.ir/pass/apps/change-plan.md). The OpenAPI page does not mention changing `bundlePlanID` there.
- Full OpenAPI index: https://developers.liara.ir/llms.txt

No public, unauthenticated plan endpoint was found. For an assistant, prices are best read from `/v1/me` with the user's token.

### A.5 Software plans (feature bundles) for PaaS

From `docs@13ab045:src/pages/paas/details/plans/software-plans.mdx:43-89` (https://docs.liara.ir/paas/details/plans/software-plans/):

| Feature | Bronze (`basic`) | Silver (`standard`) | Gold (`pro`) |
|---|---|---|---|
| Deploys per day | 20 | 50 | unlimited |
| Max source upload | 128 MB | 256 MB | 256 MB |
| Max build time | 5 min | 10 min | 20 min |
| Zero-downtime deploy | no | yes | yes |
| Rollback | yes | yes | yes |
| Hourly / daily / weekly / monthly auto backup | no / no / no / no | no / 7 d / no / no | 12 h / 7 d / 4 w / 3 mo |
| Manual backups per hour (storage) | 0 (0 GB) | 2 (45 GB) | 10 (155 GB) |
| Log retention, metrics history | 7 d, 7 d | 30 d, 30 d | 60 d, 60 d |
| Max disks, FTP accounts | 2, 2 | 5, 2 | 10, 100 |
| Free SSL | yes | yes | yes |
| **Max custom domains** | **5** | **5** | **unlimited** |

Notes:
- The CLI also reads `maxLogsRetention` per bundle from `/v1/me` (`cli@14ec35f:src/commands/app/logs.ts:150`). This is useful for the monitoring feature.
- The 128 MB upload limit on Bronze matters for deploys. The CLI's own `MAX_SOURCE_SIZE` is 256 MiB (`cli@14ec35f:src/constants.ts:29`).

### A.6 Free tier, trial credit and billing

- **Billing is hourly**, deducted from prepaid account credit. The docs say "از آنجایی که محاسبه هزینه‌ها در لیارا ساعتی می‌باشد", meaning costs in Liara are calculated hourly (`docs@13ab045:src/pages/paas/disks/decrease-value.mdx:146`). The pricing page lists both hourly and monthly prices (https://liara.ir/pricing/).
- Credit is topped up in the console under Profile → «افزایش اعتبار» (Increase credit). The amount is entered in **Rial** and paid through a gateway (https://docs.liara.ir/references/console/increase-credit/).
- The console has a cost-estimation view in the same section (https://docs.liara.ir/references/console/cost-estimation/).
- A create call fails with **HTTP 402** when balance is too low. The CLI message is "Not enough balance. Please charge your account." (`cli@14ec35f:src/commands/app/create.ts:110-112`).
- **Free credit:** the docs currently say free credit is not offered: "در حال حاضر اعتبار رایگان ارائه نمی‌شود" (`docs@13ab045:src/pages/references/api/get-info.mdx:269`).
- **Free plan:** the API still knows a `free` plan ID with its own `free` bundle. The server returns `free_plan_platform` (403) when a platform is not allowed on free, and `free_plan_count` (403, "only one app on the free plan") (`cli@14ec35f:src/commands/app/create.ts:76-78,100-133`). The current pricing page lists no free PaaS plan, so whether `free` is still `available` is **unverified**.

### A.7 Which plan for which project? (recommendation, not from Liara)

This is my sizing advice, based on the specs above and general runtime memory needs. Liara does not publish it.

| Project | Hardware | Bundle | Rationale |
|---|---|---|---|
| Static site (`static`, `react`/`vue`/`angular` SPA builds) | Earth (0.5 CPU / 512 MB) | Bronze | Served by a web server, so memory needs are tiny. |
| Small Node / Express / Fastify API | Earth → Mars | Bronze (Silver if zero-downtime is needed) | 512 MB fits a small API. Use Mars if you use ORMs or worker threads. |
| Laravel | Mars (1 GB) | Bronze/Silver | PHP-FPM workers plus queue. Add a managed MySQL/MariaDB. |
| Django / Flask | Mars → Jupiter | Bronze/Silver | Gunicorn with several workers needs about 1-2 GB. Add Postgres. |
| Next.js (SSR) | Jupiter (2 GB) | Silver | The SSR runtime plus image optimization is memory-heavy. Use Earth for `output: export` static (https://docs.liara.ir/paas/nextjs/how-tos/use-static-html-export/). |

Rules of thumb for the agent:
- Start one plan lower and resize with `POST /v1/projects/{name}/resize`, since billing is hourly.
- Upgrade on OOM or restarts seen in logs or metrics. See 03-liara-logs-metrics.md.
- Platform IDs accepted by `liara create`: `node, laravel, php, python, django, flask, dotnet, react, angular, vue, static, docker, next, go` (`cli@14ec35f:src/constants.ts:31-46`).

### A.8 Other Liara products a website needs (short)

| Product | Notes | Links |
|---|---|---|
| Managed DBs (DBaaS) | MySQL, MariaDB, PostgreSQL, MongoDB, Redis, MSSQL, ClickHouse, ElasticSearch, RabbitMQ. Same seven hardware tiers as PaaS on the pricing page, plus Bronze/Silver/Gold DB bundles. API is `POST v1/databases` (`cli@14ec35f:src/commands/db/create.ts:14`). | https://docs.liara.ir/dbaas/about/ , https://docs.liara.ir/dbaas/details/plans/hardware-plans/ , https://docs.liara.ir/dbaas/details/plans/software-plans/ , https://docs.liara.ir/dbaas/details/private-network/ |
| Object Storage (S3-compatible) | 20 GB SSD for 475,000 T/mo (659 T/h) on the pricing page. API base is `https://storage-service.liara.ir` (`cli@14ec35f:src/constants.ts:23`). Supports a custom domain. | https://docs.liara.ir/object-storage/about/ , https://docs.liara.ir/object-storage/details/plans/ , https://docs.liara.ir/object-storage/add-domain/ |
| DNS service | Free ("به صورت کاملاً رایگان", completely free) (`docs@13ab045:src/pages/dns-management-system/about.mdx:40`). Zone API is `https://dns-service.iran.liara.ir/api/v1/zones` (`cli@14ec35f:src/commands/zone/create.ts:10-12`). | https://docs.liara.ir/dns-management-system/about/ |
| Email server | Plans Opal → Diamond, 1,475,000 to 43,000,000 T/mo (pricing page). CLI plan IDs are `m1`..`m8`, modes `DEV`/`LIVE` (`cli@14ec35f:src/constants.ts:49-60`). API base is `https://mail-service.liara.ir`. Needs MX/SPF/DKIM/DMARC records. | https://docs.liara.ir/email-server/about/ , https://docs.liara.ir/email-server/details/dns-records/ , https://docs.liara.ir/email-server/details/plans/ |

---

## Topic B - Domains

### B.1 Default domain

- Every app gets `<app-id>.liara.run` (`docs@13ab045:src/pages/paas/domains/default-subdomain.mdx:27`).
- The CLI prints `https://<app>.iran.liara.run` for Iran-region apps without a private network, and `.liara.run` otherwise (`cli@14ec35f:src/commands/deploy.ts:236-243`).
- After attaching a custom domain, the docs recommend disabling the default subdomain for SEO, under Settings → «زیردامنه پیش‌فرض» (Default subdomain) (`default-subdomain.mdx:33`).

### B.2 Connecting a custom domain: console steps

From `docs@13ab045:src/pages/paas/domains/add-domain.mdx` (https://docs.liara.ir/paas/domains/add-domain/):

1. Open the app, choose «دامنه‌ها» (Domains), then «افزودن دامنه» (Add domain). Enter `mydomain.com` and click «ایجاد دامنه» (Create domain).
2. Liara shows **three DNS records** (`add-domain.mdx:38-46`):
   - **ALIAS / CNAME** at the root, pointing to Liara's server.
   - **TXT**, which proves ownership.
   - **CNAME `_acme-challenge`**, used for DNS-01 validation when issuing and renewing SSL.
3. Add the records at your DNS provider and click «بررسی وضعیت رکوردها» (Check record status). Red ticks turn green when the domain is connected (`add-domain.mdx:50-51`).
4. **With Liara DNS**, these records are added automatically (`add-domain.mdx:66`).
5. **With a CDN**, the red "records not configured" warning can be ignored (`add-domain.mdx:60`).

About the record values:
- The exact target values are per-domain and shown only in the console. The docs give no fixed IP or hostname.
- The API returns the root target as `CNameRecord` and the ownership token as `verificationCode` on the domain object (see B.3).
- Liara uses **ALIAS/CNAME at the apex, not an A record**. An apex CNAME needs a provider that supports ALIAS, ANAME or CNAME-flattening (Liara DNS, Cloudflare, ArvanCloud). Plain registrar DNS that only allows A records at `@` cannot host the apex. Use Liara DNS in that case.

Cloudflare and ArvanCloud flows (same page):
- Change the nameservers at the registrar (nic.ir for `.ir`) and copy Liara's records exactly.
- **Cloudflare:** turn off Universal SSL, issue the Liara certificate, then re-enable Universal SSL (`add-domain.mdx:142`).
- **ArvanCloud:** turn the CDN (proxy) **off** for the `_acme-challenge` record (`add-domain.mdx:227`). Delete Arvan's default A records for `@` and `www` (`:223`). Nameserver changes can take up to 24 h (`:212`).
- Write down existing records, such as email records, before moving nameservers (`:177`).

Related pages:
- www: https://docs.liara.ir/paas/domains/add-www-subdomain/
- Other subdomains: https://docs.liara.ir/paas/domains/add-subdomains/
- Wildcard: https://docs.liara.ir/paas/domains/add-wildcard-domain/
- CDN: https://docs.liara.ir/paas/domains/use-cdn/
- Moving a domain: https://docs.liara.ir/paas/domains/move/

**Supported TLDs:** any TLD except `.gq .cf .ga .ml .tk` (`docs@13ab045:src/pages/paas/domains/supported-tlds.mdx:34-38`).

**Domain limit:** 5 domains on Bronze and Silver, unlimited on Gold (A.5).

### B.3 Domain API endpoints (PaaS)

Base URL is `https://api.liara.ir`. Auth is `Authorization: Bearer <key>`, plus `teamID` for team accounts. Source: https://developers.liara.ir/llms.txt → `pass/domains/*.md`.

| Action | Method and path | Body / params | Notes |
|---|---|---|---|
| List an app's domains | `GET /v1/domains?project=<app>` | | Returns `domains[]` with `_id, name, type, project{_id,project_id}, status, certificatesStatus, redirectTo, redirectStatus, created_at, CNameRecord` ([get-all-domains](https://developers.liara.ir/pass/domains/get-all-domains.md); also `cli@14ec35f:src/base.ts:97-115`, `src/commands/deploy.ts:245-258`). |
| Add a domain | `POST /v1/domains` | `{name, project, type:"PROJECT"}` | 201 returns `{domain:{_id}}`. 404 means the app does not exist. 409 means a conflict, for example the domain is already in use ([create-a-domain](https://developers.liara.ir/pass/domains/create-a-domain.md)). |
| Check DNS / verify | `GET /v1/domains/{id}/check` | | Returns `domain` with `status, certificatesStatus, verificationCode, CNameRecord, punycodeName, issuedAt...` ([check-a-domain](https://developers.liara.ir/pass/domains/check-a-domain.md)). |
| Attach a domain to an app | `POST /v1/domains/set-project` | `{domainID, projectID}` | ([set-a-domain-for-project](https://developers.liara.ir/pass/domains/set-a-domain-for-project.md)) |
| Enable SSL | `POST /v1/domains/provision-ssl-certs` | `{domain}` | Returns `{code}`. 404 means the domain does not exist ([enable-ssl](https://developers.liara.ir/pass/domains/enable-ssl.md)). |
| Disable SSL | see [disable-ssl](https://developers.liara.ir/pass/domains/disable-ssl.md) | | Not fetched in detail. |
| Redirect | `POST /v1/domains/{id}/set-redirect` | `{redirectTo, redirectStatus: 301 \| 302}` | ([redirect-a-domain](https://developers.liara.ir/pass/domains/redirect-a-domain.md)) |
| Delete | see [delete-a-domain](https://developers.liara.ir/pass/domains/delete-a-domain.md) | | Not fetched in detail. |

The deploy command treats `certificatesStatus === 'ACTIVE'` as HTTPS-ready (`cli@14ec35f:src/commands/deploy.ts:255-256`). A good agent loop is:

`create → show CNameRecord/TXT → poll check until status OK → provision-ssl-certs → poll until certificatesStatus=ACTIVE`

The CLI v9.6.0 has **no app-domain commands**. In the CLI, `liara zone ...` covers the DNS service only (`cli@14ec35f:README.md:144-151`).

### B.4 Liara DNS service (zones) vs external DNS

**Console flow:**
1. DNS → «افزودن دامنه» (Add domain).
2. Enter the bare domain, without `www` or `https`.
3. The status becomes «در انتظار تغییر Nameserverها» (waiting for nameserver change).
4. Set Liara's NS records at the registrar, for example nic.ir for `.ir`. The domain activates "after a short time".

Source: `docs@13ab045:src/pages/dns-management-system/quick-setup.mdx` (step 3 at line 68), https://docs.liara.ir/dns-management-system/quick-setup/.

**Zone API** (base `https://dns-service.iran.liara.ir`; the developers portal lists `https://dns-service.liara.ir`):

| Action | Method and path | Source |
|---|---|---|
| Create zone | `POST api/v1/zones {name}` | `cli@14ec35f:src/commands/zone/create.ts:10-39`. 409 means the zone already exists. |
| Re-check nameservers | `PUT api/v1/zones/{zone}/check` | `zone/check.ts:12,38`. 404 means not pending. 406 means "System is checking your domain". |
| Get zone | `GET api/v1/zones/{zone}` | `zone/get.ts:43-64`. Returns `status` (`ACTIVE`/`PENDING`), `nameServers` (what to set) and `currentNameServers` (what the registry currently has). |
| Records | `api/v1/zones/{zone}/dns-records` (CRUD) | `zone/record/create.ts:239-241,315`; https://developers.liara.ir/dns/dns-record/create-dns-record.md |

**Liara nameservers:** these are **`ns1.liara.zone` and `ns2.liara.zone`**. The docs do not print them. I verified them with a live DNS lookup on 2026-10-22: `liara.run NS = ns1.liara.zone, ns2.liara.zone`; `ns1.liara.zone = 185.208.182.251`; `ns2.liara.zone = 45.93.171.227`. Third-party passive DNS also shows customer domains delegated to this pair (https://dns.coffee/domains/blitam.com). **The agent should read `nameServers` from `GET api/v1/zones/{zone}` rather than hard-code them.**

**Which DNS to use:**
- Use **Liara DNS** for zero-config records, including automatic ALIAS, TXT and ACME records. It is free.
- Use an **external DNS** (Cloudflare or Arvan) when a CDN or WAF is needed or DNS is already managed elsewhere. The user must copy the three records by hand, and the CDN must be off on `_acme-challenge`.

### B.5 IRNIC (.ir) - setting nameservers

Typical user steps in the IRNIC panel. Sources: https://www.nic.ir/panel/auth/sign-in; NetAfraz guide (updated 1405/03/31) https://www.netafraz.com/blog/how-to-configure-dns-for-ir-and-generic-top-level-domains-gtlds/; and the same flow described by https://mihanwp.com/change-ir-domain-dns/ and https://iranweb.org/blog/change-dns-in-irnic/. I could not fetch the last two in full.

1. Log in at nic.ir with the IRNIC account (NIC handle such as `ab1234-irnic`, plus password). Sign-up is at https://www.nic.ir/panel/auth/sign-up.
2. Go to «دامنه‌ها» → «دامنه‌های من» (Domains → My domains) and select the domain.
3. Open the DNS / name-server editor. Older guides call it «ویرایش ردیف‌های کارگزاری نام و میزبانی دامنه» (edit the domain's name-server and hosting rows). In the «نام کارگزار» (server name) fields, enter `ns1.liara.zone` and `ns2.liara.zone`. **No IP addresses are needed**, because these are not child nameservers under your own domain.
4. Answer the account's **secret question** («پاسخ سوال امنیتی») and click «ثبت تغییرات» (Save changes).
5. Wait for delegation. Then press "check" in the Liara DNS zone, or call `PUT .../zones/{zone}/check`, until the zone status is `ACTIVE`.

**Timelines** (third-party, not IRNIC-official):
- Usually minutes to 24 h. Reports range from 20 min to 72 h for `.ir`.
- An IRNIC support reply quoted "24 office hours" (NetAfraz comments).
- IRNIC's formal rules require at least one DNS server and recommend at least two (https://www.nic.ir/docs/ir/annex-1-formal-rules).

**Common pitfalls:**
- **Forgotten secret question.** The user must contact IRNIC support. If a reseller is the technical contact, the change can be made through that reseller instead (NetAfraz guide).
- **Only the holder or the technical contact can edit NS records.** A domain bought through a reseller may have to be changed in the reseller's panel.
- **The domain is not active.** This covers a new registration still awaiting IRNIC approval or documents (https://www.nic.ir/upload-document), and an expired domain awaiting renewal (https://www.nic.ir/docs/ir/annex-4-renewal-guideline). NS changes then fail or do not resolve.
- **The zone was not created in Liara first.** Create the zone before switching NS, so that the delegation answers immediately.
- **Typo or extra dot** in the NS hostname. Check with a WHOIS or `dig NS domain.ir` lookup.
- **Leftover records.** Old email, MX or A records at the previous DNS are lost when NS changes. Recreate them in Liara DNS first.

### B.6 Generic registrar steps (non-.ir: .com, .net and others)

1. Log in to the registrar (Namecheap, GoDaddy, Porkbun and others). Open the domain, then **Nameservers / DNS** → choose **Custom DNS**.
2. Enter `ns1.liara.zone` and `ns2.liara.zone`, or the values in the zone's `nameServers`. Remove any other nameservers and save.
3. If **DNSSEC** is enabled at the registrar, remove the DS record first, otherwise resolution breaks. Liara DNS docs do not mention DNSSEC support.
4. Propagation is up to 24-48 h, bounded by the parent TTL. Poll with `PUT .../zones/{zone}/check`.

**Alternative:** keep the registrar's DNS and add the three records from B.2. This works only if the registrar supports ALIAS, ANAME or CNAME-flattening at the apex.

I did not find a Liara-specific source for steps 1-4 (only the Cloudflare and Arvan guides in add-domain). These are standard registrar practice.

### B.7 SSL/HTTPS and www

- **Free SSL** is available in one click from the domain page («تهیه گواهی SSL», Get SSL certificate). Renewal is automatic: "تمدید SSL نیز در زمان مناسب و به صورت خودکار توسط لیارا انجام خواهد شد", meaning Liara renews it automatically at the right time (`docs@13ab045:src/pages/paas/domains/enable-ssl.mdx:31`).
- **SSL is not described as automatic on domain add.** It is a click, or `POST /v1/domains/provision-ssl-certs`.
- The CA is **Let's Encrypt**, using ACME. The `_acme-challenge` CNAME supports DNS-01, which is required for wildcards and lets a certificate be issued before the domain resolves to the app (`docs@13ab045:src/pages/paas/domains/acme-challenge-record.mdx:39-51`).
- Free SSL is included in all bundles (A.5).
- **www:** the domain page has «ساخت زیر دامنه www» (create www subdomain). It shows one extra record to add, and by default www **redirects to the main domain** ("به صورت پیش‌فرض، این زیر دامنه به دامنه اصلی برنامه‌تان، redirect خواهد شد", by default this subdomain redirects to your app's main domain) (`docs@13ab045:src/pages/paas/domains/add-www-subdomain.mdx:37`).
- **Other redirects:** the «ریدایرکت دامنه» (Domain Redirect) section, or `POST /v1/domains/{id}/set-redirect`, with 301 (permanent) or 302 (temporary) (https://docs.liara.ir/paas/domains/redirect-url/).
- **HTTP→HTTPS:** the docs have no "force HTTPS" toggle. See open questions.
- **Cloudflare / Arvan:** Liara's certificate must be issued first, with Cloudflare Universal SSL off or the Arvan CDN off on `_acme-challenge`. Then enable edge SSL (B.2).

---

## Unverified / open questions

1. **Plan-ID ↔ name mapping.** Only `free`, `small-g2` and `medium-g2` appear in source (tests). The IDs for Earth through Pluto are unknown without an authenticated `GET /v1/me`. Confirm with a real token and list `plans.projects` keys with `RAM.amount`/`CPU.amount`.
2. **Is the `free` plan still orderable**, and on which platforms? The server enforces `free_plan_platform` and `free_plan_count`, but pricing lists no free tier. The docs also say free credit is not offered "currently".
3. **Bundle prices** (Bronze/Silver/Gold) vary per hardware plan. They are in `/v1/me` (`displayPrice`), not in public pages I could read. Not verified. The docs say there are four bundles but show three, and the fourth is probably `free`.
4. **Pricing freshness.** The Toman prices come from liara.ir/pricing as read on 2026-10-22. It is not stated whether they include VAT (9-10%). Prices change often.
5. **Exact CNAME/ALIAS target format** (for example `<something>.liara.run` or another host) and the TXT record name. These are only visible in the console or API (`CNameRecord`, `verificationCode`). The docs say only "ALIAS / CNAME".
6. **Whether a plain A record to an IP is supported** for registrars without apex-ALIAS. Not documented.
7. **Nameservers** `ns1/ns2.liara.zone` come from a DNS lookup and third-party data, not from Liara docs. Whether they are the same for every zone is unconfirmed (the API returns `nameServers` per zone). Note the base-URL mismatch for the DNS API: `dns-service.iran.liara.ir` in the CLI vs `dns-service.liara.ir` on the developers portal.
8. **Automatic HTTP→HTTPS redirect** after a certificate is active. Not documented. Test by curling `http://` on a domain with SSL.
9. **What happens when credit runs out** (apps stopped, then deleted after N days?) and whether there is a negative-balance grace period. Not found in the docs I read.
10. **IRNIC panel labels and timelines** come from third-party guides (2024-2026). The live nic.ir panel is a JS app and was not inspected. Whether IRNIC performs a pre-delegation check (rejecting NS that do not answer for the zone) is unconfirmed.
11. Request and response details for `disable-ssl` and `delete-a-domain` were not fetched. Also unknown: whether `bundlePlanID` can be changed through `resize` (the developers portal shows only `planID`).
12. DNSSEC support in Liara DNS is not mentioned anywhere.
