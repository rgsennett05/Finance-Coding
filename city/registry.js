/**
 * The city's tool registry — the "utility grid" every building plugs into.
 *
 * A TOOL is a plain object: { name, description, run(input, ctx) }.
 * A MOD is a folder in city/mods/ whose index.js exports
 *   { name, description, register(registry) }
 * and adds tools (or replaces built-in ones) when the city boots.
 *
 * That's the whole contract. Wrapping a library you found on GitHub means
 * writing one small mod that adapts the library's API to `run(input)`.
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

export class Registry {
  constructor() {
    this.tools = new Map();
    this.mods = [];
  }

  add(tool, { source = 'core' } = {}) {
    if (!tool?.name || typeof tool.run !== 'function') {
      throw new Error(`A tool needs a name and a run() function (got ${tool?.name ?? 'nothing'})`);
    }
    this.tools.set(tool.name, { ...tool, source });
    return this;
  }

  has(name) {
    return this.tools.has(name);
  }

  get(name) {
    const tool = this.tools.get(name);
    if (!tool) throw new Error(`No tool named "${name}". Loaded: ${[...this.tools.keys()].join(', ')}`);
    return tool;
  }

  /** Call a tool by name. Agents only ever touch tools through this. */
  async use(name, input, ctx) {
    return this.get(name).run(input, ctx);
  }

  list() {
    return [...this.tools.values()].map(({ name, description, source }) => ({ name, description, source }));
  }

  /**
   * Load each enabled mod. A mod that fails to load (say, its npm package
   * isn't installed) is reported and skipped — it never takes the city down.
   */
  async loadMods(modsDir, enabled = []) {
    for (const name of enabled) {
      const entry = path.join(modsDir, name, 'index.js');
      if (!fs.existsSync(entry)) {
        this.mods.push({ name, status: 'missing', note: `${entry} not found` });
        continue;
      }
      try {
        const mod = (await import(pathToFileURL(entry).href)).default;
        const note = (await mod.register(this)) || null;
        this.mods.push({ name, status: 'loaded', description: mod.description, note });
      } catch (err) {
        this.mods.push({ name, status: 'skipped', note: err.message });
      }
    }
    return this.mods;
  }
}
