/**
 * Portal + CRM light shell — lives under `components/` so Tailwind `content`
 * always picks up these class strings (avoids purging when `lib/` is missed).
 */
export const portal = {
  pageBg: "min-h-dvh w-full bg-gradient-to-b from-slate-50 via-white to-slate-50 text-slate-900 antialiased",
  header:
    "border-b border-slate-200/90 bg-white shadow-[0_1px_0_rgba(15,23,42,0.06)] backdrop-blur-sm",
  card: "rounded-2xl border border-slate-200/90 bg-white shadow-sm",
  cardMuted: "rounded-2xl border border-slate-200/80 bg-slate-50/80 shadow-sm",
  link: "font-medium text-emerald-600 hover:text-emerald-700",
  linkSubtle: "text-slate-500 hover:text-emerald-600",
  spinner: "h-10 w-10 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500",
  spinnerSm: "h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500",
  input:
    "border-slate-200 bg-white text-slate-900 placeholder:text-slate-400 focus-visible:ring-emerald-500/20 focus-visible:border-emerald-400",
  btnPrimary: "bg-emerald-500 font-semibold text-white shadow-sm hover:bg-emerald-600",
} as const;

export const lightShell = portal;
