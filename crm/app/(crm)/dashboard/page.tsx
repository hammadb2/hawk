import { createClient } from "@/lib/supabase-server";
import { redirect } from "next/navigation";
import { CEODashboard } from "@/components/dashboard/ceo-dashboard";
import { HOSDashboard } from "@/components/dashboard/hos-dashboard";
import { TeamLeadDashboard } from "@/components/dashboard/team-lead-dashboard";
import { RepDashboard } from "@/components/dashboard/rep-dashboard";
import { CSMDashboard } from "@/components/dashboard/csm-dashboard";

export default async function DashboardPage() {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const { data: user } = await supabase
    .from("users")
    .select("id, role")
    .eq("id", session.user.id)
    .single();

  const role = user?.role ?? "rep";
  const userId = user?.id ?? session.user.id;

  return (
    <>
      {role === "ceo"       && <CEODashboard />}
      {role === "hos"       && <HOSDashboard />}
      {role === "team_lead" && <TeamLeadDashboard />}
      {role === "rep"       && <RepDashboard />}
      {role === "csm"       && <CSMDashboard csmId={userId} />}
    </>
  );
}
