"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AlertCircle, Loader2 } from "lucide-react";
import { useCRMStore } from "@/store/crm-store";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { createClient } from "@/lib/supabase";

const CANADIAN_PROVINCES = [
  "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"
];

const INDUSTRIES = [
  "Healthcare", "Legal", "Financial Services", "Real Estate", "Retail",
  "Technology", "Construction", "Manufacturing", "Education", "Hospitality",
  "Professional Services", "Other"
];

interface AddProspectModalProps {
  open: boolean;
  onClose: () => void;
}

export function AddProspectModal({ open, onClose }: AddProspectModalProps) {
  const { user, addProspect } = useCRMStore();
  const [domain, setDomain] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [industry, setIndustry] = useState("");
  const [city, setCity] = useState("");
  const [province, setProvince] = useState("");
  const [loading, setLoading] = useState(false);
  const [suppressed, setSuppressed] = useState(false);
  const [enriching, setEnriching] = useState(false);

  const checkSuppression = async (d: string) => {
    if (!d) return;
    const supabase = createClient();
    const { data } = await supabase
      .from("suppressions")
      .select("id")
      .eq("domain", d)
      .limit(1);

    if (data && data.length > 0) {
      setSuppressed(true);
    } else {
      setSuppressed(false);
    }
  };

  const handleDomainBlur = async () => {
    await checkSuppression(domain.trim());
  };

  const handleSubmit = async () => {
    if (!domain.trim() || !companyName.trim()) return;
    if (suppressed) {
      toast({ title: "Domain is on suppression list", variant: "destructive" });
      return;
    }

    setLoading(true);
    try {
      const result = await prospectsApi.create({
        domain: domain.trim(),
        company_name: companyName.trim(),
        industry: industry || undefined,
        city: city.trim() || undefined,
        province: province || undefined,
      });

      if (result.success && result.data) {
        addProspect(result.data);
        toast({ title: `${companyName} added to pipeline`, variant: "success" });
        handleClose();
      } else {
        toast({ title: result.error || "Failed to add prospect", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setDomain("");
    setCompanyName("");
    setIndustry("");
    setCity("");
    setProvince("");
    setSuppressed(false);
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add Prospect</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Domain <span className="text-red">*</span>
            </label>
            <Input
              value={domain}
              onChange={(e) => { setDomain(e.target.value); setSuppressed(false); }}
              onBlur={handleDomainBlur}
              placeholder="acme.com"
              className={suppressed ? "border-red/60 focus:border-red/60" : ""}
            />
            {suppressed && (
              <div className="flex items-center gap-1.5 mt-1.5">
                <AlertCircle className="w-3.5 h-3.5 text-red" />
                <span className="text-xs text-red">This domain is on the suppression list (CASL)</span>
              </div>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Company Name <span className="text-red">*</span>
            </label>
            <Input
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="Acme Corporation"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Industry
              </label>
              <Select value={industry} onValueChange={setIndustry}>
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {INDUSTRIES.map((ind) => (
                    <SelectItem key={ind} value={ind}>{ind}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Province
              </label>
              <Select value={province} onValueChange={setProvince}>
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {CANADIAN_PROVINCES.map((p) => (
                    <SelectItem key={p} value={p}>{p}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              City
            </label>
            <Input
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="Calgary"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={handleClose} disabled={loading}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            disabled={!domain.trim() || !companyName.trim() || loading || suppressed}
          >
            {loading ? (
              <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Adding...</>
            ) : (
              "Add Prospect"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
