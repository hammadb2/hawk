"use client";

import { useCRM } from "./crm-provider";
import type { CRMRole } from "@/lib/crm-types";

interface RoleGuardProps {
  roles: CRMRole[];
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export function RoleGuard({ roles, children, fallback = null }: RoleGuardProps) {
  const { crmUser } = useCRM();
  if (!crmUser || !roles.includes(crmUser.crm_role)) return <>{fallback}</>;
  return <>{children}</>;
}
