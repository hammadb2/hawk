"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ProspectProfile } from "@/components/crm/prospect/prospect-profile";
import { Button } from "@/components/ui/button";

export default function ProspectFullPage() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : "";

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="border-slate-200" asChild>
          <Link href="/crm/pipeline">← Pipeline</Link>
        </Button>
      </div>
      {id ? <ProspectProfile prospectId={id} variant="page" /> : <p className="text-slate-600">Invalid prospect</p>}
    </div>
  );
}
