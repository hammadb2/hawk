import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const AUTH_COOKIE = "hawk_auth";

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/crm")) {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    const isPublic = pathname.startsWith("/crm/login") || pathname.startsWith("/crm/auth");

    if (!url || !key) {
      return NextResponse.next();
    }

    let supabaseResponse = NextResponse.next({ request });

    const supabase = createServerClient(url, key, {
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

    if (!isPublic && !user) {
      const login = new URL("/crm/login", request.url);
      login.searchParams.set("next", pathname);
      return NextResponse.redirect(login);
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
  matcher: ["/crm", "/crm/:path*", "/dashboard/:path*", "/onboarding"],
};
