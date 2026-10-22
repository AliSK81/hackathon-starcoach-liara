# hackathon-starcoach-liara

StarCoach is an assistant for websites on [Liara](https://liara.ir).
It helps you deploy, watch, diagnose and fix your app.
You talk to it in plain Persian or English.
It asks for your "yes" before any risky action.

## Setup

Needs [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
uv sync
```

```bash
cp .env.example .env
```

Then put your real values in `.env`. It is never committed.

## Commands

| Command | What it does |
|---|---|
| `uv run starcoach --help` | list all commands |
| `uv run starcoach version` | show the version |
| `uv run starcoach check` | test the Liara token and connection |
| `uv run starcoach apps` | list your Liara apps |
| `uv run starcoach status <app>` | one app's state and instances |
| `uv run starcoach recommend [dir]` | suggest platform, port and plan for a project folder |
| `uv run starcoach create <name> --platform P --plan ID --bundle B` | create an app (asks first; costs money) |
| `uv run starcoach deploy <dir> --app <name>` | upload and release a folder, show build progress (asks first) |
| `uv run starcoach logs <app> [--minutes N] [--errors]` | recent logs (errors only with `--errors`) |
| `uv run starcoach events <app>` | app events: restarts, kills, high RAM |
| `uv run starcoach metrics <app>` | CPU and RAM against the plan limits |
| `uv run starcoach health <app or URL> [--tries N]` | probe the site: status codes and latency |
| `uv run starcoach diagnose <app>` | ranked probable causes with evidence and fixes |
| `uv run starcoach verify <app> --causes ID...` | after a fix: wait, re-probe, check old errors are gone |
| `uv run starcoach set-env <app> KEY VALUE` | set one env var (asks first; restarts the app) |
| `uv run starcoach start <app>` / `stop <app>` | turn an app on / off (stop: type the name) |
| `uv run starcoach resize <app> <plan>` | change the plan (type the name) |
| `uv run starcoach eval` | score the diagnosis engine vs a baseline; writes `results/diagnosis-eval.json` |
| `uv run starcoach watch <app...> [--interval 60] [--auto-restart]` | check on a schedule; alert once per change (`results/alerts.jsonl`); diagnose on failure |
| `uv run starcoach domain <app> <domain> [--add] [--check] [--ssl]` | connect a domain; prints the IRNIC / registrar steps |
| `uv run starcoach limits [--topic T]` | what the Liara API cannot do |
| `uv run starcoach web` | open the web chat at http://127.0.0.1:8765 (approval cards, live status) |
| `uv run starcoach chat` | talk to the assistant (Persian or English) |
| `uv run starcoach chat --once "..."` | ask one question and exit |

Every run appends events to `logs/events.jsonl`. Secrets are masked there.

## Tests

Tests run offline.

```bash
uv run pytest -q
```

Lint (optional, uses ruff through uvx):

```bash
uvx ruff check src tests
```

## Docs

- [Roadmap](docs/ROADMAP.md)
- [Progress](docs/PROGRESS.md)
- [Decisions and facts](docs/DECISIONS.md)
- [Requirements](docs/requirements.md)
