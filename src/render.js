/**
 * Renders a snapshot into a self-contained HTML page.
 *
 * The same output serves the local file and the private Artifact published for
 * phone viewing, so it carries no external requests: no fonts, no scripts, no
 * images. `redact` strips absolute dollar figures while keeping every ratio,
 * weight and percentage intact - the shape of the portfolio without the size.
 */

const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

function formatters(redact) {
  const money = (n) => {
    if (n == null) return '—';
    if (redact) return '•••';
    return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  };
  const money2 = (n) => {
    if (n == null) return '—';
    if (redact) return '•••';
    return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
  };
  const pct = (n) => (n == null ? '—' : `${n}%`);
  const qty = (n) => (n == null ? '—' : Number(n).toLocaleString('en-US', { maximumFractionDigits: 4 }));
  return { money, money2, pct, qty };
}

const CSS = `
:root {
  --ground: #f5f7fa;
  --surface: #ffffff;
  --sunken: #eef2f8;
  --ink: #131a24;
  --ink-2: #4a5568;
  --ink-3: #7d8798;
  --line: #dde3ec;
  --accent: #2e5fd4;
  --pos: #0e7a56;
  --neg: #be3a31;
  --warn: #91610f;
  --radius: 10px;
  --mono: ui-monospace, "SF Mono", SFMono-Regular, "JetBrains Mono", Menlo, Consolas, monospace;
  --sans: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #0d1117;
    --surface: #151b24;
    --sunken: #1b222d;
    --ink: #e7edf6;
    --ink-2: #9aa6b8;
    --ink-3: #6c7889;
    --line: #262f3c;
    --accent: #6e9bff;
    --pos: #45c08a;
    --neg: #f26a60;
    --warn: #d9a23b;
  }
}
:root[data-theme="dark"] {
  --ground: #0d1117;
  --surface: #151b24;
  --sunken: #1b222d;
  --ink: #e7edf6;
  --ink-2: #9aa6b8;
  --ink-3: #6c7889;
  --line: #262f3c;
  --accent: #6e9bff;
  --pos: #45c08a;
  --neg: #f26a60;
  --warn: #d9a23b;
}

body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: var(--sans);
  font-size: 15px;
  line-height: 1.5;
  -webkit-text-size-adjust: 100%;
}
.wrap { max-width: 760px; margin: 0 auto; padding: 20px 16px 56px; display: flex; flex-direction: column; gap: 14px; }

.masthead { display: flex; flex-direction: column; gap: 3px; padding-bottom: 4px; }
.masthead h1 { margin: 0; font-size: 19px; font-weight: 650; letter-spacing: -0.015em; text-wrap: balance; }
.stamp { font-family: var(--mono); font-size: 11px; color: var(--ink-3); letter-spacing: 0.04em; }

.notice {
  background: var(--sunken); border: 1px solid var(--line); border-left: 3px solid var(--warn);
  border-radius: var(--radius); padding: 11px 13px; font-size: 13px; color: var(--ink-2);
}
.notice strong { color: var(--warn); }

.card { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 16px; }
.card > h2 {
  margin: 0 0 12px; font-size: 11px; font-weight: 650; color: var(--ink-3);
  text-transform: uppercase; letter-spacing: 0.09em;
}
.duo { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 560px) { .duo { grid-template-columns: 1fr; } }

.figure { font-family: var(--mono); font-size: 30px; font-weight: 600; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
.figure.sm { font-size: 22px; }
.note { color: var(--ink-2); font-size: 13px; margin-top: 5px; }
.note.tight { font-size: 12px; color: var(--ink-3); }

.pill {
  display: inline-block; font-size: 11px; font-weight: 650; letter-spacing: 0.05em;
  text-transform: uppercase; padding: 2px 8px; border-radius: 999px; border: 1px solid currentColor;
}
.pill.good { color: var(--pos); }
.pill.warn { color: var(--warn); }
.pill.bad  { color: var(--neg); }

.splitbar { display: flex; height: 9px; border-radius: 5px; overflow: hidden; background: var(--sunken); margin: 14px 0 10px; }
.splitbar span { display: block; }
.legend { display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: var(--ink-2); }
.legend b { color: var(--ink); font-family: var(--mono); font-variant-numeric: tabular-nums; font-weight: 600; }
.swatch { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 6px; vertical-align: 1px; }

.bars { display: flex; flex-direction: column; gap: 9px; }
.bar-head { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
.bar-head span:last-child { font-family: var(--mono); color: var(--ink-2); font-variant-numeric: tabular-nums; }
.track { height: 5px; background: var(--sunken); border-radius: 3px; overflow: hidden; margin-top: 4px; }
.fill { height: 100%; background: var(--accent); border-radius: 3px; }

.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: left; font-size: 10px; font-weight: 650; color: var(--ink-3); text-transform: uppercase;
  letter-spacing: 0.07em; padding: 0 10px 7px 0; border-bottom: 1px solid var(--line); white-space: nowrap;
}
td { padding: 9px 10px 9px 0; border-bottom: 1px solid var(--line); vertical-align: top; }
tr:last-child td { border-bottom: none; }
th.n, td.n { text-align: right; padding-right: 0; }
td.n { font-family: var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap; }
.sym { font-weight: 600; }
.sub { display: block; color: var(--ink-3); font-size: 11.5px; font-weight: 400; }
.pos { color: var(--pos); }
.neg { color: var(--neg); }
.warnc { color: var(--warn); }

.spark { display: block; width: 100%; height: 44px; margin-top: 12px; }
.empty { color: var(--ink-3); font-size: 13px; padding: 6px 0; }
footer { color: var(--ink-3); font-size: 11.5px; line-height: 1.6; border-top: 1px solid var(--line); padding-top: 14px; }
`;

function sparkline(history) {
  if (!history || history.length < 2) return '';
  const vals = history.map((h) => h.total);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const span = max - min || 1;
  const w = 300;
  const h = 40;

  const pts = vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w;
    const y = h - ((v - min) / span) * (h - 6) - 3;
    return [Number(x.toFixed(1)), Number(y.toFixed(1))];
  });

  const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x} ${y}`).join(' ');
  const area = `${line} L${w} ${h} L0 ${h} Z`;
  const [lx, ly] = pts[pts.length - 1];

  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img"
      aria-label="Net worth trend across ${history.length} recorded days">
    <path d="${area}" fill="var(--accent)" opacity="0.10" />
    <path d="${line}" fill="none" stroke="var(--accent)" stroke-width="1.6"
          stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" />
    <circle cx="${lx}" cy="${ly}" r="2.6" fill="var(--accent)" />
  </svg>`;
}

function barList(rows, limit = 6) {
  if (!rows || rows.length === 0) return '<p class="empty">Nothing to break down yet.</p>';
  return `<div class="bars">${rows
    .slice(0, limit)
    .map(
      (r) => `<div>
        <div class="bar-head"><span>${esc(r.label)}</span><span>${r.pct}%</span></div>
        <div class="track"><div class="fill" style="width:${Math.max(r.pct, 1)}%"></div></div>
      </div>`
    )
    .join('')}</div>`;
}

export function renderSnapshot(snap, { redact = false, demo = false, title = 'Money' } = {}) {
  const f = formatters(redact);
  const { netWorth: nw, positions: pos, diversification: div, runway, income } = snap;

  const stamp = new Date(snap.generatedAt).toLocaleString('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });

  const runwayPill =
    runway.status === 'buffer met' ? 'good' : runway.status === 'thin' ? 'bad' : 'warn';

  const notices = [];
  if (demo) {
    notices.push(
      `<div class="notice"><strong>Example data.</strong> Nothing here is real — this is the layout
       filled with sample figures so you can decide what to keep, drop, or add before any account is linked.</div>`
    );
  }
  if (redact) {
    notices.push(
      `<div class="notice"><strong>Amounts hidden.</strong> Percentages, weights and ratios are exact;
       every dollar figure is masked.</div>`
    );
  }

  return `<title>${esc(title)}</title>
<style>${CSS}</style>
<div class="wrap">
  <header class="masthead">
    <h1>${esc(title)}</h1>
    <p class="stamp">SNAPSHOT · ${esc(stamp)}</p>
  </header>

  ${notices.join('')}

  <section class="card">
    <h2>Net worth</h2>
    <div class="figure">${f.money(nw.netWorth)}</div>
    <div class="splitbar">
      <span style="width:${nw.bankPct}%;background:var(--pos)"></span>
      <span style="width:${nw.investedPct}%;background:var(--accent)"></span>
    </div>
    <div class="legend">
      <span><i class="swatch" style="background:var(--pos)"></i>Bank <b>${f.money(nw.bank)}</b> · ${nw.bankPct}%</span>
      <span><i class="swatch" style="background:var(--accent)"></i>Invested <b>${f.money(nw.invested)}</b> · ${nw.investedPct}%</span>
      ${nw.liabilities ? `<span><i class="swatch" style="background:var(--neg)"></i>Owed <b>${f.money(nw.liabilities)}</b></span>` : ''}
    </div>
    ${sparkline(nw.history)}
  </section>

  <div class="duo">
    <section class="card">
      <h2>Cash runway</h2>
      <div class="figure sm">${runway.runwayMonths == null ? '—' : `${runway.runwayMonths} mo`}</div>
      <p class="note"><span class="pill ${runwayPill}">${esc(runway.status)}</span></p>
      <p class="note">${f.money(runway.monthlyExpenses)}/mo spending · ${runway.targetMonths}-month target of ${f.money(runway.targetBuffer)}</p>
      <p class="note tight">${runway.surplus >= 0 ? 'Surplus' : 'Short'} ${f.money(Math.abs(runway.surplus))} · ${esc(runway.basis)}</p>
    </section>

    <section class="card">
      <h2>Concentration</h2>
      <div class="figure sm">${div.hhi || '—'}</div>
      <p class="note">Herfindahl index — ${esc(div.hhiVerdict)}</p>
      <p class="note">Top 5 positions hold ${div.topFiveWeight}% of the portfolio.</p>
      ${
        div.concentrated.length
          ? `<p class="note tight warnc">Over your ${div.concentrationWarnPct}% ceiling: ${div.concentrated
              .map((c) => `${esc(c.ticker)} ${c.weight}%`)
              .join(', ')}</p>`
          : `<p class="note tight">No position exceeds your ${div.concentrationWarnPct}% ceiling.</p>`
      }
    </section>
  </div>

  <div class="duo">
    <section class="card">
      <h2>By asset class</h2>
      ${barList(div.byAssetClass)}
    </section>
    <section class="card">
      <h2>By sector</h2>
      ${barList(div.bySector)}
      ${div.bySector.length ? `<p class="note tight">Sector coverage ${div.sectorCoverage}%.</p>` : ''}
    </section>
  </div>

  <section class="card">
    <h2>Dividends &amp; reinvestment · last 12 months</h2>
    <div class="legend" style="margin-bottom:14px">
      <span>Received <b>${f.money2(income.totalIncome)}</b></span>
      <span>Reinvested <b>${f.money2(income.totalReinvested)}</b></span>
      <span>Reinvestment rate <b>${income.reinvestmentRate}%</b></span>
      <span>Trailing yield <b>${income.trailingYieldPct}%</b></span>
    </div>
    ${
      income.byDestination.length
        ? `<div class="scroll"><table>
            <thead><tr><th>Reinvested into</th><th class="n">Amount</th><th class="n">Shares</th><th class="n">Weight now</th></tr></thead>
            <tbody>${income.byDestination
              .map(
                (d) => `<tr>
                  <td><span class="sym">${esc(d.ticker)}</span>${d.name ? `<span class="sub">${esc(d.name)}</span>` : ''}</td>
                  <td class="n">${f.money2(d.amount)}</td>
                  <td class="n">${f.qty(d.shares)}</td>
                  <td class="n">${d.currentWeight == null ? '—' : `${d.currentWeight}%`}</td>
                </tr>`
              )
              .join('')}</tbody></table></div>`
        : `<p class="empty">${
            income.hasData
              ? `Income arrived but none was auto-reinvested — ${f.money2(income.heldAsCash)} is sitting as cash.`
              : 'No dividend or interest activity recorded yet.'
          }</p>`
    }
    ${income.heldAsCash > 0 && income.byDestination.length ? `<p class="note tight">${f.money2(income.heldAsCash)} of income stayed in cash rather than being reinvested.</p>` : ''}
  </section>

  <section class="card">
    <h2>Positions · ${pos.count} holdings</h2>
    ${
      pos.positions.length
        ? `<div class="scroll"><table>
            <thead><tr><th>Holding</th><th class="n">Value</th><th class="n">Unrealized</th><th class="n">Weight</th></tr></thead>
            <tbody>${pos.positions
              .map(
                (p) => `<tr>
                  <td><span class="sym">${esc(p.ticker)}</span><span class="sub">${esc(p.name || p.assetClass || '')}</span></td>
                  <td class="n">${f.money2(p.value)}</td>
                  <td class="n ${p.gain == null ? '' : p.gain >= 0 ? 'pos' : 'neg'}">${
                    p.gain == null ? '—' : `${redact ? '' : `${f.money2(p.gain)} `}${p.gainPct == null ? '' : `${p.gainPct > 0 ? '+' : ''}${p.gainPct}%`}`
                  }</td>
                  <td class="n">${p.weight}%</td>
                </tr>`
              )
              .join('')}</tbody></table></div>`
        : '<p class="empty">No positions yet.</p>'
    }
  </section>

  <footer>
    Generated from your local Finance Coding database and published privately to your claude.ai account.
    This page is a point-in-time snapshot, not a live connection — re-run <code>npm run snapshot</code> to refresh it.
    Balances come from Plaid and reflect your institutions' last reported values.
  </footer>
</div>`;
}
