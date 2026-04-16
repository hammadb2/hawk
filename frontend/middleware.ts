import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { getHawkCrmSupabaseAuthStorageKey } from "@/lib/supabase/auth-storage";
import { safePortalNextPath } from "@/lib/site-url";

const AUTH_COOKIE = "hawk_auth";

function crmCookieOptions(url: string) {
  return { name: getHawkCrmSupabaseAuthStorageKey(url) };
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname === "/login") {
    if (request.nextUrl.searchParams.get("register") === "1") {
      return NextResponse.redirect(new URL("/#pricing", request.url));
    }
    return NextResponse.redirect(new URL("/portal/login", request.url));
  }
  if (pathname === "/forgot-password" || pathname === "/reset-password") {
    return NextResponse.redirect(new URL("/portal/login", request.url));
  }

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  // AI Onboarding Portal — allow access; guarded by its own auth inside the page
  if (pathname === "/onboarding" || pathname.startsWith("/onboarding/")) {
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

    const {
      data: { user },
    } = await supabase.auth.getUser();

    // Not logged in → send to CRM login with redirect back
    if (!user) {
      const login = new URL("/crm/login", request.url);
      login.searchParams.set("next", pathname);
      return NextResponse.redirect(login);
    }

    // CEO bypasses onboarding entirely → send to CRM
    const { data: onbProf } = await supabase
      .from("profiles")
      .select("role,onboarding_status")
      .eq("id", user.id)
      .maybeSingle();

    if (onbProf?.role === "ceo") {
      return NextResponse.redirect(new URL("/crm/dashboard", request.url));
    }

    // Already approved → send to CRM
    if (onbProf?.onboarding_status === "approved") {
      return NextResponse.redirect(new URL("/crm/dashboard", request.url));
    }

    // /onboarding/complete — only if pending_review or approved
    if (pathname === "/onboarding/complete" && onbProf?.onboarding_status !== "pending_review" && onbProf?.onboarding_status !== "approved") {
      return NextResponse.redirect(new URL("/onboarding", request.url));
    }

    return supabaseResponse;
  }

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
      // Account-first: rows are created by PortalGate + /api/portal/bootstrap — never block on client_portal_profiles in middleware.
      const { data: cppAtLogin } = await supabase
        .from("client_portal_profiles")
        .select("id")
        .eq("user_id", user.id)
        .maybeSingle();
      const nextParam = request.nextUrl.searchParams.get("next");
      const fallback = cppAtLogin ? "/portal" : "/portal/billing";
      const safe = safePortalNextPath(nextParam, fallback);
      return NextResponse.redirect(new URL(safe, request.url));
    }

    if (!isPublic && !user) {
      const login = new URL("/portal/login", request.url);
      login.searchParams.set("next", pathname);
      return NextResponse.redirect(login);
    }

    // Authenticated portal routes: do not enforce client_portal_profiles in middleware (bootstrap runs in PortalGate).

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
      const { data: loginProf } = await supabase
        .from("profiles")
        .select("role")
        .eq("id", user.id)
        .maybeSingle();
      if (loginProf?.role === "client") {
        return NextResponse.redirect(new URL("/portal", request.url));
      }
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
      const { data: prof } = await supabase
        .from("profiles")
        .select("id,role,onboarding_status")
        .eq("id", user.id)
        .maybeSingle();
      if (prof?.role === "client") {
        return NextResponse.redirect(new URL("/portal", request.url));
      }
      if (!prof?.id) {
        const { data: cpp } = await supabase.from("client_portal_profiles").select("id").eq("user_id", user.id).maybeSingle();
        if (cpp) {
          return NextResponse.redirect(new URL("/portal", request.url));
        }
      }

      // AI Onboarding enforcement — redirect to /onboarding if not approved (CEO bypasses)
      if (
        prof &&
        prof.role !== "ceo" &&
        prof.onboarding_status &&
        prof.onboarding_status !== "approved" &&
        !pathname.startsWith("/crm/login") &&
        !pathname.startsWith("/crm/auth") &&
        // Allow access to onboarding review pages for privileged users
        !pathname.startsWith("/crm/onboarding/review")
      ) {
        // Check if user is privileged (CEO/HoS) viewing review pages
        const isPrivileged = prof.role === "ceo" || prof.role === "hos";
        if (!isPrivileged) {
          return NextResponse.redirect(new URL("/onboarding", request.url));
        }
      }
    }

    return supabaseResponse;
  }

  if (pathname.startsWith("/dashboard")) {
    const auth = request.cookies.get(AUTH_COOKIE)?.value;
    if (!auth) {
      const login = new URL("/portal/login", request.url);
      login.searchParams.set("next", pathname);
      return NextResponse.redirect(login);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/login",
    "/forgot-password",
    "/reset-password",
    "/onboarding",
    "/onboarding/:path*",
    "/crm",
    "/crm/:path*",
    "/portal",
    "/portal/:path*",
    "/dashboard",
    "/dashboard/:path*",
  ],
};
