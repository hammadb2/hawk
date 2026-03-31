import { LiveScoreboard } from "@/components/crm/scoreboard/live-scoreboard";

export default function ScoreboardPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Scoreboard</h1>
        <p className="mt-1 text-sm text-zinc-500">Live team rankings — same data refreshes when records change (Supabase Realtime).</p>
      </div>
      <LiveScoreboard />
    </div>
  );
}
