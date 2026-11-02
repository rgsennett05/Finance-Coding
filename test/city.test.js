/**
 * Offline checks for the agent city: DCF math, SEC fact extraction, agent
 * ordering, the tool contract, and a full offline run.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { valuePerShare, runDcf, cagr } from '../city/tools/dcf.js';
import { annualSeries, extractFundamentals } from '../city/tools/fundamentals.js';
import { rsi, maxDrawdown } from '../city/tools/indicators.js';
import { Registry } from '../city/registry.js';
import { order, runCity } from '../city/run.js';
import { renderCity } from '../city/render.js';

const yearsAgo = (n) => new Date(Date.now() - n * 365.25 * 86400000).toISOString().slice(0, 10);

test('DCF with zero growth equals the perpetuity value', () => {
  // g0 = gT = 0, r = 10%: value is FCF / r regardless of horizon.
  const v = valuePerShare({ baseFcf: 100, g0: 0, years: 5, r: 0.1, gT: 0, cash: 0, debt: 0, shares: 10 });
  assert.ok(Math.abs(v.perShare - 100) < 1e-9);
});

test('DCF adds cash, subtracts debt, and refuses r <= g', () => {
  const base = { baseFcf: 100, g0: 0, years: 5, r: 0.1, gT: 0, shares: 10 };
  assert.ok(Math.abs(valuePerShare({ ...base, cash: 50, debt: 20 }).perShare - 103) < 1e-9);
  assert.equal(valuePerShare({ ...base, r: 0.02, gT: 0.03 }), null);
});

test('runDcf clamps growth and builds a 3x3 sensitivity grid', () => {
  const fund = {
    sharesOutstanding: 100,
    cash: 0, debt: 0,
    freeCashFlow: [
      { end: yearsAgo(4), value: 100 },
      { end: yearsAgo(1), value: 1000 }, // ~115% CAGR, should clamp to maxGrowth
    ],
  };
  const out = runDcf(fund, 50, { projectionYears: 5, discountRate: 0.09, terminalGrowth: 0.025, maxGrowth: 0.2, minGrowth: -0.05 });
  assert.equal(out.ok, true);
  assert.equal(out.assumptions.startingGrowth, 0.2);
  assert.equal(out.sensitivity.length, 9);
  assert.ok(cagr(fund.freeCashFlow) > 1);
  assert.equal(runDcf({ ...fund, freeCashFlow: [{ end: yearsAgo(1), value: -5 }] }, 50, out.assumptions).ok, false);
  assert.match(runDcf({ ...fund, freeCashFlow: [{ end: yearsAgo(3), value: 500 }] }, 50, out.assumptions).reason, /stale/);
});

test('annualSeries keeps only 10-K full-year values, latest restatement wins', () => {
  const facts = { facts: { 'us-gaap': { NetCashProvidedByUsedInOperatingActivities: { units: { USD: [
    { form: '10-K', start: '2022-01-01', end: '2022-12-31', val: 10, filed: '2023-02-01' },
    { form: '10-K', start: '2022-01-01', end: '2022-12-31', val: 11, filed: '2024-02-01' },
    { form: '10-Q', start: '2023-01-01', end: '2023-03-31', val: 99, filed: '2023-05-01' },
    { form: '10-K', start: '2023-10-01', end: '2023-12-31', val: 5, filed: '2024-02-01' },
  ] } }, PaymentsToAcquirePropertyPlantAndEquipment: { units: { USD: [
    { form: '10-K', start: '2022-01-01', end: '2022-12-31', val: 3, filed: '2023-02-01' },
  ] } } } } };
  assert.deepEqual(annualSeries(facts, ['NetCashProvidedByUsedInOperatingActivities']).rows, [{ end: '2022-12-31', value: 11 }]);
  assert.deepEqual(extractFundamentals(facts).freeCashFlow, [{ end: '2022-12-31', value: 8 }]);
});

test('capex tags are merged across a mid-history tag switch; shares fall back', () => {
  const k = (end, val) => ({ form: '10-K', start: `${end.slice(0, 4)}-01-01`, end, val, filed: `${Number(end.slice(0, 4)) + 1}-02-01` });
  const facts = { facts: { dei: {}, 'us-gaap': {
    NetCashProvidedByUsedInOperatingActivities: { units: { USD: [k('2011-12-31', 10), k('2024-12-31', 100)] } },
    PaymentsToAcquirePropertyPlantAndEquipment: { units: { USD: [k('2011-12-31', 2)] } },
    PaymentsToAcquireProductiveAssets: { units: { USD: [k('2024-12-31', 30)] } },
    WeightedAverageNumberOfDilutedSharesOutstanding: { units: { shares: [{ end: '2024-12-31', val: 5, filed: '2025-02-01' }] } },
  } } };
  const f = extractFundamentals(facts);
  assert.deepEqual(f.freeCashFlow, [{ end: '2011-12-31', value: 8 }, { end: '2024-12-31', value: 70 }]);
  assert.equal(f.sharesOutstanding, 5);
});

test('indicators: RSI of a rising series is 100, drawdown measured from peak', () => {
  assert.equal(rsi(Array.from({ length: 30 }, (_, i) => i + 1)), 100);
  assert.ok(Math.abs(maxDrawdown([100, 120, 90, 130]) - -0.25) < 1e-12);
});

test('agents run in dependency order and cycles are rejected', () => {
  const a = (id, needs = []) => ({ id, needs });
  assert.deepEqual(order([a('c', ['b']), a('b', ['a']), a('a')]).map((x) => x.id), ['a', 'b', 'c']);
  assert.throws(() => order([a('x', ['y']), a('y', ['x'])]), /cycle/);
});

test('registry rejects tools without run() and reports unknown names', async () => {
  const r = new Registry();
  assert.throws(() => r.add({ name: 'nope' }));
  r.add({ name: 'echo', description: '', run: (x) => x });
  assert.equal(await r.use('echo', 7), 7);
  assert.throws(() => r.get('missing'), /No tool named/);
});

test('a full offline shift produces picks and a renderable map', async () => {
  const state = await runCity({ offline: true, log: () => {} });
  assert.ok(state.agents.every((a) => a.status !== 'failed'), JSON.stringify(state.agents));
  assert.equal(state.board.mayor.picks.length, 3);
  assert.equal(state.agents.find((a) => a.id === 'research').status, 'closed');
  assert.match(renderCity(state), /Tonight's picks/);
});
