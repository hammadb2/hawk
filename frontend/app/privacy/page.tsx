import Link from "next/link";

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background px-4 py-16 text-text-primary sm:px-6">
      <div className="mx-auto max-w-2xl">
        <Link href="/" className="text-sm text-[#00C48C] hover:underline">
          ← Back to home
        </Link>
        <h1 className="mt-8 text-3xl font-extrabold">Privacy Policy</h1>
        <p className="mt-6 text-text-secondary leading-relaxed">
          HAWK Security (AKB Studios) processes business contact information and domain scan data to deliver security assessments
          and services you request. For questions:{" "}
          <a href="mailto:hello@akbstudios.com" className="text-[#00C48C] hover:underline">
            hello@akbstudios.com
          </a>
          .
        </p>
        <p className="mt-4 text-sm text-text-dim">This page is a summary; full policy may be provided at contract.</p>
      </div>
    </div>
  );
}
