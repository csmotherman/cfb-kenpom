export const EARLY_BETA_END_LABEL = "October 15, 2026";

// Early Beta remains active through October 15 in the product's Eastern-time
// launch calendar. Detroit is on EDT at the cutoff, so midnight on October 16
// is 04:00 UTC.
const EARLY_BETA_EXPIRES_AT = Date.parse("2026-10-16T04:00:00.000Z");

export function isEarlyBetaActive(now: Date = new Date()) {
  return now.getTime() < EARLY_BETA_EXPIRES_AT;
}
