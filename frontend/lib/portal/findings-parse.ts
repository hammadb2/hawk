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

/** Top findings for client-facing copy (severity + title). */
export function topFindingsPlainEnglish(findings: ParsedFinding[], limit = 3): string[] {
  const out: string[] = [];
  const order = ["critical", "high", "medium", "low", "info"];
  const rank = (s: string) => {
    const i = order.indexOf(s);
    return i === -1 ? 99 : i;
  };
  const sorted = [...findings].sort((a, b) => {
    const sa = String(a.severity || "").toLowerCase();
    const sb = String(b.severity || "").toLowerCase();
    return rank(sa) - rank(sb);
  });
  for (const f of sorted) {
    const title = String(f.title || "").trim();
    if (!title) continue;
    const sev = String(f.severity || "").toLowerCase();
    const label =
      sev === "critical"
        ? "Critical"
        : sev === "high"
          ? "High"
          : sev === "medium"
            ? "Medium"
            : sev === "low"
              ? "Low"
              : "Finding";
    out.push(`${label}: ${title}`);
    if (out.length >= limit) break;
  }
  return out;
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
