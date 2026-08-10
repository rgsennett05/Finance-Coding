#!/usr/bin/env node
/**
 * Offline checks for the filing parsers. These run without network access, so
 * the XML handling can be verified independently of SEC reachability.
 *
 *   node --test test/
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { parseForm4 } from '../src/signals/form4.js';
import { parseInfoTable, diffQuarters } from '../src/signals/thirteenf.js';
import { renderSnapshot } from '../src/render.js';
import { demoSnapshot } from '../src/demo-data.js';

// A Form 4 in EDGAR's real shape: one open-market purchase, one tax-withholding
// disposal, and one derivative row.
const FORM4 = `<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerName>Apple Inc.</issuerName>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001214128</rptOwnerCik>
      <rptOwnerName>COOK TIMOTHY D</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector>
      <isOfficer>1</isOfficer>
      <officerTitle>Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-05-01</value></transactionDate>
      <transactionCoding><transactionFormType>4</transactionFormType><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>187.25</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-05-02</value></transactionDate>
      <transactionCoding><transactionCode>F</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>250</value></transactionShares>
        <transactionPricePerShare><value>188.10</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <derivativeTable>
    <derivativeTransaction>
      <securityTitle><value>Restricted Stock Unit</value></securityTitle>
      <transactionDate><value>2026-05-03</value></transactionDate>
      <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><value>0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </derivativeTransaction>
  </derivativeTable>
</ownershipDocument>`;

test('parseForm4 extracts issuer, owner and every transaction row', () => {
  const rows = parseForm4(FORM4, 'https://example.test/f4', '2026-05-04');
  assert.equal(rows.length, 3);

  const buy = rows[0];
  assert.equal(buy.ticker, 'AAPL');
  assert.equal(buy.actorLabel, 'COOK TIMOTHY D (Chief Executive Officer)');
  assert.equal(buy.action, 'buy');
  assert.equal(buy.openMarket, true);
  assert.equal(buy.direction, 'in');
  assert.equal(buy.quantity, 1000);
  assert.equal(buy.value, 187250);
  assert.equal(buy.transactedAt, '2026-05-01');
  assert.equal(buy.filedAt, '2026-05-04');
});

test('parseForm4 separates real trades from grants and tax withholding', () => {
  const rows = parseForm4(FORM4, 'https://example.test/f4', '2026-05-04');
  assert.deepEqual(
    rows.map((r) => [r.action, r.openMarket]),
    [
      ['buy', true],
      ['tax', false],
      ['exercise', false],
    ]
  );
  assert.equal(rows[2].derivative, true);
});

test('parseForm4 handles namespaced tags', () => {
  const ns = FORM4.replace(/<issuerTradingSymbol>/, '<ns1:issuerTradingSymbol>')
    .replace(/<\/issuerTradingSymbol>/, '</ns1:issuerTradingSymbol>');
  assert.equal(parseForm4(ns, 'u', '2026-05-04')[0].ticker, 'AAPL');
});

// ---------------------------------------------------------------------------

const infoTable = (rows) => `<?xml version="1.0"?>
<informationTable>
${rows
  .map(
    (r) => `<infoTable>
  <nameOfIssuer>${r.name}</nameOfIssuer>
  <titleOfClass>COM</titleOfClass>
  <cusip>${r.cusip}</cusip>
  <value>${r.value}</value>
  <shrsOrPrnAmt><sshPrnamt>${r.shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
</infoTable>`
  )
  .join('\n')}
</informationTable>`;

test('parseInfoTable reads values as whole dollars after the 2023 cutover', () => {
  const xml = infoTable([{ name: 'APPLE INC', cusip: '037833100', value: 1000000, shares: 5000 }]);
  const [row] = parseInfoTable(xml, '2026-03-31');
  assert.equal(row.value, 1000000);
  assert.equal(row.shares, 5000);
  assert.equal(row.issuer, 'APPLE INC');
});

test('parseInfoTable scales pre-2023 filings reported in thousands', () => {
  const xml = infoTable([{ name: 'APPLE INC', cusip: '037833100', value: 1000, shares: 5000 }]);
  const [row] = parseInfoTable(xml, '2022-09-30');
  assert.equal(row.value, 1000000);
});

test('parseInfoTable rolls up duplicate CUSIPs across accounts', () => {
  const xml = infoTable([
    { name: 'APPLE INC', cusip: '037833100', value: 600000, shares: 3000 },
    { name: 'APPLE INC', cusip: '037833100', value: 400000, shares: 2000 },
  ]);
  const rows = parseInfoTable(xml, '2026-03-31');
  assert.equal(rows.length, 1);
  assert.equal(rows[0].value, 1000000);
  assert.equal(rows[0].shares, 5000);
});

test('diffQuarters classifies new, increase, reduce and exit', () => {
  const previous = {
    totalValue: 3000,
    holdings: [
      { cusip: 'A', issuer: 'AAA', value: 1000, shares: 100 },
      { cusip: 'B', issuer: 'BBB', value: 1000, shares: 100 },
      { cusip: 'C', issuer: 'CCC', value: 1000, shares: 100 },
    ],
  };
  const current = {
    totalValue: 3000,
    holdings: [
      { cusip: 'A', issuer: 'AAA', value: 1500, shares: 150 },
      { cusip: 'B', issuer: 'BBB', value: 500, shares: 50 },
      { cusip: 'D', issuer: 'DDD', value: 1000, shares: 100 },
    ],
  };

  const moves = diffQuarters(current, previous);
  const byIssuer = Object.fromEntries(moves.map((m) => [m.issuer, m]));

  assert.equal(byIssuer.DDD.action, 'new');
  assert.equal(byIssuer.AAA.action, 'increase');
  assert.equal(byIssuer.AAA.sharesDelta, 50);
  assert.equal(byIssuer.BBB.action, 'reduce');
  assert.equal(byIssuer.BBB.sharesDelta, -50);
  assert.equal(byIssuer.CCC.action, 'exit');
  assert.equal(byIssuer.CCC.pctChange, -100);
});

// ---------------------------------------------------------------------------

test('renderSnapshot produces a self-contained page with no external requests', () => {
  const html = renderSnapshot(demoSnapshot(), { demo: true });
  assert.match(html, /<title>/);
  assert.doesNotMatch(html, /<!doctype|<html|<head>|<body>/i);
  // The Artifact CSP blocks every external host.
  assert.doesNotMatch(html, /src="https?:|href="https?:|@import|url\(https?:/);
  assert.match(html, /Example data/);
});

test('renderSnapshot masks dollar amounts under --redact but keeps ratios', () => {
  const snap = demoSnapshot();
  const html = renderSnapshot(snap, { redact: true });

  assert.match(html, /•••/);
  assert.match(html, /Amounts hidden/);
  // Percentages survive redaction; the formatted net-worth figure does not.
  assert.match(html, new RegExp(`${snap.netWorth.bankPct}%`));
  const netWorthFormatted = snap.netWorth.netWorth.toLocaleString('en-US', {
    style: 'currency', currency: 'USD', maximumFractionDigits: 0,
  });
  assert.ok(!html.includes(netWorthFormatted), 'redacted page must not contain the net worth figure');
});

test('renderSnapshot defines every theme token on bare :root', () => {
  const html = renderSnapshot(demoSnapshot(), {});
  const bareRoot = html.match(/:root\s*\{([\s\S]*?)\}/)[1];
  for (const token of ['--ground', '--surface', '--ink', '--line', '--accent', '--pos', '--neg', '--warn']) {
    assert.ok(bareRoot.includes(token), `${token} must be defined on bare :root`);
  }
  assert.match(html, /body\s*\{[^}]*background:\s*var\(--ground\)/);
});
