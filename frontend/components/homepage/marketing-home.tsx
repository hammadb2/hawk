"use client";

import Link from "next/link";
import { HomeScanner } from "./home-scanner";
import {
  EnterpriseBookingLink,
  ShieldCheckoutButton,
  StarterCheckoutButton,
} from "./pricing-checkout-buttons";

function NavScanButton({ className }: { className?: string }) {
  return (
    <a
      href="#scan"
      className={`${className} bg-accent hover:bg-accent/90 text-white shadow-sm transition-colors`}
    >
      Scan My Domain Free
    </a>
  );
}

const ENTERPRISE_BOOKING =
  process.env.NEXT_PUBLIC_CAL_COM_BOOKING_URL || "https://cal.com";

export function MarketingHome() {
  return (
    <div className="min-h-screen bg-background text-text-primary selection:bg-accent/20">
      <header className="sticky top-0 z-40 border-b border-surface-3 bg-surface-1/80 backdrop-blur-md shadow-sm">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex items-center justify-between gap-3">
            <Link href="/" className="flex shrink-0 items-center gap-2">
              <img src="/hawk-logo.png" alt="HAWK Security" className="h-10 w-auto sm:h-12 opacity-95" width={168} height={56} />
            </Link>
            <div className="flex items-center gap-2 sm:gap-4 md:hidden">
              <NavScanButton className="rounded-md px-4 py-2 text-sm font-medium" />
              <Link href="/portal/login" className="whitespace-nowrap text-sm font-medium text-text-secondary hover:text-accent">
                Log In
              </Link>
            </div>
          </div>
          <nav className="hidden md:flex flex-wrap items-center justify-center gap-x-6 text-sm font-medium text-text-secondary sm:justify-end">
            <a href="#how-it-works" className="hover:text-accent transition-colors">
              How It Works
            </a>
            <a href="#pricing" className="hover:text-accent transition-colors">
              Pricing
            </a>
            <a href="#hawk-certified" className="hover:text-accent transition-colors">
              HAWK Certified
            </a>
          </nav>
          <div className="hidden md:flex items-center gap-4">
            <Link href="/portal/login" className="whitespace-nowrap text-sm font-medium text-text-secondary hover:text-accent transition-colors">
              Log In
            </Link>
            <NavScanButton className="rounded-md px-5 py-2.5 text-sm font-medium" />
          </div>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section id="scan" className="scroll-mt-28 bg-surface-1 border-b border-surface-3 px-4 py-20 sm:px-6 sm:py-32">
          <div className="mx-auto max-w-4xl text-center">
            <h1 className="text-balance text-4xl font-extrabold leading-tight tracking-tight text-text-primary sm:text-5xl md:text-6xl">
              Your business has security vulnerabilities right now. Here is what attackers can see.
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-pretty text-lg leading-relaxed text-text-secondary sm:text-xl">
              HAWK monitors and tests Canadian small businesses daily. Follow our recommendations and if you still get breached — we cover the response costs. In writing. No other company will say that.
            </p>
            <div className="mx-auto mt-12 max-w-2xl shadow-xl rounded-xl bg-surface-1 border border-surface-3 overflow-hidden">
              <HomeScanner />
            </div>
            <p className="mx-auto mt-8 max-w-lg text-sm leading-relaxed text-text-dim">
              No account required · Results in seconds · Used by dental clinics, law firms & accountants across Canada
            </p>
          </div>
        </section>

        {/* Guarantee */}
        <section className="bg-background px-4 py-20 sm:px-6 sm:py-24">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight text-text-primary sm:text-4xl">
              We stand behind our work — financially.
            </h2>
            <div className="mt-8 space-y-4 text-left text-lg leading-relaxed text-text-secondary sm:text-center">
              <p>Most cybersecurity companies tell you what is wrong and walk away.</p>
              <p>We do not.</p>
              <p className="font-medium text-text-primary">
                If you follow our recommendations and something still happens — we cover your incident response costs. In writing. At signup.
              </p>
              <p>No other cybersecurity company serving Canadian small businesses will say that.</p>
            </div>
            <Link href="/guarantee-terms" className="mt-10 inline-flex items-center gap-2 text-base font-semibold text-accent hover:text-accent/80 transition-colors">
              See full guarantee terms <span aria-hidden="true">&rarr;</span>
            </Link>
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="scroll-mt-24 border-y border-surface-3 bg-surface-1 px-4 py-20 sm:px-6 sm:py-24">
          <h2 className="text-center text-3xl font-extrabold text-text-primary sm:text-4xl">How It Works</h2>
          <div className="mx-auto mt-16 grid max-w-6xl gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                step: "1",
                title: "We Scan",
                body: "We find every vulnerability on your domain in plain English.",
              },
              {
                step: "2",
                title: "We Monitor",
                body: "We watch your domain every day and alert you the moment something changes.",
              },
              {
                step: "3",
                title: "You Fix",
                body: "We show you exactly how to fix each issue with step-by-step guides. We help if you need us.",
              },
              {
                step: "4",
                title: "You Are Certified",
                body: "After 90 days of verified security you become HAWK Certified — proof your clients can see.",
              },
            ].map((s) => (
              <div key={s.step} className="rounded-2xl border border-surface-3 bg-background p-8 shadow-sm transition-shadow hover:shadow-md">
                <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-lg bg-accent/10 text-lg font-bold text-accent">
                  {s.step}
                </div>
                <h3 className="text-xl font-bold text-text-primary">{s.title}</h3>
                <p className="mt-3 text-base leading-relaxed text-text-secondary">{s.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* HAWK Certified */}
        <section id="hawk-certified" className="scroll-mt-24 bg-background px-4 py-20 sm:px-6 sm:py-24 border-b border-surface-3">
          <div className="mx-auto grid max-w-6xl gap-12 lg:grid-cols-2 lg:items-center lg:gap-20">
            <div>
              <h2 className="text-3xl font-extrabold text-text-primary sm:text-4xl">HAWK Certified</h2>
              <p className="mt-4 text-xl font-medium text-accent">
                Proof you take your clients&apos; data seriously.
              </p>
              <div className="mt-6 space-y-5 text-base leading-relaxed text-text-secondary">
                <p>
                  After 90 days of active monitoring with all critical issues resolved — your business becomes HAWK Certified.
                </p>
                <p>
                  You get a certificate, an embeddable badge for your website, and a public verification page your clients can check.
                </p>
                <p>
                  Dental clinics put it in their waiting room. Law firms put it in their client intake forms. Accountants put it in their proposals.
                </p>
                <p className="font-medium text-text-primary text-lg">It tells your clients: we checked. We are protected.</p>
              </div>
            </div>
            <div className="flex justify-center lg:justify-end">
              <div className="w-full max-w-md rounded-2xl border border-surface-3 bg-surface-1 p-10 shadow-xl relative overflow-hidden">
                <div className="absolute top-0 left-0 w-full h-2 bg-accent" />
                <div className="flex items-start gap-5">
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-2xl text-emerald-400">
                    ✓
                  </div>
                  <div>
                    <img src="/hawk-logo.png" alt="" className="h-7 w-auto opacity-95" />
                    <p className="mt-4 text-2xl font-bold text-text-primary">HAWK Certified</p>
                    <p className="text-base text-text-secondary mt-1">Verified Security Posture</p>
                  </div>
                </div>
                <div className="mt-8 rounded-lg border border-surface-3 bg-surface-2 px-4 py-3 font-mono text-sm text-text-dim text-center">
                  securedbyhawk.com/verify/example-clinic
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Who */}
        <section className="bg-surface-1 px-4 py-20 sm:px-6 sm:py-24 border-b border-surface-3">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="text-3xl font-extrabold text-text-primary sm:text-4xl">Who It Is For</h2>
            <p className="mt-4 text-lg text-text-secondary">Designed specifically for regulated Canadian practices.</p>
          </div>
          <div className="mx-auto mt-16 grid max-w-6xl gap-8 md:grid-cols-3">
            {[
              {
                title: "Dental Clinics",
                body: "Patient records are a top target for attackers. PIPEDA requires you to protect them. We make sure you do.",
              },
              {
                title: "Law Firms",
                body: "Client confidentiality is everything. One breach destroys trust built over decades. We protect what you have built.",
              },
              {
                title: "Accounting Practices",
                body: "Financial data is the most valuable target in any breach. Your clients trust you with their livelihood. We help you keep that trust.",
              },
            ].map((c) => (
              <div key={c.title} className="rounded-2xl border border-surface-3 bg-background p-8 shadow-sm">
                <h3 className="text-xl font-bold text-accent">
                  {c.title}
                </h3>
                <p className="mt-4 text-base leading-relaxed text-text-secondary">{c.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="scroll-mt-24 px-4 py-20 sm:px-6 sm:py-24 bg-background">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="text-3xl font-extrabold text-text-primary sm:text-4xl">Pricing</h2>
            <p className="mt-4 text-lg text-text-secondary">Enterprise-grade security, priced for small businesses.</p>
          </div>
          <div className="mx-auto mt-16 grid max-w-6xl gap-8 lg:grid-cols-3 items-center">
            <div className="rounded-2xl border border-surface-3 bg-surface-1 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-text-primary">HAWK Starter</h3>
              <p className="mt-4 text-4xl font-extrabold text-text-primary">
                $199<span className="text-lg font-normal text-text-secondary">/mo</span>
              </p>
              <p className="mt-6 text-base leading-relaxed text-text-secondary min-h-[100px]">
                Monthly scan and findings report. Plain English fix guides. Email alerts.
              </p>
              <div className="mt-4 pt-6 border-t border-surface-3">
                <p className="text-sm font-medium text-text-primary mb-6">Best for businesses that want to know their risk.</p>
                <StarterCheckoutButton />
              </div>
            </div>
            
            <div className="relative rounded-2xl border-2 border-accent bg-surface-1 p-10 shadow-2xl transform lg:-translate-y-4">
              <span className="absolute -top-4 left-1/2 -translate-x-1/2 rounded-full bg-accent px-4 py-1 text-xs font-bold uppercase tracking-wide text-white">
                Most Popular
              </span>
              <h3 className="text-xl font-bold text-accent">HAWK Shield</h3>
              <p className="mt-4 text-4xl font-extrabold text-text-primary">
                $997<span className="text-lg font-normal text-text-secondary">/mo</span>
              </p>
              <p className="mt-6 text-base leading-relaxed text-text-secondary min-h-[100px]">
                Daily monitoring. Weekly attacker simulation. Real-time alerts. HAWK Certified. Financially backed guarantee.
              </p>
              <div className="mt-4 pt-6 border-t border-surface-3">
                <p className="text-sm font-medium text-text-primary mb-6">Best for businesses that want to be protected.</p>
                <ShieldCheckoutButton />
              </div>
            </div>
            
            <div className="rounded-2xl border border-surface-3 bg-surface-1 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-text-primary">HAWK Enterprise</h3>
              <p className="mt-4 text-4xl font-extrabold text-text-primary">
                $2,500<span className="text-lg font-normal text-text-secondary">/mo</span>
              </p>
              <p className="mt-6 text-base leading-relaxed text-text-secondary min-h-[100px]">
                Everything in Shield plus dedicated advisor, up to 5 domains, enhanced guarantee coverage, PIPEDA compliance reporting.
              </p>
              <div className="mt-4 pt-6 border-t border-surface-3">
                <p className="text-sm font-medium text-text-primary mb-6">Best for multi-location practices.</p>
                <EnterpriseBookingLink href={ENTERPRISE_BOOKING} />
              </div>
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="bg-surface-1 border-t border-surface-3 px-4 py-20 sm:px-6 sm:py-32">
          <div className="mx-auto max-w-4xl rounded-3xl bg-accent px-6 py-16 text-center sm:px-12 shadow-2xl">
            <h2 className="text-3xl font-bold text-white sm:text-4xl text-balance">
              Find out what attackers can see about your business right now.
            </h2>
            <p className="mt-6 text-lg text-accent-light text-balance">
              It takes 60 seconds. No account required.
            </p>
            <a
              href="#scan"
              className="mt-10 inline-block rounded-xl bg-surface-1 px-10 py-4 text-base font-bold text-accent shadow-md hover:bg-surface-2 transition-colors"
            >
              Scan My Domain Free
            </a>
          </div>
        </section>
      </main>

      <footer className="border-t border-surface-3 bg-background px-4 py-12 sm:px-6">
        <div className="mx-auto max-w-6xl text-center text-sm text-text-secondary">
          <div className="flex justify-center mb-6">
             <img src="/hawk-logo.png" alt="" className="h-8 w-auto opacity-50 hover:opacity-90 transition-opacity" />
          </div>
          <p className="font-medium text-text-dim">HAWK Security &copy; AKB Studios &mdash; Calgary, AB</p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 font-medium">
            <a href="#how-it-works" className="hover:text-accent transition-colors">
              How It Works
            </a>
            <span className="text-surface-3" aria-hidden>|</span>
            <a href="#pricing" className="hover:text-accent transition-colors">
              Pricing
            </a>
            <span className="text-surface-3" aria-hidden>|</span>
            <a href="#hawk-certified" className="hover:text-accent transition-colors">
              HAWK Certified
            </a>
            <span className="text-surface-3" aria-hidden>|</span>
            <Link href="/guarantee-terms" className="hover:text-accent transition-colors">
              Guarantee Terms
            </Link>
            <span className="text-surface-3" aria-hidden>|</span>
            <Link href="/privacy" className="hover:text-accent transition-colors">
              Privacy Policy
            </Link>
          </div>
          <div className="mt-8 flex justify-center gap-6 text-sm font-medium">
            <Link href="/portal/login" className="hover:text-accent transition-colors">
              Client Login
            </Link>
            <a href="https://securedbyhawk.com" className="hover:text-accent transition-colors">
              securedbyhawk.com
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
