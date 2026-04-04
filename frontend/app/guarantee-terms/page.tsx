import Link from "next/link";

export default function GuaranteeTermsPage() {
  return (
    <div className="min-h-screen bg-background px-4 py-16 text-text-primary sm:px-6">
      <div className="mx-auto max-w-2xl">
        <Link href="/" className="text-sm text-[#00C48C] hover:underline">
          ← Back to home
        </Link>
        <h1 className="mt-8 text-3xl font-extrabold">Guarantee terms</h1>
        <p className="mt-6 text-text-secondary leading-relaxed">
          HAWK Shield includes financially backed incident response coverage subject to your subscription agreement, timely remediation
          of notified critical and high findings, and other conditions in writing at signup. Your executed order or master services
          agreement controls for your organization.
        </p>
        <p className="mt-4 text-text-secondary leading-relaxed">
          For a copy of the full guarantee terms for your plan, contact{" "}
          <a href="mailto:hello@akbstudios.com" className="text-[#00C48C] hover:underline">
            hello@akbstudios.com
          </a>
          .
        </p>
      </div>
    </div>
  );
}
