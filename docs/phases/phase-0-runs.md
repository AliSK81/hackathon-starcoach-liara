# Phase 0 — The project runs

## Goal
One install command. One run command. One offline test. No keys needed.

## Choices
- Python package `starcoach` in `src/`, run with `uv run starcoach` (D5).
- CLI with stdlib `argparse`. One subcommand per capability.
- `.env` read by a tiny built-in parser. No extra library.
- Append-only JSONL log at `logs/events.jsonl`. Secret values are masked before writing.
- Tests with `pytest`. It is the only dev dependency.

## Checklist
- [x] `pyproject.toml`, `.gitignore`, `.env.example`
- [x] `starcoach --help` and `starcoach version`
- [x] config loader with secret masking
- [x] JSONL event log
- [x] one offline test passes
- [x] README: install, run, test
