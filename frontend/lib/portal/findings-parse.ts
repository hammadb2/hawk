/** Normalize crm_prospect_scans.findings JSON → finding rows (Phase 5). */

export type ParsedFinding = {
  id?: string;
  severity?: string;
  title?: string;
};

export function findingsListFromScanPayload(findings: Record<string, unknown> | null | undefined): ParsedFinding[] {
  if (!findings || typeof findings !== "object") return [];
  const inner = findings.findings;
  if (!Array.isArray(inner)) return [];
  return inner.filter((x): x is ParsedFinding => x !== null && typeof x === "object");
}

export function summarizeSeverity(findings: ParsedFinding[]): {
  criticalTitles: string[];
  highCount: number;
  criticalCount: number;
} {
  const criticalTitles: string[] = [];
  let highCount = 0;
  let criticalCount = 0;
  for (const f of findings) {
    const sev = String(f.severity || "").toLowerCase();
    if (sev === "critical") {
      criticalCount += 1;
      const t = String(f.title || "").trim();
      if (t && criticalTitles.length < 5) criticalTitles.push(t);
    }
    if (sev === "high") highCount += 1;
  }
  return { criticalTitles, highCount, criticalCount };
}
