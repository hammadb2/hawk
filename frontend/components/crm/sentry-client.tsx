"use client";

import { useEffect, useRef } from "react";

export function SentryClientInit() {
  const started = useRef(false);
  useEffect(() => {
    const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
    if (!dsn || started.current) return;
    started.current = true;
    void import("@sentry/nextjs").then((Sentry) => {
      Sentry.init({ dsn, tracesSampleRate: 0.1 });
    });
  }, []);
  return null;
}
