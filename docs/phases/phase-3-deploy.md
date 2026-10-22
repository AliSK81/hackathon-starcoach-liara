# Phase 3 — Deploy

## Goal
From a project folder to a live Liara app: recommend, create, deploy, report.

## Choices
- Platform detection follows the official CLI order (research 02 §6). Default ports from the same table.
- Pre-deploy checks catch known failures early: no `npm start`, Next.js without `output: 'standalone'`, no `requirements.txt`, `.env` in the folder (research 02 §8).
- The plan is chosen from the real plan list in `/v1/me` (`plans.projects`) when the token is set. Rule: the cheapest plan that meets the RAM need of the platform class. Without a token we show the class only.
- Packing: tar.gz, paths relative to the root. Always skip the CLI's fixed list, `.env*`, and patterns from the root `.liaraignore` (or `.gitignore`). `.env` is always skipped, even where the CLI would upload it (security).
- Deploy = upload (`POST /v2/projects/{app}/sources`, multipart `file`) → release (`POST /v2/projects/{app}/releases`) → poll build logs every 2 s until a final state (research 02 §2–3).
- `create_app` and `deploy_app` are `change` tools: they cost money or change the live site.
- A demo app lives in `examples/`.

## Checklist
- [x] `starcoach recommend <dir>`: platform, port, checks, resource class
- [x] plan pick from `/v1/me` plans
- [ ] packer with ignore rules
- [ ] `starcoach deploy <dir> --app <name>` with build progress and final state
- [ ] `starcoach create <name> --platform P --plan ID`
- [ ] agent tools: `recommend_setup`, `create_app`, `deploy_app`, `release_status`
- [x] demo app in `examples/`
- [ ] real deploy answers HTTP 200
