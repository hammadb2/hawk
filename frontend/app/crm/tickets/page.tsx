import { SupportTicketsConsole } from "@/components/crm/tickets/support-tickets-console";
import { crmPageSubtitle, crmPageTitle } from "@/lib/crm/crm-surface";

export default function TicketsPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className={crmPageTitle}>Support tickets</h1>
        <p className={crmPageSubtitle}>File requests for leadership. CEO and HoS can change status and priority.</p>
      </div>
      <SupportTicketsConsole />
    </div>
  );
}
