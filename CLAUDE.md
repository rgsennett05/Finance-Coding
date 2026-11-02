# Ticker City — notes for Claude

## Who this is for
The owner is new to coding and to Claude Code. Explain changes in plain English, define jargon the
first time it appears, and say what they need to do on GitHub (merge, add a secret) step by step.

## What the project is
A "city" of research agents that rank stocks on a watchlist. Agents are buildings (`city/agents/`),
tools are shared utilities (`city/tools/`), and mods (`city/mods/`) wrap outside libraries or data
services. `city/run.js` runs agents in dependency order; `city/render.js` draws the map. See README.md.

## Rules
- Run `npm test` before every commit; add a test for new math or parsing.
- `npm run city:offline` must always work without network or keys.
- Never commit keys. They live in `.env` (gitignored) locally and in GitHub Actions secrets.
- Never present synthetic or missing data as real — say so on the map and in the summary.
- New agents/tools/mods follow the existing contracts; don't change an agent to add a data source —
  write a mod.
- This is research, not trading advice. Don't add order placement or brokerage trading.
