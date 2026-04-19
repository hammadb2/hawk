import { ReportsHub } from "@/components/crm/reports/reports-hub";
import { crmPageSubtitle, crmPageTitle } from "@/lib/crm/crm-surface";

export default function ReportsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className={crmPageTitle}>Reports</h1>
        <p className={crmPageSubtitle}>Pipeline, revenue, and commission snapshot from live CRM data.</p>
      </div>
      <ReportsHub />
    </div>
  );
}
