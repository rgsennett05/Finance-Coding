import { Configuration, PlaidApi, PlaidEnvironments } from 'plaid';
import { config, requirePlaid } from '../config.js';

let cached = null;

export function plaid() {
  if (cached) return cached;
  requirePlaid();

  const basePath = PlaidEnvironments[config.plaid.env];
  if (!basePath) {
    throw new Error(
      `Unknown PLAID_ENV "${config.plaid.env}". Use one of: ${Object.keys(PlaidEnvironments).join(', ')}`
    );
  }

  cached = new PlaidApi(
    new Configuration({
      basePath,
      baseOptions: {
        headers: {
          'PLAID-CLIENT-ID': config.plaid.clientId,
          'PLAID-SECRET': config.plaid.secret,
        },
      },
    })
  );
  return cached;
}

/**
 * Plaid errors arrive as axios errors with the useful part buried in
 * response.data. Surface that instead of "Request failed with status code 400".
 */
export function plaidError(err) {
  const d = err?.response?.data;
  if (!d) return err;
  const e = new Error(`${d.error_code || 'PLAID_ERROR'}: ${d.error_message || 'unknown'}`);
  e.plaid = d;
  e.displayMessage = d.display_message;
  return e;
}
