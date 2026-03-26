import { createClient } from "@/lib/supabase-server";
import { redirect } from "next/navigation";
import { notFound } from "next/navigation";
import { ProspectProfilePage } from "@/components/prospect/prospect-profile-page";
import type { Prospect } from "@/types/crm";

interface ProspectPageProps {
  params: { id: string };
}

export default async function ProspectPage({ params }: ProspectPageProps) {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const { data: prospect, error } = await supabase
    .from("prospects")
    .select("*, assigned_rep:assigned_rep_id(id, name, email, role)")
    .eq("id", params.id)
    .single();

  if (error || !prospect) notFound();

  return <ProspectProfilePage initialProspect={prospect as Prospect} />;
}
