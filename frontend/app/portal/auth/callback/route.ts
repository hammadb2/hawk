import { NextResponse } from "next/server";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { getPublicSiteUrlFromRequest, safePortalNextPath } from "@/lib/site-url";
import { getHawkCrmSupabaseAuthStorageKey } from "@/lib/supabase/auth-storage";

export async function GET(request: Request) {
  const reqUrl = new URL(request.url);
  const searchParams = reqUrl.searchParams;
  const origin = getPublicSiteUrlFromRequest(request.url);

  const oauthError = searchParams.get("error");
  if (oauthError) {
    const desc = searchParams.get("error_description") ?? "";
    const login = new URL(`${origin}/portal/login`);
    login.searchParams.set("error", "auth");
    if (desc) login.searchParams.set("message", desc.slice(0, 300));
    return NextResponse.redirect(login);
  }

  const code = searchParams.get("code");
  const next = safePortalNextPath(searchParams.get("next"), "/portal");

  if (!code) {
    return NextResponse.redirect(`${origin}/portal/login?error=auth&reason=missing_code`);
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
    const login = new URL(`${origin}/portal/login`);
    login.searchParams.set("error", "auth");
    login.searchParams.set("message", error.message.slice(0, 200));
    return NextResponse.redirect(login);
  }

  return NextResponse.redirect(new URL(next, origin).toString());
}
