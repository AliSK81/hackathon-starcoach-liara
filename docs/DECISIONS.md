# Decisions and checked facts

Rules:
- Never edit old entries.
- A new entry can replace an old one. It says which one ("replaces D3").
- PROGRESS entries link to these IDs.

## Decisions

| ID | Decision | Date | Who |
|---|---|---|---|
| D1 | The Liara API token comes from the user's own `.env` (`LIARA_API_TOKEN`). The tool never reads `~/.liara-auth.json`. | 2026-10-22 | user |
| D2 | Real demo apps are allowed: at most 2 apps, cheapest plan, names start with `starcoach-`. Delete or resize only after the user says yes. | 2026-10-22 | user |
| D3 | The LLM is the user's own OpenAI-compatible provider. Base URL, model and key come from `.env` (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`). | 2026-10-22 | user |
| D4 | Interface: a local web chat and a CLI. The assistant answers in the user's language, Persian first. Docs are in English. | 2026-10-22 | user |
| D5 | Language: Python. Few libraries. Tests run offline. | 2026-10-22 | Claude |
| D6 | Risk tiers for every tool: `read` runs at once; `change` and `danger` need a user "yes" first. | 2026-10-22 | rules (requirements: Human-in-the-Loop) |

## Checked facts

| ID | Fact | Value | Date | Source |
|---|---|---|---|---|
| F1 | The Liara Iran API is reachable from the dev machine. Without a token it returns 401. | `GET https://api.iran.liara.ir/v1/projects` → 401 `{"error":"Unauthorized."}` | 2026-10-22 | `python -c "urllib.request.urlopen(...)"` |
| F2 | The dev machine uses an HTTPS proxy. curl/schannel fails the TLS revocation check through it. Python works. | `https_proxy=http://127.0.0.1:10808`; curl exit 35 `CRYPT_E_REVOCATION_OFFLINE` | 2026-10-22 | `curl -sv https://api.iran.liara.ir/v1/projects` |
| F3 | The installed Liara CLI is broken on the dev machine. We do not depend on it. | `Cannot find module ...@liara\cli\bin\run.js` | 2026-10-22 | `liara --version` |
