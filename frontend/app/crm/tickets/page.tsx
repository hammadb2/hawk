import { SupportTicketsConsole } from "@/components/crm/tickets/support-tickets-console";

export default function TicketsPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Support tickets</h1>
        <p className="mt-1 text-sm text-zinc-500">File requests for leadership. CEO and HoS can change status and priority.</p>
      </div>
      <SupportTicketsConsole />
    </div>
  );
}
