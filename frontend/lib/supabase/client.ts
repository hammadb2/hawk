import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import { getHawkCrmSupabaseAuthStorageKey } from "./auth-storage";

/** Public Supabase demo credentials — only used during SSR/build when env is unset (prerender). */
const SSR_PLACEHOLDER_URL = "https://placeholder.supabase.co";
const SSR_PLACEHOLDER_ANON =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0";

/** Browser-only singleton — avoids parallel clients stealing the auth storage lock. */
let browserSingleton: SupabaseClient | null = null;

function resolveUrlAndKey(): { url: string; key: string } {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (url && key) return { url, key };
  if (typeof window === "undefined") {
    return { url: SSR_PLACEHOLDER_URL, key: SSR_PLACEHOLDER_ANON };
  }
  throw new Error("Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY");
}

export function createClient(): SupabaseClient {
  const { url, key } = resolveUrlAndKey();

  if (typeof window !== "undefined" && browserSingleton) {
    return browserSingleton;
  }

  const storageKey = getHawkCrmSupabaseAuthStorageKey(url);

  const client = createBrowserClient(url, key, {
    isSingleton: true,
    cookieOptions: { name: storageKey },
    auth: {
      persistSession: true,
      storageKey,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });

  if (typeof window !== "undefined") {
    browserSingleton = client;
  }

  return client;
}
