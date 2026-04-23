import Link from "next/link";

export const metadata = {
  title: "Compliance overview | HAWK Portal",
  description:
    "Vertical aware US compliance orientation. HIPAA Security Rule for dental and medical, FTC Safeguards Rule for accounting and tax, ABA Formal Opinion 24-514 for legal. Educational, not legal advice.",
};

/** Portal orientation page. Content mirrors the downloadable compliance overview PDF so
 *  a client can read the same material in the browser before downloading. Vertical specific
 *  framing lives in the PDF generator; this page surfaces all three frameworks plus the
 *  generic US baseline so any client can find what applies to them.
 */
export default function PortalCompliancePage() {
  return (
    <div className="prose prose-slate prose-sm prose-headings:text-slate-900 prose-p:text-slate-600 prose-li:text-slate-600 max-w-none space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Cybersecurity compliance for US practices</h1>
        <p className="text-sm text-slate-600">
          Orientation for dental, medical, accounting, tax, and legal practices operating under US regulation. Not
          legal advice. Confirm your obligations with qualified US counsel.
        </p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="mt-0 text-lg font-medium text-slate-900">How HAWK maps to your framework</h2>
        <p className="text-slate-700">
          Your downloadable <strong>compliance overview PDF</strong> selects the framework that applies to your
          practice based on your vertical and maps your latest findings to named sections with enforcement context.
          The summary below is a plain language orientation to each framework.
        </p>
        <ul className="text-slate-700">
          <li>
            <strong>Technical security</strong> (what HAWK scans) supports the <strong>safeguards</strong> required by
            every US framework below. It is one input into a broader compliance program.
          </li>
          <li>
            <strong>Compliance</strong> also requires documented policies, incident response, vendor oversight,
            workforce training, and breach notification procedures that go beyond an external scan.
          </li>
        </ul>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="mt-0 text-lg font-medium text-slate-900">Dental and medical practices</h2>
        <p className="text-slate-700">
          The <strong>HIPAA Security Rule</strong> at 45 CFR 164 Subpart C requires administrative, physical, and
          technical safeguards for electronic protected health information. The <strong>Breach Notification
          Rule</strong> at Subpart D requires notification to HHS and affected individuals within 60 days of discovery
          for breaches of unsecured PHI. Media notice is required for breaches affecting 500 or more individuals in a
          state or jurisdiction. Authority sits with the US Department of Health and Human Services, Office for Civil
          Rights (OCR).
        </p>
        <p className="text-slate-700">
          HAWK findings commonly map to Technical Safeguards at 45 CFR 164.312, Security Incident Procedures at
          164.308(a)(6), and Risk Analysis at 164.308(a)(1)(ii)(A).
        </p>
        <p className="text-sm text-slate-600">
          Official guidance:{" "}
          <a
            href="https://www.hhs.gov/hipaa/for-professionals/security/index.html"
            className="text-emerald-600 hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            hhs.gov HIPAA Security Rule
          </a>
        </p>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="mt-0 text-lg font-medium text-slate-900">Accounting, CPA, and tax practices</h2>
        <p className="text-slate-700">
          The <strong>FTC Safeguards Rule</strong> at 16 CFR 314 requires covered financial institutions, which
          include tax preparers, CPA firms, and bookkeeping firms, to develop and maintain a written Information
          Security Program with nine required elements. The <strong>May 2024 amendment</strong> at 16 CFR 314.5 adds
          an affirmative 30 day notification duty to the FTC for any notification event affecting 500 or more
          consumers. Authority sits with the US Federal Trade Commission.
        </p>
        <p className="text-slate-700">
          HAWK findings commonly map to the Encryption element at 16 CFR 314.4(c)(3), the Access Controls element at
          16 CFR 314.4(c)(1), the Risk Assessment duty at 16 CFR 314.4(b), and the Continuous Monitoring duty at 16
          CFR 314.4(d)(2).
        </p>
        <p className="text-sm text-slate-600">
          Official guidance:{" "}
          <a
            href="https://www.ftc.gov/business-guidance/resources/ftc-safeguards-rule-what-your-business-needs-know"
            className="text-emerald-600 hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            ftc.gov Safeguards Rule guide
          </a>
        </p>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="mt-0 text-lg font-medium text-slate-900">Legal practices and law firms</h2>
        <p className="text-slate-700">
          <strong>ABA Formal Opinion 24-514</strong> (April 2024) confirms that lawyers have an affirmative duty to
          notify current clients of a material data incident affecting representation. That duty is grounded in{" "}
          <strong>Model Rule 1.1</strong> (competence, including Comment 8 on technology competence),{" "}
          <strong>Model Rule 1.4</strong> (communication), and <strong>Model Rule 1.6(c)</strong> (reasonable efforts
          to prevent inadvertent or unauthorized disclosure of client confidences). State bars in New York,
          California, Texas, and Florida have issued parallel guidance. <strong>Model Rule 1.15</strong> treats trust
          account losses from phishing as safekeeping violations.
        </p>
        <p className="text-slate-700">
          HAWK findings commonly map to Rule 1.6(c) reasonable efforts, Rule 1.1 technology competence, Rule 1.4
          communication duties when lookalike domains are used to impersonate the firm, and Rule 1.15 when wire fraud
          exposure is present.
        </p>
        <p className="text-sm text-slate-600">
          Official guidance:{" "}
          <a
            href="https://www.americanbar.org/groups/professional_responsibility/publications/"
            className="text-emerald-600 hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            americanbar.org ethics opinions
          </a>
        </p>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="mt-0 text-lg font-medium text-slate-900">Any US practice: state breach notification baseline</h2>
        <p className="text-slate-700">
          Every US state has its own data breach notification law, with timelines typically ranging from 30 to 90 days
          and thresholds that vary by state. Cyber insurance carriers now require multi factor authentication,
          endpoint detection and response, and a written information security program at renewal. Even practices
          outside HIPAA, FTC, and ABA scope should plan against the shortest applicable state deadline.
        </p>
      </section>

      <section>
        <h2 className="text-lg font-medium text-slate-900">Practical next steps</h2>
        <ol className="text-slate-700">
          <li>Prioritize critical and high findings. Document remediation dates and owners.</li>
          <li>Maintain a written risk assessment or risk analysis proportionate to your framework.</li>
          <li>Confirm your incident response procedures can meet the shortest applicable breach clock.</li>
          <li>Review your framework annually with counsel and your IT provider.</li>
        </ol>
      </section>

      <p className="text-center text-sm text-slate-500">
        <Link href="/portal" className="text-emerald-600 hover:underline">
          Back to portal home
        </Link>
      </p>
    </div>
  );
}
