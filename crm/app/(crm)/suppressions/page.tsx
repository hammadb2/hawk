import { createClient } from "@/lib/supabase-server";
import { redirect } from "next/navigation";
import { SuppressionsConsole } from "@/components/suppressions/suppressions-console";

export default async function SuppressionsPage() {
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

  if (!user || (user.role !== "ceo" && user.role !== "hos")) {
    redirect("/dashboard");
  }

  return <SuppressionsConsole />;
}
