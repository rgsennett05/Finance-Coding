import { getSubmissions, listFilingFiles, secFetch, xmlBlocks, xmlText, xmlNumber } from './sec.js';

/**
 * Form 4 transaction codes. Only P and S are open-market decisions - the rest
 * are grants, option mechanics or tax withholding, which say little about
 * conviction and would otherwise drown out the real signal.
 */
const CODE_MEANING = {
  P: { action: 'buy', label: 'Open-market purchase', openMarket: true },
  S: { action: 'sell', label: 'Open-market sale', openMarket: true },
  A: { action: 'grant', label: 'Grant / award', openMarket: false },
  M: { action: 'exercise', label: 'Option exercise', openMarket: false },
  F: { action: 'tax', label: 'Shares withheld for tax', openMarket: false },
  G: { action: 'gift', label: 'Gift', openMarket: false },
  C: { action: 'convert', label: 'Conversion', openMarket: false },
  D: { action: 'dispose', label: 'Disposition to issuer', openMarket: false },
  X: { action: 'exercise', label: 'In-the-money option exercise', openMarket: false },
};

export function parseForm4(xml, sourceUrl, filingDate) {
  const issuerBlock = xmlBlocks(xml, 'issuer')[0] || '';
  const ticker = xmlText(issuerBlock, 'issuerTradingSymbol');
  const issuerName = xmlText(issuerBlock, 'issuerName');

  const ownerBlock = xmlBlocks(xml, 'reportingOwner')[0] || '';
  const ownerName = xmlText(ownerBlock, 'rptOwnerName');
  const ownerCik = xmlText(ownerBlock, 'rptOwnerCik');
  const officerTitle = xmlText(ownerBlock, 'officerTitle');
  const isDirector = xmlText(ownerBlock, 'isDirector') === '1';
  const role = officerTitle || (isDirector ? 'Director' : '10% owner / insider');

  const rows = [];
  for (const table of ['nonDerivativeTransaction', 'derivativeTransaction']) {
    for (const t of xmlBlocks(xml, table)) {
      const code = xmlText(t, 'transactionCode');
      if (!code) continue;
      const meaning = CODE_MEANING[code] || { action: code, label: code, openMarket: false };
      const shares = xmlNumber(t, 'transactionShares');
      const price = xmlNumber(t, 'transactionPricePerShare');
      const disposed = xmlText(t, 'transactionAcquiredDisposedCode') === 'D';

      rows.push({
        source: 'form4',
        actor: ownerCik,
        actorLabel: `${ownerName}${role ? ` (${role})` : ''}`,
        ticker,
        securityName: issuerName,
        action: meaning.action,
        actionLabel: meaning.label,
        openMarket: meaning.openMarket,
        direction: disposed ? 'out' : 'in',
        quantity: shares,
        price,
        value: shares != null && price != null ? Number((shares * price).toFixed(2)) : null,
        transactedAt: xmlText(t, 'transactionDate'),
        filedAt: filingDate,
        url: sourceUrl,
        derivative: table === 'derivativeTransaction',
      });
    }
  }
  return rows;
}

/**
 * Insider filings for one entity. A company CIK yields every insider trading
 * that stock; a person's CIK yields that individual's trades everywhere.
 */
export async function fetchForm4(cik, { limit = 15 } = {}) {
  const { entityName, filings } = await getSubmissions(cik, { forms: ['4', '4/A'], limit });
  const out = [];

  for (const filing of filings) {
    try {
      let url = filing.url;
      if (!url.endsWith('.xml')) {
        const files = await listFilingFiles(filing.folder);
        const xmlFile =
          files.find((f) => /^(wf-)?form4.*\.xml$/i.test(f.name)) ||
          files.find((f) => f.name.endsWith('.xml') && !/R\d+\.xml|FilingSummary/i.test(f.name));
        if (!xmlFile) continue;
        url = xmlFile.url;
      }
      const xml = await secFetch(url);
      out.push(...parseForm4(xml, filing.url, filing.filingDate));
    } catch {
      // One malformed filing must not sink the batch.
    }
  }

  return { entityName, trades: out };
}
