/**
 * Shared shell tokens used by the portal, 404, and auth pages. Unified with
 * the landing page: graphite ink canvas + signal amber accent. Kept under
 * `components/` so Tailwind `content` always picks up these class strings.
 */
export const portal = {
  pageBg:
    "min-h-dvh w-full bg-ink-950 font-display text-ink-0 antialiased",
  header:
    "border-b border-white/5 bg-ink-950/70 shadow-[0_1px_0_rgba(255,255,255,0.03)] backdrop-blur-xl",
  card: "rounded-2xl border border-white/5 bg-ink-800/60 shadow-ink",
  cardMuted: "rounded-2xl border border-white/5 bg-ink-900/70 shadow-ink",
  link: "font-medium text-signal hover:text-signal-400",
  linkSubtle: "text-ink-200 hover:text-signal",
  spinner:
    "h-10 w-10 animate-spin rounded-full border-2 border-ink-700 border-t-signal",
  spinnerSm:
    "h-8 w-8 animate-spin rounded-full border-2 border-ink-700 border-t-signal",
  input:
    "border-white/10 bg-ink-900 text-ink-0 placeholder:text-ink-300 focus-visible:ring-signal/30 focus-visible:border-signal/50",
  btnPrimary:
    "bg-signal font-semibold text-ink-950 shadow-signal-sm hover:bg-signal-400",
} as const;

export const lightShell = portal;
