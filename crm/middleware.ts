import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

/** Routes limited by CRM role (prefix match). Keeps deep links aligned with sidebar access. */
const ROLE_GUARDED_ROUTES: { prefix: string; roles: readonly string[] }[] = [
  { prefix: "/settings", roles: ["ceo"] },
  { prefix: "/tickets", roles: ["ceo", "hos"] },
  { prefix: "/charlotte", roles: ["ceo", "hos"] },
  { prefix: "/team", roles: ["ceo", "hos"] },
];

function pathnameMatchesRoute(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: { name: string; value: string; options?: Record<string, unknown> }[]) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options as Parameters<typeof supabaseResponse.cookies.set>[2])
          );
        },
      },
    }
  );

  // Use getUser() not getSession() — getUser() validates the JWT with the auth
  // server and refreshes an expired access token, ensuring cookies are always
  // fresh when the page renders. getSession() only reads from the cookie without
  // validating, so an expired token would reach the client un-refreshed.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;

  // Public routes that don't require auth
  const publicRoutes = ["/login", "/auth/callback"];
  const isPublicRoute = publicRoutes.some((route) => pathname.startsWith(route));

  const profileExemptPrefixes = ["/setup-required", "/onboarding"];
  const isProfileExempt = profileExemptPrefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));

  if (!user && !isPublicRoute) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.searchParams.set("redirected_from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (user && pathname === "/login") {
    const dashboardUrl = request.nextUrl.clone();
    dashboardUrl.pathname = "/dashboard";
    return NextResponse.redirect(dashboardUrl);
  }

  if (user && !isPublicRoute && !isProfileExempt) {
    const rule = ROLE_GUARDED_ROUTES.find((r) => pathnameMatchesRoute(pathname, r.prefix));
    if (rule) {
      const { data: profile } = await supabase.from("users").select("role").eq("id", user.id).maybeSingle();
      if (!profile?.role) {
        const setupUrl = request.nextUrl.clone();
        setupUrl.pathname = "/setup-required";
        return NextResponse.redirect(setupUrl);
      }
      if (!rule.roles.includes(profile.role)) {
        const dash = request.nextUrl.clone();
        dash.pathname = "/dashboard";
        return NextResponse.redirect(dash);
      }
    }
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
