import { createClient, getUser } from "@/lib/supabase-server";
import { redirect } from "next/navigation";
import { CEODashboard } from "@/components/dashboard/ceo-dashboard";
import { HOSDashboard } from "@/components/dashboard/hos-dashboard";
import { TeamLeadDashboard } from "@/components/dashboard/team-lead-dashboard";
import { RepDashboard } from "@/components/dashboard/rep-dashboard";
import { CSMDashboard } from "@/components/dashboard/csm-dashboard";

export default async function DashboardPage() {
  const authUser = await getUser();
  if (!authUser) redirect("/login");

  const supabase = createClient();
  const { data: user } = await supabase
    .from("users")
    .select("id, role")
    .eq("id", authUser.id)
    .single();

  const role = user?.role ?? "rep";
  const userId = user?.id ?? authUser.id;

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
