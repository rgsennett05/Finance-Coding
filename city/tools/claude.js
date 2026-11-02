/**
 * claude — asks Claude for a written research note.
 *
 * Optional: without ANTHROPIC_API_KEY the tool reports itself unavailable and
 * the Research Library agent simply closes for the night.
 *
 * Uses the official SDK (github.com/anthropics/anthropic-sdk-typescript) —
 * itself an example of pulling a framework from GitHub via npm.
 */
import Anthropic from '@anthropic-ai/sdk';

const MODEL = process.env.CITY_CLAUDE_MODEL || 'claude-opus-5-5';

export default {
  name: 'claude',
  description: 'Writes an analyst memo from the numbers the other agents produced (needs ANTHROPIC_API_KEY).',
  async run({ system, prompt }, ctx = {}) {
    if (ctx.offline || !process.env.ANTHROPIC_API_KEY) {
      return { available: false, reason: ctx.offline ? 'offline mode' : 'ANTHROPIC_API_KEY not set' };
    }
    const client = new Anthropic();
    const response = await client.beta.messages.create({
      model: MODEL,
      max_tokens: 16000,
      output_config: { effort: 'medium' },
      // If a safety classifier declines, the API retries on a fallback model.
      betas: ['server-side-fallback-2026-07-01'],
      fallbacks: 'default',
      system,
      messages: [{ role: 'user', content: prompt }],
    });
    if (response.stop_reason === 'refusal') {
      return { available: true, text: null, reason: `declined (${response.stop_details?.category ?? 'unspecified'})` };
    }
    const text = response.content.filter((b) => b.type === 'text').map((b) => b.text).join('\n').trim();
    return { available: true, model: response.model, text };
  },
};
