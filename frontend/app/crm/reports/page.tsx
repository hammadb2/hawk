import { ReportsHub } from "@/components/crm/reports/reports-hub";

export default function ReportsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Reports</h1>
        <p className="mt-1 text-sm text-zinc-500">Pipeline, revenue, and commission snapshot from live CRM data.</p>
      </div>
      <ReportsHub />
    </div>
  );
}
