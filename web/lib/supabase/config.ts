// The project URL and publishable key are intentionally safe to ship to the browser.
// Environment variables can override them later without changing application code.
export const supabaseUrl =
  process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://wmlzqmtsxqqxuiekmrqm.supabase.co";

export const supabasePublishableKey =
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??
  "sb_publishable_fidXXjZJy_bPbZ8sywabRA_W0pRQ1GK";
