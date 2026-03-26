"use client";

import { useState, useEffect } from "react";
import { Pen, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDateTime, getInitials } from "@/lib/utils";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { useCRMStore } from "@/store/crm-store";
import { createClient } from "@/lib/supabase";
import type { Activity } from "@/types/crm";

interface NotesTabProps {
  prospectId: string;
}

export function NotesTab({ prospectId }: NotesTabProps) {
  const { user } = useCRMStore();
  const [notes, setNotes] = useState<Activity[]>([]);
  const [newNote, setNewNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const loadNotes = async () => {
    const supabase = createClient();
    const { data, error } = await supabase
      .from("activities")
      .select("*, author:created_by(id, name, role)")
      .eq("prospect_id", prospectId)
      .eq("type", "note_added")
      .order("created_at", { ascending: false });

    if (!error && data) {
      setNotes(data as Activity[]);
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await loadNotes();
      setLoading(false);
    };
    init();
  }, [prospectId]);

  const handleSubmit = async () => {
    if (!newNote.trim()) return;
    setSubmitting(true);

    try {
      const result = await prospectsApi.addNote(prospectId, newNote.trim());
      if (result.success) {
        setNewNote("");
        await loadNotes();
        toast({ title: "Note added", variant: "success" });
      } else {
        toast({ title: result.error || "Failed to add note", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Add note form */}
      <div className="rounded-xl border border-border bg-surface-2 p-3">
        <Textarea
          value={newNote}
          onChange={(e) => setNewNote(e.target.value)}
          placeholder="Add a note..."
          rows={3}
          className="border-0 bg-transparent p-0 resize-none focus-visible:ring-0"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              handleSubmit();
            }
          }}
        />
        <div className="flex items-center justify-between mt-2">
          <span className="text-2xs text-text-dim">Cmd+Enter to submit</span>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={!newNote.trim() || submitting}
            className="gap-1.5 h-7 text-xs"
          >
            <Send className="w-3 h-3" />
            {submitting ? "Adding..." : "Add Note"}
          </Button>
        </div>
      </div>

      {/* Notes list */}
      {notes.length === 0 ? (
        <EmptyState
          icon={Pen}
          title="No notes yet"
          description="Add a note above to keep track of important information."
        />
      ) : (
        <div className="space-y-3">
          {notes.map((note) => (
            <div key={note.id} className="flex gap-3">
              <Avatar className="w-7 h-7 flex-shrink-0">
                <AvatarFallback className="text-xs">
                  {note.author ? getInitials(note.author.name) : "?"}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-xs font-medium text-text-primary">
                    {note.author?.name ?? "Unknown"}
                  </span>
                  <span className="text-2xs text-text-dim">
                    {formatDateTime(note.created_at)}
                  </span>
                </div>
                <p className="text-sm text-text-secondary leading-relaxed">{note.notes}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
