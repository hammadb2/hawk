import { WebhookInstructions } from "@/components/crm/charlotte/webhook-instructions";

export default function CharlottePage() {
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Charlotte & email events</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Connect Smartlead, Charlotte, or any script to the HAWK API so reps see engagement on the prospect profile.
        </p>
      </div>
      <WebhookInstructions apiBase={apiBase} />
    </div>
  );
}
