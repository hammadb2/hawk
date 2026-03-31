import { TeamDirectory } from "@/components/crm/team/team-directory";

export default function TeamPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Team</h1>
        <p className="mt-1 text-sm text-zinc-500">Sales reps and team leads — read-only directory (CEO / HoS).</p>
      </div>
      <TeamDirectory />
    </div>
  );
}
