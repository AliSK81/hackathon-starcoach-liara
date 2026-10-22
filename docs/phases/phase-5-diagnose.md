# Phase 5 — Diagnose and fix

## Goal
From "my site is broken" to ranked causes, an approved fix, and a checked result.

## Choices
- Deterministic rule engine from research 06 §3–6: regex signatures with weight classes (definitive 60, strong 30, moderate 15, weak 5), probe and metric evidence, contradictions (−30), a logistic confidence. The LLM explains; it does not invent causes.
- The best cause is always shown with its confidence. Further causes only when confidence ≥ 0.3 (changed after F7).
- Container rules (traceback, stack frames) never outrank a specific cause.
- Each cause can carry a suggested action (`set_env`, `resize_app`, `start_app`, `deploy_app`).
- Fix tools: `set_env` (change; merges, refuses when encrypted envs exist), `restart_app`, `start_app` (change), `stop_app`, `resize_app` (danger: the user types the app name).
- `verify_fix`: wait for the app to answer, probe 5 times, and check the old signatures are gone from logs written after the fix.
- Honest testing: labelled incident sets in `evals/`, compared with a naive "first error line" baseline. Results in `results/diagnosis-eval.json`.

## Checklist
- [x] `diagnose.py` engine and `gather` (survives failing sources)
- [x] `starcoach diagnose <app>`
- [x] fix commands: `set-env`, `start`, `stop`, `resize`
- [x] `starcoach verify <app>`
- [x] agent tools: `diagnose_app`, `verify_fix`, `set_env`, `start_app`, `stop_app`, `resize_app`
- [x] `starcoach eval` on dev + 2 holdout sets vs baseline
- [ ] real broken demo app diagnosed and fixed end to end
