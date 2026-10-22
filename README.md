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
| `uv run starcoach limits [--topic T]` | what the Liara API cannot do |

Every run appends events to `logs/events.jsonl`. Secrets are masked there.

## Tests

Tests run offline.

```bash
uv run pytest -q
```

## Docs

- [Roadmap](docs/ROADMAP.md)
- [Progress](docs/PROGRESS.md)
- [Decisions and facts](docs/DECISIONS.md)
- [Requirements](docs/requirements.md)
