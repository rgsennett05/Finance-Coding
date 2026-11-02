/**
 * Draws the city: one building per agent, lit by status, grouped by district,
 * with the night's picks, DCF results and the research memo underneath.
 * Self-contained HTML (no external requests) so it can be opened from disk
 * or published as a private Artifact.
 */
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const pct = (n, d = 1) => (Number.isFinite(n) ? `${(n * 100).toFixed(d)}%` : '—');
const usd = (n) => (Number.isFinite(n) ? `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}` : '—');

const STATUS = {
  done: { label: 'Working', cls: 'ok' },
  closed: { label: 'Closed', cls: 'idle' },
  blocked: { label: 'Blocked', cls: 'warn' },
  failed: { label: 'Fire!', cls: 'bad' },
};

function building(a, i) {
  const s = STATUS[a.status] || STATUS.closed;
  const floors = 3 + (i % 4);
  const h = 30 + floors * 16;
  const windows = [];
  for (let f = 0; f < floors; f++) for (let c = 0; c < 3; c++) {
    windows.push(`<rect x="${14 + c * 18}" y="${120 - h + 14 + f * 16}" width="10" height="9" rx="1" class="win ${s.cls}"/>`);
  }
  return `<figure class="bldg ${s.cls}">
  <svg viewBox="0 0 80 124" role="img" aria-label="${esc(a.building)}: ${esc(s.label)}">
    <rect x="6" y="${120 - h}" width="68" height="${h}" rx="3" class="body"/>
    <rect x="30" y="${120 - h - 8}" width="20" height="8" class="roof"/>
    ${windows.join('')}
    <rect x="33" y="106" width="14" height="14" class="door"/>
  </svg>
  <figcaption>
    <strong>${esc(a.building)}</strong>
    <span class="who">${esc(a.name)}</span>
    <span class="pill ${s.cls}">${s.label}</span>
    <span class="sum">${esc(a.summary)}</span>
    ${a.tools?.length ? `<span class="tools">uses ${a.tools.map(esc).join(', ')}</span>` : ''}
    ${a.needs?.length ? `<span class="tools">after ${a.needs.map(esc).join(', ')}</span>` : ''}
  </figcaption>
</figure>`;
}

function bar(v, cls) {
  return `<span class="bar"><span class="fill ${cls}" style="width:${Number.isFinite(v) ? (v * 100).toFixed(0) : 0}%"></span></span>`;
}

export function renderCity(state) {
  const districts = {};
  state.agents.forEach((a, i) => (districts[a.district] ??= []).push(building(a, i)));
  const mayor = state.board.mayor;
  const val = state.board.valuation || {};
  const memo = state.board.research?.memo;

  const rows = (mayor?.ranked || []).map((r, i) => `<tr class="${mayor.picks.includes(r.ticker) ? 'pick' : ''}">
    <td>${i + 1}</td><td><b>${esc(r.ticker)}</b></td><td class="num">${pct(r.score, 0)}</td>
    <td>${bar(r.parts.momentum, 'm')}</td><td>${bar(r.parts.value, 'v')}</td><td>${bar(r.parts.risk, 'r')}</td>
    <td class="muted">${r.missing.length ? `no ${r.missing.join(', ')}` : ''}</td></tr>`).join('');

  const dcfRows = Object.entries(val).map(([t, d]) => d.ok
    ? `<tr><td><b>${esc(t)}</b></td><td class="num">${usd(d.intrinsicPerShare)}</td><td class="num">${usd(d.price)}</td>
       <td class="num ${d.marginOfSafety > 0 ? 'pos' : 'neg'}">${pct(d.marginOfSafety)}</td>
       <td class="num">${pct(d.assumptions.startingGrowth)}</td><td class="num">${pct(d.terminalShareOfValue, 0)}</td>
       <td class="num muted">${usd(Math.min(...d.sensitivity.map((s) => s.perShare)))} – ${usd(Math.max(...d.sensitivity.map((s) => s.perShare)))}</td></tr>`
    : `<tr><td><b>${esc(t)}</b></td><td colspan="6" class="muted">${esc(d.reason)}</td></tr>`).join('');

  const warn = state.agents.flatMap((a) => (a.warnings || []).map((w) => `${a.building}: ${w}`));

  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(state.city)}</title>
<style>
:root{--bg:#eef2f7;--sky:#dfe7f3;--surface:#fff;--ink:#141b26;--ink2:#566174;--line:#d7dee9;--road:#c5ceda;
--ok:#f2b632;--idle:#8b95a5;--warn:#d9822b;--bad:#cf3d33;--body:#3c4a63;--m:#3b6fd8;--v:#159a6c;--r:#8a5cd1;--pos:#0e7a56;--neg:#be3a31}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0d1119;--sky:#121a2a;--surface:#171e2b;--ink:#e6ebf3;--ink2:#9aa6b8;--line:#2a3446;--road:#253046;--body:#2c3953;--pos:#3fc495;--neg:#f0776e}}
:root[data-theme="dark"]{--bg:#0d1119;--sky:#121a2a;--surface:#171e2b;--ink:#e6ebf3;--ink2:#9aa6b8;--line:#2a3446;--road:#253046;--body:#2c3953;--pos:#3fc495;--neg:#f0776e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}h1{margin:0;font-size:26px}h2{font-size:18px;margin:32px 0 10px}
.meta{color:var(--ink2);font-size:13px}.banner{background:var(--warn);color:#fff;padding:8px 12px;border-radius:8px;margin-top:12px;font-size:14px}
.city{background:var(--sky);border-radius:14px;padding:16px;margin-top:16px;display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.district{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px 12px;border-bottom:6px solid var(--road)}
.district h3{margin:0 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink2)}
.bldg{display:flex;gap:10px;margin:8px 0;align-items:flex-end}.bldg svg{width:64px;flex:none}
.body{fill:var(--body)}.roof{fill:var(--ink2)}.door{fill:var(--road)}
.win.ok{fill:var(--ok)}.win.idle{fill:#56627a}.win.warn{fill:var(--warn)}.win.bad{fill:var(--bad)}
.bad .body{animation:flick 1s infinite alternate}@keyframes flick{to{opacity:.7}}
figcaption{display:flex;flex-direction:column;font-size:13px;min-width:0}.who,.tools{color:var(--ink2);font-size:12px}.sum{margin-top:2px}
.pill{align-self:flex-start;font-size:11px;padding:1px 8px;border-radius:99px;color:#fff;margin:2px 0}.pill.ok{background:#b58613}.pill.idle{background:var(--idle)}.pill.warn{background:var(--warn)}.pill.bad{background:var(--bad)}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:4px 12px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{color:var(--ink2);font-weight:500;font-size:12px}
.num{text-align:right;font-variant-numeric:tabular-nums}.muted{color:var(--ink2)}.pos{color:var(--pos)}.neg{color:var(--neg)}
tr.pick td:first-child{box-shadow:inset 3px 0 var(--ok)}
.bar{display:inline-block;width:80px;height:8px;background:var(--line);border-radius:4px;overflow:hidden}.fill{display:block;height:100%}.fill.m{background:var(--m)}.fill.v{background:var(--v)}.fill.r{background:var(--r)}
.memo{white-space:pre-wrap;padding:12px 4px}.grid2{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
ul{margin:8px 0;padding-left:18px}code{font-size:12px}
</style></head><body><main>
<h1>🏙️ ${esc(state.city)}</h1>
<div class="meta">Shift ran ${esc(state.startedAt.replace('T', ' ').slice(0, 16))} UTC${state.offline ? ' · offline mode' : ''} · ${state.agents.length} buildings</div>
${warn.length ? `<div class="banner">${warn.map(esc).join('<br>')}</div>` : ''}
<section class="city">${Object.entries(districts).map(([d, b]) => `<div class="district"><h3>${esc(d)} district</h3>${b.join('')}</div>`).join('')}</section>

<h2>Tonight's picks</h2>
<div class="card"><table><thead><tr><th>#</th><th>Ticker</th><th class="num">Score</th><th>Momentum</th><th>Value</th><th>Safety</th><th></th></tr></thead><tbody>${rows || '<tr><td colspan="7" class="muted">City Hall did not report.</td></tr>'}</tbody></table></div>

<h2>Valuation Bank — DCF</h2>
<div class="card"><table><thead><tr><th>Ticker</th><th class="num">Intrinsic / share</th><th class="num">Price</th><th class="num">Margin of safety</th><th class="num">Start growth</th><th class="num">Terminal % of value</th><th class="num">Sensitivity range</th></tr></thead><tbody>${dcfRows || '<tr><td colspan="7" class="muted">No valuations.</td></tr>'}</tbody></table></div>

${memo ? `<h2>Research Library memo</h2><div class="card memo">${esc(memo)}</div>` : ''}

<h2>Utility grid</h2>
<div class="grid2">
<div class="card"><b>Tools</b><ul>${state.tools.map((t) => `<li><code>${esc(t.name)}</code> <span class="muted">(${esc(t.source)})</span> — ${esc(t.description)}</li>`).join('')}</ul></div>
<div class="card"><b>Mods</b><ul>${state.mods.length ? state.mods.map((m) => `<li><code>${esc(m.name)}</code> — ${esc(m.status)}${m.note ? `: <span class="muted">${esc(m.note)}</span>` : ''}</li>`).join('') : '<li class="muted">none enabled</li>'}</ul></div>
</div>
<p class="meta">Research output, not investment advice. Scores are relative to this watchlist only.</p>
</main></body></html>`;
}
