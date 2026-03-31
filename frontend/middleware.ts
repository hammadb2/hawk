import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getHawkCrmSupabaseAuthStorageKey } from "@/lib/supabase/auth-storage";

const AUTH_COOKIE = "hawk_auth";

function crmCookieOptions(url: string) {
  return { name: getHawkCrmSupabaseAuthStorageKey(url) };
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (pathname.startsWith("/portal")) {
    if (!url || !key) {
      return NextResponse.next();
    }

    let supabaseResponse = NextResponse.next({ request });
    const supabase = createServerClient(url, key, {
      cookieOptions: crmCookieOptions(url),
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => supabaseResponse.cookies.set(name, value, options));
        },
      },
    });

    // Magic-link return + OAuth: must stay public (Supabase redirects to /portal/auth/callback)
    const isPublic = pathname.startsWith("/portal/login") || pathname.startsWith("/portal/auth");

    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (user && pathname.startsWith("/portal/login")) {
      const next = request.nextUrl.searchParams.get("next") || "/portal";
      const safe = next.startsWith("/") && !next.startsWith("//") && !next.includes("://") ? next : "/portal";
      return NextResponse.redirect(new URL(safe, request.url));
    }

    if (!isPublic && !user) {
      const login = new URL("/portal/login", request.url);
      login.searchParams.set("next", pathname);
      return NextResponse.redirect(login);
    }

    if (!isPublic && user) {
      const { data: cpp } = await supabase.from("client_portal_profiles").select("id").eq("user_id", user.id).maybeSingle();
      if (!cpp) {
        return NextResponse.redirect(new URL("/portal/login?error=not_linked", request.url));
      }
    }

    return supabaseResponse;
  }

  if (pathname.startsWith("/crm")) {
    if (!url || !key) {
      return NextResponse.next();
    }

    let supabaseResponse = NextResponse.next({ request });

    const supabase = createServerClient(url, key, {
      cookieOptions: crmCookieOptions(url),
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => supabaseResponse.cookies.set(name, value, options));
        },
      },
    });

    const isPublic = pathname.startsWith("/crm/login") || pathname.startsWith("/crm/auth"); // includes /crm/auth/callback

    const {
      data: { user },
    } = await supabase.auth.getUser();

    if (user && pathname.startsWith("/crm/login")) {
      const next = request.nextUrl.searchParams.get("next") || "/crm/dashboard";
      const safe = next.startsWith("/") && !next.startsWith("//") && !next.includes("://") ? next : "/crm/dashboard";
      return NextResponse.redirect(new URL(safe, request.url));
    }

    if (!isPublic && !user) {
      const login = new URL("/crm/login", request.url);
      login.searchParams.set("next", pathname);
      return NextResponse.redirect(login);
    }

    if (user && !isPublic) {
      const { data: prof } = await supabase.from("profiles").select("id").eq("id", user.id).maybeSingle();
      if (!prof?.id) {
        const { data: cpp } = await supabase.from("client_portal_profiles").select("id").eq("user_id", user.id).maybeSingle();
        if (cpp) {
          return NextResponse.redirect(new URL("/portal", request.url));
        }
      }
    }

    if (user && (pathname === "/crm/pipeline" || pathname.startsWith("/crm/pipeline/"))) {
      const { data: prof, error: pe } = await supabase
        .from("profiles")
        .select("role,onboarding_completed_at")
        .eq("id", user.id)
        .maybeSingle();
      if (
        !pe &&
        prof &&
        ["sales_rep", "team_lead"].includes(prof.role as string) &&
        !(prof as { onboarding_completed_at?: string | null }).onboarding_completed_at
      ) {
        return NextResponse.redirect(new URL("/crm/onboarding", request.url));
      }
    }

    return supabaseResponse;
  }

  if (pathname.startsWith("/dashboard") || pathname.startsWith("/onboarding")) {
    const auth = request.cookies.get(AUTH_COOKIE)?.value;
    if (!auth) {
      const login = new URL("/login", request.url);
      login.searchParams.set("next", pathname);
      return NextResponse.redirect(login);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/crm", "/crm/:path*", "/portal", "/portal/:path*", "/dashboard/:path*", "/onboarding"],
};
