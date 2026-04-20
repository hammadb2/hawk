import { VAConsole } from "@/components/crm/va/va-console";
import { crmPageSubtitle, crmPageTitle } from "@/lib/crm/crm-surface";

export default function VAPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div>
        <h1 className={crmPageTitle}>VA Outreach</h1>
        <p className={crmPageSubtitle}>
          Manual outreach queue for the overflow past the 600/day automated dispatcher. VA manager assigns;
          VAs copy the ARIA-drafted email, send from their own inbox, and log the outcome.
        </p>
      </div>
      <VAConsole />
    </div>
  );
}
