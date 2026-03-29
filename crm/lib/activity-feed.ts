import type { Activity } from "@/types/crm";

export interface FeedItem {
  id: string;
  type: string;
  text: string;
  time: string;
}

export function activityToFeedItem(a: Activity): FeedItem {
  const typeLabel = a.type.replace(/_/g, " ");
  const text = a.notes ? a.notes.slice(0, 80) : typeLabel.charAt(0).toUpperCase() + typeLabel.slice(1);
  return { id: a.id, type: a.type, text, time: a.created_at };
}
