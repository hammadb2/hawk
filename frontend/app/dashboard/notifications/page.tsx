"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { notificationsApi, type Notification } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function DashboardNotificationsPage() {
  const { token } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    if (!token) return;
    notificationsApi
      .list(token)
      .then((r) => setNotifications(r.notifications))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [token]);

  const markAllRead = async () => {
    if (!token) return;
    try {
      await notificationsApi.readAll(token);
      load();
    } catch {
      // ignore
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Notifications</h1>
          <p className="text-text-secondary mt-1">Alerts, digests, and updates.</p>
        </div>
        {notifications.some((n) => !n.read) && (
          <Button variant="secondary" size="sm" onClick={markAllRead}>
            Mark all read
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Inbox</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {loading ? (
            <p className="text-text-dim">Loading…</p>
          ) : notifications.length === 0 ? (
            <p className="text-text-dim">No notifications yet.</p>
          ) : (
            <ul className="space-y-3">
              {notifications.map((n) => (
                <li
                  key={n.id}
                  className={cn(
                    "rounded-lg border p-4 transition-colors",
                    n.read ? "border-surface-3 bg-surface-1 text-text-secondary" : "border-surface-3 bg-surface-2 text-text-primary"
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-medium">{n.title}</p>
                      {n.body && <p className="text-sm mt-1 opacity-90">{n.body}</p>}
                      {n.created_at && (
                        <p className="text-xs text-text-dim mt-2">
                          {new Date(n.created_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                    {!n.read && (
                      <span className="shrink-0 w-2 h-2 rounded-full bg-accent" aria-hidden />
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
