const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

const money = (n) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const money2 = (n) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
const num = (n, d = 2) => (n == null ? '—' : Number(n).toLocaleString('en-US', { maximumFractionDigits: d }));

let currentSignalSource = '';

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function banner(msg, isError = false) {
  const el = $('#banner');
  if (!msg) return el.classList.add('hidden');
  el.textContent = msg;
  el.classList.toggle('error', isError);
  el.classList.remove('hidden');
}

// --- Tabs ------------------------------------------------------------------

$$('.tab').forEach((tab) =>
  tab.addEventListener('click', () => {
    $$('.tab').forEach((t) => t.classList.toggle('active', t === tab));
    $$('.panel').forEach((p) => p.classList.toggle('hidden', p.id !== `tab-${tab.dataset.tab}`));
  })
);

// --- Plaid Link ------------------------------------------------------------

async function openLink(mode) {
  try {
    const { linkToken } = await api('/api/link/token', { method: 'POST', body: { mode } });
    const handler = Plaid.create({
      token: linkToken,
      onSuccess: async (publicToken) => {
        banner('Linked. Pulling your data…');
        try {
          const r = await api('/api/link/exchange', { method: 'POST', body: { publicToken } });
          banner(`Linked ${r.institutionName}.`);
          await loadAll();
        } catch (err) {
          banner(err.message, true);
        }
      },
      onExit: (err) => {
        if (err) banner(err.display_message || err.error_message || 'Link cancelled.', true);
      },
    });
    handler.open();
  } catch (err) {
    banner(err.message, true);
  }
}

$('#linkBank').addEventListener('click', () => openLink('bank'));
$('#linkBrokerage').addEventListener('click', () => openLink('brokerage'));

$('#syncBtn').addEventListener('click', async (e) => {
  e.target.disabled = true;
  banner('Syncing…');
  try {
    const r = await api('/api/sync', { method: 'POST' });
    const errs = r.items.flatMap((i) => i.errors);
    banner(errs.length ? `Synced with issues: ${errs.join('; ')}` : 'Synced.', errs.length > 0);
    await loadAll();
  } catch (err) {
    banner(err.message, true);
  } finally {
    e.target.disabled = false;
  }
});

// --- Money tab -------------------------------------------------------------

function renderNetWorth(nw) {
  $('#netWorth').textContent = money(nw.netWorth);

  $('#splitBar').innerHTML = `
    <span style="width:${nw.bankPct}%;background:var(--green)"></span>
    <span style="width:${nw.investedPct}%;background:var(--accent)"></span>`;

  $('#splitLegend').innerHTML = `
    <span><i class="dot" style="background:var(--green)"></i>Bank ${money(nw.bank)} · ${nw.bankPct}%</span>
    <span><i class="dot" style="background:var(--accent)"></i>Invested ${money(nw.invested)} · ${nw.investedPct}%</span>
    ${nw.liabilities ? `<span><i class="dot" style="background:var(--red)"></i>Owed ${money(nw.liabilities)}</span>` : ''}`;

  const tbody = $('#accountsTable tbody');
  tbody.innerHTML = nw.accounts.length
    ? nw.accounts
        .map(
          (a) => `<tr>
            <td>${a.institution || ''} — ${a.name}${a.mask ? ` ····${a.mask}` : ''}</td>
            <td class="meta">${a.subtype || a.type}</td>
            <td class="num">${money2(a.balance)}</td>
          </tr>`
        )
        .join('')
    : '<tr><td class="empty">No accounts linked yet.</td></tr>';
}

function renderRunway(r) {
  $('#runwayMonths').textContent = r.runwayMonths == null ? '—' : `${r.runwayMonths} mo`;
  const cls = r.status === 'buffer met' ? 'pos' : r.status === 'thin' ? 'neg' : 'warn';
  $('#runwayDetail').innerHTML =
    r.monthlyExpenses > 0
      ? `<span class="${cls}">${r.status}</span> · ${money(r.monthlyExpenses)}/mo spend · target ${money(r.targetBuffer)} (${r.targetMonths} mo)
         <br>${r.surplus >= 0 ? 'Surplus' : 'Short by'} ${money(Math.abs(r.surplus))}`
      : 'Link a bank account to compute spending.';
  $('#runwayBasis').textContent = r.basis;
}

function bars(container, rows) {
  const el = $(container);
  el.innerHTML = rows.length
    ? rows
        .slice(0, 8)
        .map(
          (r) => `<div class="bar">
            <div class="barTop"><span>${r.label}</span><span>${r.pct}%</span></div>
            <div class="track"><div class="fill" style="width:${r.pct}%"></div></div>
          </div>`
        )
        .join('')
    : '<p class="empty">No holdings yet.</p>';
}

function renderDiversification(d) {
  $('#hhi').textContent = d.hhi || '—';
  $('#hhiVerdict').innerHTML = `Herfindahl index — <strong>${d.hhiVerdict}</strong>`;
  $('#topFive').innerHTML =
    `Top 5 positions = ${d.topFiveWeight}% of portfolio` +
    (d.concentrated.length
      ? `<br><span class="warn">${d.concentrated.map((c) => `${c.ticker} at ${c.weight}%`).join(', ')} over your ${d.concentrationWarnPct}% limit</span>`
      : '');

  bars('#byAssetClass', d.byAssetClass);
  bars('#bySector', d.bySector);
  $('#sectorNote').textContent =
    d.bySector.length === 0
      ? ''
      : `Sector coverage ${d.sectorCoverage}% — Plaid does not return sectors, so anything unmapped shows as Unclassified. Tag tickers in the sector_map table to improve this.`;
}

// --- Holdings --------------------------------------------------------------

function renderPositions(p) {
  $('#positionsSummary').textContent = `${p.count} positions · ${money(p.total)} · unrealized ${money(p.unrealizedGain)}`;
  const tbody = $('#positionsTable tbody');
  tbody.innerHTML = p.positions.length
    ? p.positions
        .map(
          (x) => `<tr>
            <td><strong>${x.ticker}</strong><div class="meta">${x.name || ''}</div></td>
            <td class="meta">${x.account}</td>
            <td class="num">${num(x.quantity, 4)}</td>
            <td class="num">${money2(x.price)}</td>
            <td class="num">${money2(x.value)}</td>
            <td class="num">${x.costBasis == null ? '—' : money2(x.costBasis)}</td>
            <td class="num ${x.gain == null ? '' : x.gain >= 0 ? 'pos' : 'neg'}">
              ${x.gain == null ? '—' : `${money2(x.gain)} (${x.gainPct}%)`}
            </td>
            <td class="num">${x.weight}%</td>
          </tr>`
        )
        .join('')
    : '<tr><td colspan="8" class="empty">No positions yet — link a brokerage account.</td></tr>';
}

// --- Income / DRIP ---------------------------------------------------------

function renderIncome(i) {
  $('#totalIncome').textContent = money2(i.totalIncome);
  $('#trailingYield').textContent = `${i.trailingYieldPct}% trailing yield on current portfolio value`;
  $('#totalReinvested').textContent = money2(i.totalReinvested);
  $('#reinvestRate').innerHTML = `<strong>${i.reinvestmentRate}%</strong> of income reinvested`;
  $('#heldAsCash').textContent = `${money2(i.heldAsCash)} stayed as cash`;

  $('#destTable tbody').innerHTML = i.byDestination.length
    ? i.byDestination
        .map(
          (d) => `<tr>
            <td><strong>${d.ticker}</strong><div class="meta">${d.name || ''}</div></td>
            <td class="num">${money2(d.amount)}</td>
            <td class="num">${num(d.shares, 4)}</td>
            <td class="num">${d.currentWeight == null ? '—' : `${d.currentWeight}%`}</td>
          </tr>`
        )
        .join('')
    : `<tr><td colspan="4" class="empty">${
        i.hasData
          ? 'Income arrived but none of it was auto-reinvested — it is sitting as cash.'
          : 'No dividend or interest activity in the last 12 months.'
      }</td></tr>`;

  $('#destNote').textContent =
    'Sourced from Plaid transaction subtypes (dividend reinvestment, interest reinvestment, capital gain reinvestment) — these are reported by your broker, not inferred.';

  $('#sourceTable tbody').innerHTML = i.bySource.length
    ? i.bySource
        .map(
          (s) => `<tr>
            <td><strong>${s.ticker}</strong><div class="meta">${s.name || ''}</div></td>
            <td class="num">${money2(s.amount)}</td>
            <td class="num">${s.n}</td>
          </tr>`
        )
        .join('')
    : '<tr><td colspan="3" class="empty">Nothing yet.</td></tr>';
}

// --- Follows + signals -----------------------------------------------------

async function loadFollows() {
  const { follows, suggestions } = await api('/api/follows');

  $('#followList').innerHTML = follows.length
    ? follows
        .map(
          (f) => `<span class="chip">${f.label} <span class="meta">${f.kind}</span>
            <button data-kind="${f.kind}" data-id="${f.identifier}">×</button></span>`
        )
        .join('')
    : '<p class="empty">Not following anyone yet.</p>';

  $$('#followList .chip button').forEach((b) =>
    b.addEventListener('click', async () => {
      await api(`/api/follows/${b.dataset.kind}/${encodeURIComponent(b.dataset.id)}`, { method: 'DELETE' });
      loadFollows();
    })
  );

  const following = new Set(follows.map((f) => f.identifier));
  const unseen = suggestions.filter((s) => !following.has(s.cik));
  $('#suggestions').innerHTML = unseen.length
    ? `<h3>Suggested funds</h3>` +
      unseen
        .map(
          (s) => `<div class="result"><span>${s.label}</span>
            <button class="btn addSuggestion" data-cik="${s.cik}" data-label="${s.label}">Follow</button></div>`
        )
        .join('')
    : '';

  $$('.addSuggestion').forEach((b) =>
    b.addEventListener('click', async () => {
      await api('/api/follows', {
        method: 'POST',
        body: { kind: 'institution', identifier: b.dataset.cik, label: b.dataset.label },
      });
      loadFollows();
    })
  );
}

$('#followSearch').addEventListener('click', async () => {
  const kind = $('#followKind').value;
  const q = $('#followQuery').value.trim();
  if (!q) return;

  // Congress members are matched by name against the House index, so there is
  // nothing to look up on EDGAR.
  if (kind === 'congress') {
    await api('/api/follows', { method: 'POST', body: { kind, identifier: q, label: q } });
    $('#followQuery').value = '';
    return loadFollows();
  }

  $('#searchResults').innerHTML = '<p class="empty">Searching EDGAR…</p>';
  try {
    const form = kind === 'institution' ? '13F-HR' : '4';
    const { results } = await api(`/api/follows/search?name=${encodeURIComponent(q)}&form=${form}`);
    $('#searchResults').innerHTML = results.length
      ? results
          .map(
            (r) => `<div class="result"><span>${r.label} <span class="meta">CIK ${r.cik}</span></span>
              <button class="btn addResult" data-cik="${r.cik}" data-label="${r.label}">Follow</button></div>`
          )
          .join('')
      : '<p class="empty">No matches on EDGAR.</p>';

    $$('.addResult').forEach((b) =>
      b.addEventListener('click', async () => {
        await api('/api/follows', {
          method: 'POST',
          body: { kind, identifier: b.dataset.cik, label: b.dataset.label },
        });
        $('#searchResults').innerHTML = '';
        $('#followQuery').value = '';
        loadFollows();
      })
    );
  } catch (err) {
    $('#searchResults').innerHTML = `<p class="empty">${err.message}</p>`;
  }
});

$('#refreshSignals').addEventListener('click', async (e) => {
  e.target.disabled = true;
  $('#refreshReport').textContent = 'Fetching filings — SEC requests are rate limited, this takes a moment…';
  try {
    const { report } = await api('/api/signals/refresh', { method: 'POST' });
    $('#refreshReport').innerHTML = report
      .map((r) => {
        if (r.error) return `<div class="neg">${r.source}${r.actor ? ` (${r.actor})` : ''}: ${r.error}</div>`;
        if (r.skipped) return `<div>${r.source}: skipped — ${r.skipped}</div>`;
        return `<div>${r.source}${r.actor ? ` (${r.actor})` : ''}: ${r.saved ?? 0} rows${
          r.daysStale != null ? ` · ${r.daysStale} days stale` : ''
        }</div>`;
      })
      .join('');
    await loadSignals();
  } catch (err) {
    $('#refreshReport').innerHTML = `<div class="neg">${err.message}</div>`;
  } finally {
    e.target.disabled = false;
  }
});

$$('.filter').forEach((b) =>
  b.addEventListener('click', () => {
    $$('.filter').forEach((x) => x.classList.toggle('active', x === b));
    currentSignalSource = b.dataset.source;
    loadSignals();
  })
);

const SOURCE_LABEL = { form4: 'Insider', '13f': 'Fund', congress: 'Congress', analyst: 'Analysts' };

async function loadSignals() {
  const qs = currentSignalSource ? `?source=${currentSignalSource}` : '';
  const { signals } = await api(`/api/signals${qs}`);

  $('#signalsTable tbody').innerHTML = signals.length
    ? signals
        .map((s) => {
          const size =
            s.amount_low && s.amount_high && s.amount_low !== s.amount_high
              ? `${money(s.amount_low)}–${money(s.amount_high)}`
              : s.amount_low
                ? money(s.amount_low)
                : s.quantity
                  ? `${num(s.quantity, 0)} sh`
                  : '—';
          const lag = s.daysSinceFiled == null ? '—' : `${s.daysSinceFiled}d`;
          const cls = ['buy', 'new', 'increase'].includes(s.action)
            ? 'pos'
            : ['sell', 'exit', 'reduce'].includes(s.action)
              ? 'neg'
              : '';
          return `<tr>
            <td>${s.actor_label || s.actor}<div class="meta">${SOURCE_LABEL[s.source] || s.source}</div></td>
            <td class="${cls}">${s.raw?.actionLabel || s.action}</td>
            <td>${s.ticker || s.security_name || '—'}</td>
            <td class="num">${size}</td>
            <td>${s.filed_at || '—'}${s.url ? ` <a href="${s.url}" target="_blank" rel="noopener">↗</a>` : ''}</td>
            <td class="meta">${lag}</td>
          </tr>`;
        })
        .join('')
    : '<tr><td colspan="6" class="empty">Follow someone, then hit “Refresh disclosures”.</td></tr>';
}

// --- Settings --------------------------------------------------------------

async function loadPrefs() {
  const prefs = await api('/api/prefs');
  for (const key of ['target_buffer_months', 'concentration_warn_pct', 'signal_lookback_days']) {
    const el = $(`#pref_${key}`);
    if (el) el.value = prefs[key] ?? '';
  }

  const { items } = await api('/api/items');
  $('#itemsTable tbody').innerHTML = items.length
    ? items
        .map(
          (i) => `<tr>
            <td>${i.institution_name || i.item_id}</td>
            <td class="meta">${i.account_count} accounts · synced ${i.last_synced_at || 'never'}</td>
            <td class="num"><button class="btn unlink" data-id="${i.item_id}">Unlink</button></td>
          </tr>`
        )
        .join('')
    : '<tr><td class="empty">Nothing linked.</td></tr>';

  $$('.unlink').forEach((b) =>
    b.addEventListener('click', async () => {
      await api(`/api/items/${b.dataset.id}`, { method: 'DELETE' });
      loadAll();
    })
  );
}

$('#savePrefs').addEventListener('click', async () => {
  const body = {};
  for (const key of ['target_buffer_months', 'concentration_warn_pct', 'signal_lookback_days']) {
    body[key] = $(`#pref_${key}`).value;
  }
  await api('/api/prefs', { method: 'POST', body });
  banner('Preferences saved.');
  loadAll();
});

// --- Boot ------------------------------------------------------------------

async function loadAll() {
  try {
    const cfg = await api('/api/config');
    $('#envLine').textContent =
      `Plaid: ${cfg.plaidConfigured ? cfg.plaidEnv : 'not configured'} · ` +
      `SEC: ${cfg.secConfigured ? 'ready' : 'set SEC_USER_AGENT'} · ` +
      `Analysts: ${cfg.analystsConfigured ? 'ready' : 'no API key'}`;
    if (!cfg.plaidConfigured) {
      banner('Add PLAID_CLIENT_ID and PLAID_SECRET to .env, then restart the server.', true);
    }

    const o = await api('/api/overview');
    renderNetWorth(o.netWorth);
    renderRunway(o.runway);
    renderDiversification(o.diversification);
    renderPositions(o.positions);
    renderIncome(o.income);
    await Promise.all([loadFollows(), loadSignals(), loadPrefs()]);
  } catch (err) {
    banner(err.message, true);
  }
}

loadAll();
