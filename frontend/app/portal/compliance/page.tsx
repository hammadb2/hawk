import Link from "next/link";

export const metadata = {
  title: "C-27 privacy primer | HAWK Portal",
  description: "Plain-language orientation on Canada’s Bill C-27 and the proposed CPPA — not legal advice.",
};

/** Phase 5 — Client-facing orientation on federal privacy reform (educational). */

export default function PortalCompliancePage() {
  return (
    <div className="prose prose-invert prose-sm prose-headings:text-ink-0 prose-p:text-ink-200 prose-li:text-ink-200 max-w-none space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-ink-0">Canada privacy reform (Bill C-27) — primer</h1>
        <p className="text-sm text-ink-200">
          Short orientation for SMBs. This is not legal advice. Confirm obligations with qualified Canadian counsel.
        </p>
      </div>

      <section className="rounded-xl border border-white/10 bg-ink-800 p-5">
        <h2 className="mt-0 text-lg font-medium text-ink-0">What is Bill C-27?</h2>
        <p className="text-ink-100">
          <strong>Bill C-27</strong> is federal legislation (as proposed and amended over time) intended to modernize
          Canada’s private-sector privacy framework. A central piece is the <strong>Consumer Privacy Protection Act (CPPA)</strong>,
          which would replace parts of PIPEDA for organizations subject to federal law. Provisions, timelines, and
          transition rules change as the bill moves through Parliament — always check current status on{" "}
          <a href="https://www.priv.gc.ca" className="text-signal hover:underline" target="_blank" rel="noreferrer">
            priv.gc.ca
          </a>{" "}
          and with your lawyer.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-medium text-ink-0">How this relates to HAWK</h2>
        <ul className="text-ink-100">
          <li>
            <strong>Technical security</strong> (what HAWK scans) supports <strong>safeguards</strong> and breach-risk
            reduction — one input into privacy programs.
          </li>
          <li>
            <strong>Compliance</strong> still requires policies, contracts, consent/notice, data retention, vendor
            management, and breach processes — beyond an external scan.
          </li>
          <li>
            Your <strong>PIPEDA overview PDF</strong> from the portal maps findings to <em>themes</em> under today’s
            fair information principles; CPPA (if enacted in your context) may add new duties and enforcement tools.
          </li>
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-medium text-ink-0">Practical next steps</h2>
        <ol className="text-ink-100">
          <li>Prioritize critical and high findings; document remediation dates and owners.</li>
          <li>Maintain a simple data inventory: what personal information you hold, where, and why.</li>
          <li>Review breach notification readiness (real risk of significant harm) under current PIPEDA — CPPA may evolve.</li>
          <li>Ask your counsel whether provincial law (e.g. Quebec Law 25, Alberta, B.C.) applies instead of or alongside federal rules.</li>
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
