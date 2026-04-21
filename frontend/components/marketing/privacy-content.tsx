"use client";

import Link from "next/link";
import { motion } from "framer-motion";

const SECTIONS: ReadonlyArray<{ id: string; title: string; body: ReadonlyArray<string> }> = [
  {
    id: "who-we-are",
    title: "1. Who we are",
    body: [
      "HAWK Security is a product of AKB Company Ltd (doing business as AKB Studios). We build external cybersecurity monitoring and breach response services for dental, legal, and accounting practices in the United States.",
      "When this policy says we, us, or HAWK, it means AKB Company Ltd operating the HAWK Security product under the securedbyhawk.com domain.",
    ],
  },
  {
    id: "data-we-collect",
    title: "2. Data we collect",
    body: [
      "Business contact data. If you enter a domain and work email on a HAWK form, we store the name, email, business name, practice type, and domain you provided, plus timestamps and source attribution for audit purposes.",
      "Scan data. When HAWK runs a scan on a domain, we collect publicly visible external signals: DNS records, mail authentication posture (SPF, DKIM, DMARC), TLS configuration, HTTP response headers, and exposed service banners returned by the target. We do not authenticate to any system you own without a separate signed agreement.",
      "Usage data. Server access logs with IP address, user agent, and timestamps. We use these for security and abuse prevention.",
      "We do not collect patient records, client matter data, or any regulated information from inside your systems. HAWK is an external surface monitoring product, by design.",
    ],
  },
  {
    id: "how-we-use",
    title: "3. How we use data",
    body: [
      "We use business contact data to deliver the report or service you asked for, to email findings of new risk we detect on your domain, and to contact you about HAWK offerings directly related to that intent.",
      "We use scan data to compute your posture score, produce the report, track regressions, and to improve our detection engines at the aggregate level. Aggregate means statistics across many customers with no individual business identifiable.",
      "We never sell your contact data or scan results. We do not use your scan data to enrich third party lead databases.",
    ],
  },
  {
    id: "retention",
    title: "4. Retention",
    body: [
      "Active customer records are retained for the lifetime of the subscription plus 12 months for audit and breach response continuity.",
      "Free scan leads and their report data are retained for 24 months so we can detect regressions if you return. You can request deletion at any time.",
      "Server access logs are retained for 30 days.",
    ],
  },
  {
    id: "disclosure",
    title: "5. When we disclose data",
    body: [
      "We disclose data only in these cases. One, subprocessors we use to run HAWK, under a written data processing agreement. These include our database, email delivery, infrastructure, and observability providers. Two, to comply with a lawful order, subpoena, or court process. Three, to protect HAWK or its customers from abuse, fraud, or security incidents.",
      "If any of the above requires a change in how your data is handled we will notify you in advance where legally permitted.",
    ],
  },
  {
    id: "rights",
    title: "6. Your rights",
    body: [
      "You have the right to access, correct, and delete the business contact data we hold on you. Email hello@securedbyhawk.com with the subject line data request and the work email on file, and we will respond within 10 business days.",
      "You can unsubscribe from any HAWK email at any time. Unsubscribe removes you from marketing sends. It does not delete records of past business. For full deletion use the data request flow above.",
    ],
  },
  {
    id: "security",
    title: "7. How we secure data",
    body: [
      "Data at rest is encrypted using AES 256 managed by our infrastructure provider. Data in transit is encrypted with TLS 1.2 or higher. Access to production data is restricted to HAWK engineering staff with least privilege role based permissions and audited access.",
      "We run the same kind of external monitoring on our own infrastructure that we sell you. If we find something on ourselves we fix it the same day.",
    ],
  },
  {
    id: "children",
    title: "8. Children",
    body: [
      "HAWK is a B2B product for licensed professional practices. We do not knowingly collect information from anyone under 18. If you believe a minor provided information to us, contact hello@securedbyhawk.com and we will delete it.",
    ],
  },
  {
    id: "changes",
    title: "9. Changes to this policy",
    body: [
      "If we make material changes we will notify current customers by email at least 14 days in advance. The current version is always posted here with a last updated date.",
    ],
  },
  {
    id: "contact",
    title: "10. Contact",
    body: [
      "Questions about this policy, or about data we hold on you, can be sent to hello@securedbyhawk.com. We will respond within 10 business days.",
    ],
  },
];

export function PrivacyContent() {
  return (
    <section className="relative px-6 pb-28 pt-20 sm:px-8 sm:pb-32 sm:pt-28">
      <div className="mx-auto grid max-w-6xl gap-16 lg:grid-cols-[260px_1fr]">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          >
            <span className="text-eyebrow inline-flex items-center gap-2 text-signal">
              <span className="h-1.5 w-1.5 rounded-full bg-signal" />
              Privacy policy
            </span>
            <h1 className="mt-5 font-display text-4xl font-extrabold tracking-tightest text-ink-0 sm:text-5xl">
              What we collect. Why we keep it.
            </h1>
            <p className="mt-4 text-sm leading-relaxed text-ink-200">
              Last updated April 2026. Plain language version. Binding legal terms live in your signed subscription agreement.
            </p>
            <nav className="mt-8 hidden flex-col gap-2 border-l border-white/10 pl-4 text-sm lg:flex">
              {SECTIONS.map((s) => (
                <a
                  key={s.id}
                  href={`#${s.id}`}
                  className="text-ink-200 transition-colors hover:text-ink-0"
                >
                  {s.title}
                </a>
              ))}
            </nav>
          </motion.div>
        </aside>

        <motion.article
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.1 }}
          className="max-w-3xl"
        >
          {SECTIONS.map((section, i) => (
            <section
              key={section.id}
              id={section.id}
              className={`scroll-mt-24 border-t border-white/5 pb-10 pt-10 ${
                i === 0 ? "border-t-0 pt-0" : ""
              }`}
            >
              <h2 className="font-display text-2xl font-bold tracking-tight text-ink-0 sm:text-3xl">
                {section.title}
              </h2>
              <div className="mt-5 space-y-4">
                {section.body.map((p, idx) => (
                  <p key={idx} className="text-pretty text-base leading-relaxed text-ink-100">
                    {p}
                  </p>
                ))}
              </div>
            </section>
          ))}

          <div className="mt-14 rounded-2xl border border-white/5 bg-ink-900/60 p-6 backdrop-blur-xl sm:p-8">
            <p className="text-sm leading-relaxed text-ink-100">
              Questions about this policy or a data request.
            </p>
            <p className="mt-2 text-sm leading-relaxed text-ink-200">
              <a
                href="mailto:hello@securedbyhawk.com"
                className="font-semibold text-signal transition-colors hover:text-signal-400"
              >
                hello@securedbyhawk.com
              </a>
            </p>
            <div className="mt-6 flex flex-wrap gap-3 text-sm">
              <Link
                href="/free-scan"
                className="inline-flex items-center gap-1.5 rounded-full bg-signal px-4 py-2 font-semibold text-ink-950 shadow-signal-sm transition-colors hover:bg-signal-400"
              >
                Run a free scan
              </Link>
              <Link
                href="/guarantee-terms"
                className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2 font-medium text-ink-100 transition-colors hover:border-white/20 hover:text-ink-0"
              >
                Guarantee terms
              </Link>
            </div>
          </div>
        </motion.article>
      </div>
    </section>
  );
}
