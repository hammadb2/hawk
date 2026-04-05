import { NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { getPublicSiteUrlFromRequest } from "@/lib/site-url";
import { getHawkCrmSupabaseAuthStorageKey } from "@/lib/supabase/auth-storage";

function safeInternalNextPath(raw: string | null, fallback = "/crm/dashboard"): string {
  if (!raw) return fallback;
  try {
    const p = decodeURIComponent(raw);
    if (!p.startsWith("/") || p.startsWith("//") || p.includes("://")) return fallback;
    return p;
  } catch {
    return fallback;
  }
}

export async function GET(request: Request) {
  const reqUrl = new URL(request.url);
  const searchParams = reqUrl.searchParams;
  const origin = getPublicSiteUrlFromRequest(request.url);

  const oauthError = searchParams.get("error");
  if (oauthError) {
    const desc = searchParams.get("error_description") ?? "";
    const login = new URL(`${origin}/crm/login`);
    login.searchParams.set("error", "auth");
    if (desc) login.searchParams.set("message", desc.slice(0, 300));
    return NextResponse.redirect(login);
  }

  const code = searchParams.get("code");
  const next = safeInternalNextPath(searchParams.get("next"), "/crm/dashboard");

  if (!code) {
    return NextResponse.redirect(`${origin}/crm/login?error=auth&reason=missing_code`);
  }

  const cookieStore = await cookies();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;
  const supabase = createServerClient(url, key, {
    cookieOptions: { name: getHawkCrmSupabaseAuthStorageKey(url) },
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
      },
    },
  });

  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    const login = new URL(`${origin}/crm/login`);
    login.searchParams.set("error", "auth");
    login.searchParams.set("message", error.message.slice(0, 200));
    return NextResponse.redirect(login);
  }

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (user?.id) {
    const { data: profile } = await supabase.from("profiles").select("role").eq("id", user.id).maybeSingle();
    if (profile?.role === "client") {
      return NextResponse.redirect(new URL("/portal", origin).toString());
    }
  }

  return NextResponse.redirect(new URL(next, origin).toString());
}
