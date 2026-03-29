import { createClient } from "@/lib/supabase-server";
import { redirect } from "next/navigation";
import { TicketConsole } from "@/components/tickets/ticket-console";

export default async function TicketsPage() {
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

  return <TicketConsole />;
}
