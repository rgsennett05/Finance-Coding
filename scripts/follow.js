#!/usr/bin/env node
import { addFollow, removeFollow, listFollows, findEntity, SUGGESTED_INSTITUTIONS } from '../src/signals/index.js';

const [cmd, ...rest] = process.argv.slice(2);

const usage = `
  npm run follow -- list
  npm run follow -- search "berkshire"            # find a fund's CIK on EDGAR
  npm run follow -- search "apple" 4              # find a company for Form 4 insiders
  npm run follow -- institution <CIK> "Label"     # 13F filer
  npm run follow -- insider <CIK> "Label"         # company or person filing Form 4s
  npm run follow -- congress "Nancy Pelosi"
  npm run follow -- remove <kind> <identifier>
  npm run follow -- suggestions
`;

switch (cmd) {
  case 'list': {
    const rows = listFollows();
    if (rows.length === 0) console.log('  Following nobody yet.');
    for (const f of rows) console.log(`  ${f.kind.padEnd(12)} ${String(f.identifier).padEnd(12)} ${f.label}`);
    break;
  }

  case 'search': {
    const [name, form] = rest;
    if (!name) { console.log(usage); break; }
    const results = await findEntity(name, form || '13F-HR');
    if (results.length === 0) console.log('  No matches.');
    for (const r of results) console.log(`  CIK ${String(r.cik).padEnd(10)} ${r.label}`);
    break;
  }

  case 'suggestions':
    for (const s of SUGGESTED_INSTITUTIONS) console.log(`  CIK ${s.cik.padEnd(10)} ${s.label}`);
    break;

  case 'remove': {
    const [kind, id] = rest;
    console.log(removeFollow(kind, id) ? `  Unfollowed ${id}.` : '  Not found.');
    break;
  }

  case 'institution':
  case 'insider':
  case 'congress': {
    const [identifier, ...labelParts] = rest;
    if (!identifier) { console.log(usage); break; }
    const f = addFollow(cmd, identifier, labelParts.join(' ') || identifier);
    console.log(`  Following ${f.label} (${f.kind}).`);
    break;
  }

  default:
    console.log(usage);
}
