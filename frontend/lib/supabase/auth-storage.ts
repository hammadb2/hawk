/**
 * Namespaced storage key so Hawk CRM does not fight the default
 * `sb-<ref>-auth-token` lock if another app shares the same Supabase project
 * or multiple clients are created. Must match browser + server + middleware.
 */
export function getHawkCrmSupabaseAuthStorageKey(supabaseUrl: string): string {
  try {
    const host = new URL(supabaseUrl).hostname;
    const ref = host.split(".")[0];
    return `hawk-crm-sb-${ref}-auth-token`;
  } catch {
    return "hawk-crm-sb-auth-token";
  }
}
