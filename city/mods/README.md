# Mods

A mod is a folder here with an `index.js` that exports:

```js
export default {
  name: 'my-mod',
  description: 'One line on what it adds',
  async register(registry) {
    registry.add({ name: 'some-tool', description: '…', run: async (input, ctx) => ({ … }) },
                 { source: 'mod:my-mod' });
  },
};
```

Turn it on by adding the folder name to `"mods"` in `city/city.config.json`. If `register` throws
(e.g. its package isn't installed) the mod is listed as **skipped** on the city map and everything
else keeps running.

Registering under an existing tool name **replaces** that tool — that's how
`technical-indicators/` upgrades the built-in `indicators` tool for every agent at once.
