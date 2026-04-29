import Link from "next/link";

export const metadata = {
  title: "US compliance primer | HAWK Portal",
  description: "Plain-language orientation on US privacy and cybersecurity regulations for SMBs — not legal advice.",
};

/** Phase 5 — Client-facing orientation on US regulatory landscape (educational). */

export default function PortalCompliancePage() {
  return (
    <div className="prose prose-invert prose-sm prose-headings:text-ink-0 prose-p:text-ink-200 prose-li:text-ink-200 max-w-none space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-ink-0">US cybersecurity compliance — primer</h1>
        <p className="text-sm text-ink-200">
          Short orientation for SMBs. This is not legal advice. Confirm obligations with qualified US counsel.
        </p>
      </div>

      <section className="rounded-xl border border-white/10 bg-ink-800 p-5">
        <h2 className="mt-0 text-lg font-medium text-ink-0">Key regulations by industry</h2>
        <ul className="text-ink-100">
          <li>
            <strong>Healthcare (dental, medical)</strong> — <strong>HIPAA Security Rule</strong> (45 CFR 164) requires
            administrative, physical, and technical safeguards. The OCR 60-day breach notification rule applies to
            unsecured PHI. Penalties range from $100 to $50,000+ per violation.
          </li>
          <li>
            <strong>Financial services (accounting, tax, wealth management)</strong> — The <strong>FTC Safeguards Rule</strong>{" "}
            (16 CFR 314) requires a written information security program. The May 2024 amendment added 30-day breach
            notification requirements.
          </li>
          <li>
            <strong>Legal</strong> — <strong>ABA Formal Opinion 2024-3</strong> establishes cyber ethics duties under
            Model Rules 1.1, 1.4, and 1.6. Attorneys must make reasonable efforts to prevent unauthorized access to
            client information.
          </li>
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-medium text-ink-0">How this relates to HAWK</h2>
        <ul className="text-ink-100">
          <li>
            <strong>Technical security</strong> (what HAWK scans) supports <strong>safeguards</strong> and breach-risk
            reduction — one input into compliance programs.
          </li>
          <li>
            <strong>Compliance</strong> still requires policies, contracts, access controls, data retention, vendor
            management, and breach response plans — beyond an external scan.
          </li>
          <li>
            Your <strong>compliance overview PDF</strong> from the portal maps scan findings to regulatory themes
            relevant to your industry.
          </li>
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-medium text-ink-0">Practical next steps</h2>
        <ol className="text-ink-100">
          <li>Prioritize critical and high findings; document remediation dates and owners.</li>
          <li>Maintain a simple data inventory: what sensitive information you hold, where, and why.</li>
          <li>Review your breach notification readiness under the applicable regulation for your industry.</li>
          <li>Check whether your state has its own data breach notification law (all 50 states do) — requirements vary.</li>
        </ol>
      </section>

      <p className="text-center text-sm text-ink-0">
        <Link href="/portal" className="text-signal hover:underline">
          Back to portal home
        </Link>
      </p>
    </div>
  );
}
