import { createClient } from "@/lib/supabase-server";
import { redirect } from "next/navigation";
import { MyEarnings } from "@/components/earnings/my-earnings";

export default async function EarningsPage() {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const { data: user } = await supabase
    .from("users")
    .select("role")
    .eq("id", session.user.id)
    .single();

  if (!user || !["rep", "team_lead"].includes(user.role)) {
    redirect("/dashboard");
  }

  return <MyEarnings />;
}
