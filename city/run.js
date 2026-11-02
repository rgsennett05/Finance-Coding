#!/usr/bin/env node
/**
 * City Hall's clock: boots the registry, loads mods, discovers agents and runs
 * them in dependency order. Writes everything to city/state/.
 *
 *   npm run city                 # full run
 *   npm run city -- --offline    # no network; synthetic prices, no SEC/Claude
 *   npm run city -- --only quant # one agent plus whatever it depends on
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Registry } from './registry.js';
import { renderCity } from './render.js';

const here = import.meta.dirname;
const stateDir = path.join(here, 'state');

export async function buildRegistry(config) {
  const registry = new Registry();
  for (const file of fs.readdirSync(path.join(here, 'tools')).filter((f) => f.endsWith('.js'))) {
    registry.add((await import(pathToFileURL(path.join(here, 'tools', file)).href)).default);
  }
  await registry.loadMods(path.join(here, 'mods'), config.mods || []);
  return registry;
}

export async function loadAgents() {
  const dir = path.join(here, 'agents');
  const agents = [];
  for (const file of fs.readdirSync(dir).filter((f) => f.endsWith('.js') && !f.startsWith('_'))) {
    agents.push((await import(pathToFileURL(path.join(dir, file)).href)).default);
  }
  return agents;
}

/** Topological order; throws on unknown dependencies or cycles. */
export function order(agents) {
  const byId = new Map(agents.map((a) => [a.id, a]));
  const out = [], seen = new Set(), visiting = new Set();
  const visit = (a) => {
    if (seen.has(a.id)) return;
    if (visiting.has(a.id)) throw new Error(`Dependency cycle at ${a.id}`);
    visiting.add(a.id);
    for (const dep of a.needs) {
      if (!byId.has(dep)) throw new Error(`${a.id} needs unknown agent "${dep}"`);
      visit(byId.get(dep));
    }
    visiting.delete(a.id); seen.add(a.id); out.push(a);
  };
  agents.forEach(visit);
  return out;
}

function withDeps(agents, id) {
  const byId = new Map(agents.map((a) => [a.id, a]));
  const keep = new Set();
  const add = (x) => { if (keep.has(x)) return; keep.add(x); byId.get(x)?.needs.forEach(add); };
  add(id);
  return agents.filter((a) => keep.has(a.id));
}

export async function runCity({ offline = false, only = null, config: override = null, log = console.log } = {}) {
  const config = override || JSON.parse(fs.readFileSync(path.join(here, 'city.config.json'), 'utf8'));
  const registry = await buildRegistry(config);
  let agents = await loadAgents();
  if (only) agents = withDeps(agents, only);

  const board = {};       // the town square: each agent posts its data here
  const reports = [];
  const startedAt = new Date().toISOString();

  for (const agent of order(agents)) {
    const t0 = Date.now();
    const report = { id: agent.id, name: agent.name, building: agent.building, district: agent.district, role: agent.role, needs: agent.needs, tools: agent.tools };
    const blockedBy = agent.needs.filter((d) => !(d in board));
    if (blockedBy.length) {
      reports.push({ ...report, status: 'blocked', summary: `Waiting on ${blockedBy.join(', ')}` });
      log(`  ⛔ ${agent.building}: blocked by ${blockedBy.join(', ')}`);
      continue;
    }
    // Agents may only use the tools they declare — keeps each building honest.
    const use = (name, input) => {
      if (!agent.tools.includes(name)) throw new Error(`${agent.id} used undeclared tool "${name}"`);
      return registry.use(name, input, { offline, log: (m) => log(`     ${m}`) });
    };
    try {
      const res = await agent.run({ config, board, use, offline });
      if (res.data != null) board[agent.id] = res.data;
      reports.push({ ...report, status: res.status || 'done', summary: res.summary, warnings: res.warnings || [], ms: Date.now() - t0 });
      log(`  ${res.status === 'closed' ? '💤' : '✅'} ${agent.building}: ${res.summary}`);
    } catch (err) {
      reports.push({ ...report, status: 'failed', summary: err.message, ms: Date.now() - t0 });
      log(`  ❌ ${agent.building}: ${err.message}`);
    }
  }

  const state = {
    city: config.name,
    startedAt,
    finishedAt: new Date().toISOString(),
    offline,
    tools: registry.list(),
    mods: registry.mods,
    agents: reports,
    board,
  };
  return state;
}

export function saveState(state) {
  fs.mkdirSync(path.join(stateDir, 'history'), { recursive: true });
  const slim = { ...state, board: { ...state.board, scout: undefined } }; // price series are bulky; keep them out of git
  fs.writeFileSync(path.join(stateDir, 'latest.json'), JSON.stringify(slim, null, 1));
  fs.writeFileSync(path.join(stateDir, 'history', `${state.startedAt.slice(0, 10)}.json`), JSON.stringify(slim, null, 1));
  fs.writeFileSync(path.join(stateDir, 'city.html'), renderCity(state));
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2);
  const onlyIdx = args.indexOf('--only');
  console.log('🏙️  Opening the city…');
  const state = await runCity({ offline: args.includes('--offline'), only: onlyIdx >= 0 ? args[onlyIdx + 1] : null });
  saveState(state);
  console.log(`\nMap written to city/state/city.html`);
  if (state.agents.some((a) => a.status === 'failed')) process.exitCode = 1;
}
