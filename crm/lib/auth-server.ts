/**
 * Server-only auth helpers — safe to import in Server Components and Route Handlers.
 * Do NOT import this from any "use client" component.
 */
import { createClient } from "@/lib/supabase-server";
import type { CRMUser } from "@/types/crm";

export async function getServerUser(): Promise<CRMUser | null> {
  const supabase = createClient();
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();

  if (authError || !user) return null;

  const { data, error } = await supabase
    .from("users")
    .select("*, team_lead:team_lead_id(id, name, email, role)")
    .eq("id", user.id)
    .single();

  if (error || !data) {
    console.error("getServerUser profile error:", error?.message);
    return null;
  }

  return data as CRMUser;
}
