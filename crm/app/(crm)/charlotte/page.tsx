import { createClient } from "@/lib/supabase-server";
import { redirect } from "next/navigation";
import { CharlotteModule } from "@/components/charlotte/charlotte-module";

export default async function CharlottePage() {
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

  if (!user || !["ceo", "hos"].includes(user.role)) {
    redirect("/dashboard");
  }

  return <CharlotteModule />;
}
