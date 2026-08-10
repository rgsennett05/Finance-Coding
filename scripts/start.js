#!/usr/bin/env node
/**
 * The only command anyone needs. Runs first-time setup if it has not happened
 * yet, boots the server, and opens the dashboard.
 */
import { exec } from 'node:child_process';
import { runSetup } from './setup.js';

await runSetup();

const port = process.env.PORT || 4000;
const url = `http://localhost:${port}`;

// Give the server a moment to bind before opening a window at it.
setTimeout(() => {
  const opener =
    process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'start ""' : 'xdg-open';
  exec(`${opener} ${url}`, () => {
    // A headless or restricted environment just means the user clicks the
    // printed link instead.
  });
}, 900);

await import('../src/server.js');
