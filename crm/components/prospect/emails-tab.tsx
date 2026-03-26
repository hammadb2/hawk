"use client";

import { useState, useEffect } from "react";
import { Mail, Eye, MousePointer, MessageSquare } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDateTime, cn } from "@/lib/utils";
import { createClient } from "@/lib/supabase";
import type { EmailEvent, ReplySentiment } from "@/types/crm";

const SENTIMENT_CONFIG: Record<ReplySentiment, { label: string; variant: "success" | "destructive" | "info" | "warning" }> = {
  positive: { label: "Positive", variant: "success" },
  negative: { label: "Negative", variant: "destructive" },
  question: { label: "Question", variant: "info" },
  ooo: { label: "OOO", variant: "warning" },
};

interface EmailsTabProps {
  prospectId: string;
}

export function EmailsTab({ prospectId }: EmailsTabProps) {
  const [emails, setEmails] = useState<EmailEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const supabase = createClient();
      const { data, error } = await supabase
        .from("email_events")
        .select("*")
        .eq("prospect_id", prospectId)
        .order("created_at", { ascending: false });

      if (!error && data) {
        setEmails(data as EmailEvent[]);
      }
      setLoading(false);
    };
    load();
  }, [prospectId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    );
  }

  if (emails.length === 0) {
    return (
      <EmptyState
        icon={Mail}
        title="No emails yet"
        description="Charlotte's outreach emails will appear here once sent."
      />
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-text-dim uppercase tracking-wide mb-3">
        {emails.length} Email{emails.length !== 1 ? "s" : ""} sent
      </p>
      {emails.map((email) => (
        <div key={email.id} className="rounded-xl border border-border bg-surface-2 p-3.5">
          <div className="flex items-start gap-3">
            <div className="w-7 h-7 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center flex-shrink-0">
              <Mail className="w-3.5 h-3.5 text-accent-light" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between gap-2 mb-1">
                <p className="text-sm font-medium text-text-primary truncate">
                  {email.subject ?? "(no subject)"}
                </p>
                {email.sequence_step !== null && (
                  <span className="text-2xs text-text-dim bg-surface-3 rounded px-1.5 py-0.5 flex-shrink-0">
                    Step {email.sequence_step}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-3 text-2xs text-text-dim mb-2">
                {email.sent_at && <span>Sent {formatDateTime(email.sent_at)}</span>}
              </div>

              {/* Stats row */}
              <div className="flex items-center gap-4">
                {email.open_count > 0 && (
                  <div className="flex items-center gap-1 text-xs text-text-secondary">
                    <Eye className="w-3 h-3" />
                    <span>{email.open_count} opens</span>
                  </div>
                )}
                {email.click_count > 0 && (
                  <div className="flex items-center gap-1 text-xs text-text-secondary">
                    <MousePointer className="w-3 h-3" />
                    <span>{email.click_count} clicks</span>
                  </div>
                )}
                {email.replied_at && (
                  <div className="flex items-center gap-1 text-xs text-green">
                    <MessageSquare className="w-3 h-3" />
                    <span>Replied</span>
                  </div>
                )}
                {email.reply_sentiment && (
                  <Badge
                    variant={SENTIMENT_CONFIG[email.reply_sentiment].variant}
                    className="text-2xs"
                  >
                    {SENTIMENT_CONFIG[email.reply_sentiment].label}
                  </Badge>
                )}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
