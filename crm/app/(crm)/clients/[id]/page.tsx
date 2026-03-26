import { createClient } from "@/lib/supabase-server";
import { redirect } from "next/navigation";
import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { ClientProfile } from "@/components/clients/client-profile";
import type { Client } from "@/types/crm";

interface ClientPageProps {
  params: { id: string };
}

export default async function ClientPage({ params }: ClientPageProps) {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) redirect("/login");

  const { data: client, error } = await supabase
    .from("clients")
    .select(`
      *,
      prospect:prospect_id(id, company_name, domain, industry, city),
      closing_rep:closing_rep_id(id, name, email, role),
      csm_rep:csm_rep_id(id, name, email, role)
    `)
    .eq("id", params.id)
    .single();

  if (error || !client) notFound();

  return (
    <div className="max-w-4xl mx-auto p-4">
      <div className="mb-4">
        <Link
          href="/clients"
          className="flex items-center gap-1.5 text-sm text-text-dim hover:text-text-secondary transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Clients
        </Link>
      </div>

      <div className="mb-4">
        <h1 className="text-xl font-bold text-text-primary">
          {client.prospect?.company_name ?? "Client"}
        </h1>
        <p className="text-sm text-text-secondary">
          Client since {new Date(client.close_date).toLocaleDateString()}
        </p>
      </div>

      <ClientProfile client={client as Client} />
    </div>
  );
}
