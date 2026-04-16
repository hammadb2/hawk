"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import type {
  TeamPersonalDetails,
  TeamBankDetails,
  TeamDocument,
  TeamDocumentType,
  PaymentMethod,
  Profile,
} from "@/lib/crm/types";

type ProfileTabsProps = {
  /** The profile_id (profiles.id) of the person being viewed. */
  targetProfileId: string;
  /** If true, the viewer can edit. Otherwise read-only. */
  canEdit: boolean;
  /** If true, the bank details tab is visible. */
  showBankDetails: boolean;
  /** If true, the viewer can delete documents (CEO only). */
  canDeleteDocs: boolean;
};

/* ------------------------------------------------------------------ */
/*  Details tab                                                       */
/* ------------------------------------------------------------------ */
function DetailsTab({ targetProfileId, canEdit }: { targetProfileId: string; canEdit: boolean }) {
  const supabase = useMemo(() => createClient(), []);
  const [details, setDetails] = useState<TeamPersonalDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    phone_number: "",
    whatsapp_number: "",
    address: "",
    country: "",
    date_of_birth: "",
    emergency_contact_name: "",
    emergency_contact_phone: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("team_personal_details")
      .select("*")
      .eq("profile_id", targetProfileId)
      .maybeSingle();
    if (error) {
      toast.error(error.message);
    }
    const row = data as TeamPersonalDetails | null;
    setDetails(row);
    if (row) {
      setForm({
        phone_number: row.phone_number ?? "",
        whatsapp_number: row.whatsapp_number ?? "",
        address: row.address ?? "",
        country: row.country ?? "",
        date_of_birth: row.date_of_birth ?? "",
        emergency_contact_name: row.emergency_contact_name ?? "",
        emergency_contact_phone: row.emergency_contact_phone ?? "",
      });
    }
    setLoading(false);
  }, [supabase, targetProfileId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    setSaving(true);
    const payload = {
      profile_id: targetProfileId,
      phone_number: form.phone_number || null,
      whatsapp_number: form.whatsapp_number || null,
      address: form.address || null,
      country: form.country || null,
      date_of_birth: form.date_of_birth || null,
      emergency_contact_name: form.emergency_contact_name || null,
      emergency_contact_phone: form.emergency_contact_phone || null,
      updated_at: new Date().toISOString(),
    };
    if (details) {
      const { error } = await supabase
        .from("team_personal_details")
        .update(payload)
        .eq("id", details.id);
      if (error) toast.error(error.message);
      else toast.success("Details saved");
    } else {
      const { error } = await supabase
        .from("team_personal_details")
        .insert(payload);
      if (error) toast.error(error.message);
      else toast.success("Details saved");
    }
    setSaving(false);
    void load();
  }

  if (loading) return <p className="py-6 text-center text-sm text-slate-500">Loading details…</p>;

  const fields: { key: keyof typeof form; label: string; type?: string }[] = [
    { key: "phone_number", label: "Phone number" },
    { key: "whatsapp_number", label: "WhatsApp" },
    { key: "address", label: "Address" },
    { key: "country", label: "Country" },
    { key: "date_of_birth", label: "Date of birth", type: "date" },
    { key: "emergency_contact_name", label: "Emergency contact name" },
    { key: "emergency_contact_phone", label: "Emergency contact phone" },
  ];

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => (
          <div key={f.key}>
            <Label className="text-slate-600">{f.label}</Label>
            <Input
              className="mt-1 border-slate-200 bg-slate-50"
              type={f.type ?? "text"}
              value={form[f.key]}
              disabled={!canEdit}
              onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
            />
          </div>
        ))}
      </div>
      {canEdit && (
        <Button className="bg-emerald-600" disabled={saving} onClick={() => void save()}>
          {saving ? "Saving…" : "Save details"}
        </Button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Documents tab                                                     */
/* ------------------------------------------------------------------ */
function DocumentsTab({
  targetProfileId,
  canEdit,
  canDeleteDocs,
}: {
  targetProfileId: string;
  canEdit: boolean;
  canDeleteDocs: boolean;
}) {
  const supabase = useMemo(() => createClient(), []);
  const { session } = useCrmAuth();
  const [docs, setDocs] = useState<TeamDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [docType, setDocType] = useState<TeamDocumentType>("other");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("team_documents")
      .select("*")
      .eq("profile_id", targetProfileId)
      .order("created_at", { ascending: false });
    if (error) toast.error(error.message);
    setDocs((data ?? []) as TeamDocument[]);
    setLoading(false);
  }, [supabase, targetProfileId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !session?.user?.id) return;
    setUploading(true);
    const filePath = `${targetProfileId}/${Date.now()}_${file.name}`;
    const { error: uploadError } = await supabase.storage
      .from("team-documents")
      .upload(filePath, file);
    if (uploadError) {
      toast.error(uploadError.message);
      setUploading(false);
      return;
    }
    const { error: insertError } = await supabase.from("team_documents").insert({
      profile_id: targetProfileId,
      document_type: docType,
      file_name: file.name,
      file_url: filePath,
      uploaded_by: session.user.id,
    });
    if (insertError) toast.error(insertError.message);
    else toast.success("Document uploaded");
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
    void load();
  }

  async function viewDoc(doc: TeamDocument) {
    if (!session?.access_token) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/team/documents/signed-url`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ file_path: doc.file_url }),
      });
      if (!r.ok) {
        toast.error((await r.text()).slice(0, 200));
        return;
      }
      const j = (await r.json()) as { signed_url: string };
      window.open(j.signed_url, "_blank");
    } catch {
      toast.error("Failed to generate signed URL");
    }
  }

  async function deleteDoc(doc: TeamDocument) {
    if (!session?.access_token) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/team/documents/delete`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ document_id: doc.id, file_path: doc.file_url }),
      });
      if (!r.ok) {
        toast.error((await r.text()).slice(0, 200));
        return;
      }
      toast.success("Document deleted");
      void load();
    } catch {
      toast.error("Failed to delete document");
    }
  }

  const docTypeLabel: Record<TeamDocumentType, string> = {
    contract: "Contract",
    id: "ID",
    nda: "NDA",
    other: "Other",
  };

  if (loading) return <p className="py-6 text-center text-sm text-slate-500">Loading documents…</p>;

  return (
    <div className="space-y-4">
      {canEdit && (
        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4">
          <div>
            <Label className="text-slate-600">Document type</Label>
            <select
              className="mt-1 w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900"
              value={docType}
              onChange={(e) => setDocType(e.target.value as TeamDocumentType)}
            >
              <option value="contract">Contract</option>
              <option value="id">ID</option>
              <option value="nda">NDA</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div className="flex-1">
            <Label className="text-slate-600">File</Label>
            <input
              ref={fileRef}
              type="file"
              className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-emerald-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-emerald-700 hover:file:bg-emerald-100"
              disabled={uploading}
              onChange={(e) => void handleUpload(e)}
            />
          </div>
          {uploading && <p className="text-sm text-slate-500">Uploading…</p>}
        </div>
      )}

      {docs.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">No documents uploaded yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">File name</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Uploaded</th>
                <th className="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} className="border-b border-slate-100 hover:bg-white">
                  <td className="px-3 py-2 font-medium text-slate-900">{d.file_name}</td>
                  <td className="px-3 py-2 text-slate-600">{docTypeLabel[d.document_type] ?? d.document_type}</td>
                  <td className="px-3 py-2 text-slate-500">{new Date(d.created_at).toLocaleDateString()}</td>
                  <td className="space-x-2 px-3 py-2">
                    <button
                      type="button"
                      className="text-xs text-emerald-600 underline"
                      onClick={() => void viewDoc(d)}
                    >
                      View
                    </button>
                    {canDeleteDocs && (
                      <button
                        type="button"
                        className="text-xs text-rose-500 underline"
                        onClick={() => void deleteDoc(d)}
                      >
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Bank details tab                                                  */
/* ------------------------------------------------------------------ */
function BankDetailsTab({ targetProfileId, canEdit }: { targetProfileId: string; canEdit: boolean }) {
  const supabase = useMemo(() => createClient(), []);
  const [details, setDetails] = useState<TeamBankDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    full_name: "",
    bank_name: "",
    account_number: "",
    routing_or_swift: "",
    payment_method: "bank_transfer" as PaymentMethod,
    payment_notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("team_bank_details")
      .select("*")
      .eq("profile_id", targetProfileId)
      .maybeSingle();
    if (error) toast.error(error.message);
    const row = data as TeamBankDetails | null;
    setDetails(row);
    if (row) {
      setForm({
        full_name: row.full_name ?? "",
        bank_name: row.bank_name ?? "",
        account_number: row.account_number ?? "",
        routing_or_swift: row.routing_or_swift ?? "",
        payment_method: row.payment_method ?? "bank_transfer",
        payment_notes: row.payment_notes ?? "",
      });
    }
    setLoading(false);
  }, [supabase, targetProfileId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    setSaving(true);
    const payload = {
      profile_id: targetProfileId,
      full_name: form.full_name || null,
      bank_name: form.bank_name || null,
      account_number: form.account_number || null,
      routing_or_swift: form.routing_or_swift || null,
      payment_method: form.payment_method,
      payment_notes: form.payment_notes || null,
      updated_at: new Date().toISOString(),
    };
    if (details) {
      const { error } = await supabase
        .from("team_bank_details")
        .update(payload)
        .eq("id", details.id);
      if (error) toast.error(error.message);
      else toast.success("Bank details saved");
    } else {
      const { error } = await supabase
        .from("team_bank_details")
        .insert(payload);
      if (error) toast.error(error.message);
      else toast.success("Bank details saved");
    }
    setSaving(false);
    void load();
  }

  if (loading) return <p className="py-6 text-center text-sm text-slate-500">Loading bank details…</p>;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label className="text-slate-600">Full name (on account)</Label>
          <Input
            className="mt-1 border-slate-200 bg-slate-50"
            value={form.full_name}
            disabled={!canEdit}
            onChange={(e) => setForm((prev) => ({ ...prev, full_name: e.target.value }))}
          />
        </div>
        <div>
          <Label className="text-slate-600">Bank name</Label>
          <Input
            className="mt-1 border-slate-200 bg-slate-50"
            value={form.bank_name}
            disabled={!canEdit}
            onChange={(e) => setForm((prev) => ({ ...prev, bank_name: e.target.value }))}
          />
        </div>
        <div>
          <Label className="text-slate-600">Account number</Label>
          <Input
            className="mt-1 border-slate-200 bg-slate-50"
            value={form.account_number}
            disabled={!canEdit}
            onChange={(e) => setForm((prev) => ({ ...prev, account_number: e.target.value }))}
          />
        </div>
        <div>
          <Label className="text-slate-600">Routing / SWIFT</Label>
          <Input
            className="mt-1 border-slate-200 bg-slate-50"
            value={form.routing_or_swift}
            disabled={!canEdit}
            onChange={(e) => setForm((prev) => ({ ...prev, routing_or_swift: e.target.value }))}
          />
        </div>
        <div>
          <Label className="text-slate-600">Payment method</Label>
          <select
            className="mt-1 w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 disabled:opacity-60"
            value={form.payment_method}
            disabled={!canEdit}
            onChange={(e) => setForm((prev) => ({ ...prev, payment_method: e.target.value as PaymentMethod }))}
          >
            <option value="bank_transfer">Bank transfer</option>
            <option value="wise">Wise</option>
            <option value="paypal">PayPal</option>
            <option value="gcash">GCash</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div className="sm:col-span-2">
          <Label className="text-slate-600">Payment notes</Label>
          <textarea
            className="mt-1 w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900 disabled:opacity-60"
            rows={2}
            value={form.payment_notes}
            disabled={!canEdit}
            onChange={(e) => setForm((prev) => ({ ...prev, payment_notes: e.target.value }))}
          />
        </div>
      </div>
      {canEdit && (
        <Button className="bg-emerald-600" disabled={saving} onClick={() => void save()}>
          {saving ? "Saving…" : "Save bank details"}
        </Button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Composed ProfileTabs                                              */
/* ------------------------------------------------------------------ */
export function ProfileTabs({ targetProfileId, canEdit, showBankDetails, canDeleteDocs }: ProfileTabsProps) {
  return (
    <Tabs defaultValue="details" className="w-full">
      <TabsList>
        <TabsTrigger value="details">Details</TabsTrigger>
        <TabsTrigger value="documents">Documents</TabsTrigger>
        {showBankDetails && <TabsTrigger value="bank">Bank Details</TabsTrigger>}
      </TabsList>
      <TabsContent value="details">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <DetailsTab targetProfileId={targetProfileId} canEdit={canEdit} />
        </div>
      </TabsContent>
      <TabsContent value="documents">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <DocumentsTab targetProfileId={targetProfileId} canEdit={canEdit} canDeleteDocs={canDeleteDocs} />
        </div>
      </TabsContent>
      {showBankDetails && (
        <TabsContent value="bank">
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <BankDetailsTab targetProfileId={targetProfileId} canEdit={canEdit} />
          </div>
        </TabsContent>
      )}
    </Tabs>
  );
}
