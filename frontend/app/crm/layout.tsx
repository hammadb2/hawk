import { CrmAuthProvider } from "@/components/crm/crm-auth-provider";
import { CrmShell } from "@/components/crm/layout/crm-shell";

export default function CrmLayout({ children }: { children: React.ReactNode }) {
  return (
    <CrmAuthProvider>
      <CrmShell>{children}</CrmShell>
    </CrmAuthProvider>
  );
}
