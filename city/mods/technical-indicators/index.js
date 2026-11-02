/**
 * Example mod: wraps the open-source `technicalindicators` library
 * (https://github.com/anandanand84/technicalindicators) as a city tool.
 *
 * Pattern for ANY GitHub library:
 *   1. install it         npm install technicalindicators
 *   2. import it here     (dynamic import, so a missing package = skipped mod, not a crash)
 *   3. adapt its API to   { name, description, run(input) }
 *   4. register           registry.add(tool, { source: 'mod:...' })
 *   5. enable it          add the folder name to "mods" in city.config.json
 *
 * Because it registers under the existing name "indicators", it upgrades the
 * built-in tool in place: every agent that uses "indicators" gets MACD and
 * Bollinger Bands without changing a line of agent code.
 */
import { computeAll } from '../../tools/indicators.js';

export default {
  name: 'technical-indicators',
  description: 'Adds MACD and Bollinger Bands via the technicalindicators npm package.',
  async register(registry) {
    const ti = await import('technicalindicators').catch(() => {
      throw new Error('package not installed — run: npm install technicalindicators');
    });
    const lib = ti.default ?? ti;

    registry.add(
      {
        name: 'indicators',
        description: 'Built-in indicators plus MACD(12,26,9) and Bollinger(20,2) from technicalindicators.',
        async run({ closes }) {
          const base = computeAll(closes);
          const macd = lib.MACD.calculate({
            values: closes, fastPeriod: 12, slowPeriod: 26, signalPeriod: 9,
            SimpleMAOscillator: false, SimpleMASignal: false,
          }).at(-1);
          const bb = lib.BollingerBands.calculate({ values: closes, period: 20, stdDev: 2 }).at(-1);
          return {
            ...base,
            macd: macd ? { line: macd.MACD, signal: macd.signal, histogram: macd.histogram } : null,
            bollinger: bb ? { upper: bb.upper, middle: bb.middle, lower: bb.lower, pctB: (closes.at(-1) - bb.lower) / (bb.upper - bb.lower) } : null,
          };
        },
      },
      { source: 'mod:technical-indicators' }
    );
    return 'replaced "indicators" with the library-backed version';
  },
};
