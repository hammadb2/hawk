import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase-server";
import { Sidebar } from "@/components/layout/sidebar";
import { TopBar } from "@/components/layout/topbar";
import { MobileNav } from "@/components/layout/mobile-nav";
import { Providers } from "@/components/layout/providers";
import type { CRMUser } from "@/types/crm";

export default async function CRMLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = createClient();

  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    redirect("/login");
  }

  // Load user profile
  const { data: userProfile } = await supabase
    .from("users")
    .select("*, team_lead:team_lead_id(id, name, email, role)")
    .eq("id", session.user.id)
    .single();

  if (!userProfile) {
    // User authenticated but no profile — might be first time
    redirect("/onboarding");
  }

  return (
    <Providers initialUser={userProfile as CRMUser}>
      <div className="flex h-screen overflow-hidden" style={{ background: "#07060C" }}>
        {/* Desktop sidebar */}
        <div className="hidden lg:flex">
          <Sidebar />
        </div>

        {/* Main content area */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <TopBar />
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
        </div>
      </div>

      {/* Mobile bottom nav */}
      <MobileNav />
    </Providers>
  );
}
