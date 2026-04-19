import { TeamDirectory } from "@/components/crm/team/team-directory";
import { crmPageSubtitle, crmPageTitle } from "@/lib/crm/crm-surface";

export default function TeamPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className={crmPageTitle}>Team</h1>
        <p className={crmPageSubtitle}>Sales reps and team leads — read-only directory (CEO / HoS).</p>
      </div>
      <TeamDirectory />
    </div>
  );
}
