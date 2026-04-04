"use client";

import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { HomeScanner } from "./home-scanner";

const HAWK = "#00C48C";

function NavScanButton({ className }: { className?: string }) {
  return (
    <a
      href="#scan"
      className={className}
      style={{ backgroundColor: HAWK, color: "#07060C" }}
    >
      Scan My Domain Free
    </a>
  );
}

export function MarketingHome() {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-background text-text-primary">
      <header className="sticky top-0 z-40 border-b border-surface-3/80 bg-background/95 backdrop-blur-sm">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex items-center justify-between gap-3">
            <Link href="/" className="flex shrink-0 items-center gap-2">
              <img src="/hawk-logo.png" alt="HAWK Security" className="h-9 w-auto sm:h-10" width={120} height={40} />
            </Link>
            <div className="flex items-center gap-2 sm:gap-3">
              <NavScanButton className="rounded-lg px-3 py-2 text-xs font-semibold sm:px-4 sm:text-sm" />
              {user ? (
                <Link href="/dashboard" className="whitespace-nowrap text-xs text-text-dim hover:text-text-secondary sm:text-sm">
                  Dashboard
                </Link>
              ) : (
                <Link href="/login" className="whitespace-nowrap text-xs text-text-dim hover:text-text-secondary sm:text-sm">
                  Log In
                </Link>
              )}
            </div>
          </div>
          <nav className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-text-secondary sm:justify-end sm:gap-x-8 sm:text-sm">
            <a href="#how-it-works" className="hover:text-text-primary">
              How It Works
            </a>
            <a href="#pricing" className="hover:text-text-primary">
              Pricing
            </a>
            <a href="#hawk-certified" className="hover:text-text-primary">
              HAWK Certified
            </a>
          </nav>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section id="scan" className="scroll-mt-28 border-b border-surface-3 px-4 py-14 sm:px-6 sm:py-20">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="text-balance text-3xl font-extrabold leading-tight tracking-tight text-text-primary sm:text-4xl md:text-5xl">
              Your business has security vulnerabilities right now. Here is what attackers can see.
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-pretty text-base leading-relaxed text-text-secondary sm:text-lg">
              HAWK monitors and tests Canadian small businesses daily. Follow our recommendations and if you still get breached — we cover the response costs. In writing. No other company will say that.
            </p>
            <div className="mx-auto mt-10 max-w-xl">
              <HomeScanner />
            </div>
            <p className="mx-auto mt-8 max-w-lg text-xs leading-relaxed text-text-dim sm:text-sm">
              No account required · Results in seconds · Used by dental clinics, law firms & accountants across Canada
            </p>
          </div>
        </section>

        {/* Guarantee */}
        <section className="border-b border-surface-3 px-4 py-16 sm:px-6 sm:py-20">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="text-2xl font-extrabold tracking-tight text-text-primary sm:text-3xl md:text-4xl">
              We stand behind our work — financially.
            </h2>
            <div className="mt-8 space-y-4 text-left text-base leading-relaxed text-text-secondary sm:text-center">
              <p>Most cybersecurity companies tell you what is wrong and walk away.</p>
              <p>We do not.</p>
              <p>
                If you follow our recommendations and something still happens — we cover your incident response costs. In writing. At signup.
              </p>
              <p>No other cybersecurity company serving Canadian small businesses will say that.</p>
            </div>
            <Link href="/guarantee-terms" className="mt-8 inline-block text-sm font-medium hover:underline" style={{ color: HAWK }}>
              See full guarantee terms →
            </Link>
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="scroll-mt-24 border-b border-surface-3 px-4 py-16 sm:px-6 sm:py-20">
          <h2 className="text-center text-2xl font-extrabold text-text-primary sm:text-3xl">How It Works</h2>
          <div className="mx-auto mt-12 grid max-w-6xl gap-8 sm:grid-cols-2 lg:grid-cols-4">
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
              <div key={s.step} className="rounded-xl border border-surface-3 bg-surface-1 p-6 text-left">
                <div
                  className="mb-4 flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold text-[#07060C]"
                  style={{ backgroundColor: HAWK }}
                >
                  {s.step}
                </div>
                <h3 className="text-lg font-semibold text-text-primary">{s.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-text-secondary">{s.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* HAWK Certified */}
        <section id="hawk-certified" className="scroll-mt-24 border-b border-surface-3 px-4 py-16 sm:px-6 sm:py-20">
          <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-2 lg:items-center lg:gap-16">
            <div>
              <h2 className="text-2xl font-extrabold text-text-primary sm:text-3xl">HAWK Certified</h2>
              <p className="mt-2 text-lg font-medium" style={{ color: HAWK }}>
                Proof you take your clients&apos; data seriously.
              </p>
              <div className="mt-6 space-y-4 text-sm leading-relaxed text-text-secondary sm:text-base">
                <p>
                  After 90 days of active monitoring with all critical issues resolved — your business becomes HAWK Certified.
                </p>
                <p>
                  You get a certificate, an embeddable badge for your website, and a public verification page your clients can check.
                </p>
                <p>
                  Dental clinics put it in their waiting room. Law firms put it in their client intake forms. Accountants put it in their proposals.
                </p>
                <p className="text-text-primary">It tells your clients: we checked. We are protected.</p>
              </div>
            </div>
            <div className="flex justify-center lg:justify-end">
              <div className="w-full max-w-sm rounded-2xl border border-surface-3 bg-surface-1 p-8 shadow-lg">
                <div className="flex items-start gap-4">
                  <div
                    className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-xl text-[#07060C]"
                    style={{ backgroundColor: HAWK }}
                  >
                    ✓
                  </div>
                  <div>
                    <img src="/hawk-logo.png" alt="" className="h-6 w-auto opacity-90" />
                    <p className="mt-3 text-xl font-bold text-text-primary">HAWK Certified</p>
                    <p className="text-sm text-text-secondary">Verified Security Posture</p>
                  </div>
                </div>
                <div className="mt-6 rounded-lg border border-surface-3 bg-background px-3 py-2 font-mono text-[10px] text-text-dim sm:text-xs">
                  securedbyhawk.com/verify/example-clinic
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Who */}
        <section className="border-b border-surface-3 px-4 py-16 sm:px-6 sm:py-20">
          <h2 className="text-center text-2xl font-extrabold text-text-primary sm:text-3xl">Who It Is For</h2>
          <div className="mx-auto mt-12 grid max-w-6xl gap-6 md:grid-cols-3">
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
              <div key={c.title} className="rounded-xl border border-surface-3 bg-surface-1 p-6">
                <h3 className="text-lg font-semibold" style={{ color: HAWK }}>
                  {c.title}
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-text-secondary">{c.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Pricing */}
        <section id="pricing" className="scroll-mt-24 border-b border-surface-3 px-4 py-16 sm:px-6 sm:py-20">
          <h2 className="text-center text-2xl font-extrabold text-text-primary sm:text-3xl">Pricing</h2>
          <div className="mx-auto mt-12 grid max-w-6xl gap-6 lg:grid-cols-3">
            <div className="rounded-xl border border-surface-3 bg-surface-1 p-6">
              <h3 className="text-lg font-bold text-text-primary">HAWK Starter</h3>
              <p className="mt-1 text-2xl font-extrabold" style={{ color: HAWK }}>
                $199<span className="text-base font-normal text-text-secondary">/month</span>
              </p>
              <p className="mt-4 text-sm leading-relaxed text-text-secondary">
                Monthly scan and findings report. Plain English fix guides. Email alerts.
              </p>
              <p className="mt-2 text-xs text-text-dim">Best for businesses that want to know their risk.</p>
              <Link
                href="/login?register=1"
                className="mt-6 block w-full rounded-lg py-3 text-center text-sm font-semibold text-[#07060C]"
                style={{ backgroundColor: HAWK }}
              >
                Get Started
              </Link>
            </div>
            <div className="relative rounded-xl border-2 p-6" style={{ borderColor: HAWK, background: "#0D0B14" }}>
              <span
                className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-0.5 text-xs font-semibold text-[#07060C]"
                style={{ backgroundColor: HAWK }}
              >
                Most Popular
              </span>
              <h3 className="text-lg font-bold text-text-primary">HAWK Shield</h3>
              <p className="mt-1 text-2xl font-extrabold" style={{ color: HAWK }}>
                $997<span className="text-base font-normal text-text-secondary">/month</span>
              </p>
              <p className="mt-4 text-sm leading-relaxed text-text-secondary">
                Daily monitoring. Weekly attacker simulation. Real-time alerts. HAWK Certified after 90 days. Financially backed guarantee. Onboarding call.
              </p>
              <p className="mt-2 text-xs text-text-dim">Best for businesses that want to be protected.</p>
              <Link
                href="/login?register=1"
                className="mt-6 block w-full rounded-lg py-3 text-center text-sm font-semibold text-[#07060C]"
                style={{ backgroundColor: HAWK }}
              >
                Get Started — Most Popular
              </Link>
            </div>
            <div className="rounded-xl border border-surface-3 bg-surface-1 p-6">
              <h3 className="text-lg font-bold text-text-primary">HAWK Enterprise</h3>
              <p className="mt-1 text-2xl font-extrabold" style={{ color: HAWK }}>
                $2,500<span className="text-base font-normal text-text-secondary">/month</span>
              </p>
              <p className="mt-4 text-sm leading-relaxed text-text-secondary">
                Everything in Shield plus dedicated advisor, up to 5 domains, enhanced guarantee coverage, PIPEDA compliance reporting.
              </p>
              <p className="mt-2 text-xs text-text-dim">Best for multi-location practices.</p>
              <a
                href="mailto:hello@akbstudios.com?subject=HAWK%20Enterprise"
                className="mt-6 block w-full rounded-lg border border-surface-3 py-3 text-center text-sm font-semibold text-text-primary hover:bg-surface-2"
              >
                Contact Us
              </a>
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="px-4 py-16 sm:px-6 sm:py-20">
          <div className="mx-auto max-w-3xl rounded-2xl border border-surface-3 bg-surface-1 px-6 py-12 text-center sm:px-10">
            <p className="text-lg font-medium text-text-primary sm:text-xl">
              Find out what attackers can see about your business right now.
            </p>
            <p className="mt-3 text-text-secondary">It takes 60 seconds. No account required.</p>
            <a
              href="#scan"
              className="mt-8 inline-block rounded-lg px-8 py-3 text-sm font-semibold text-[#07060C] sm:text-base"
              style={{ backgroundColor: HAWK }}
            >
              Scan My Domain Free
            </a>
          </div>
        </section>
      </main>

      <footer className="border-t border-surface-3 px-4 py-10 sm:px-6">
        <div className="mx-auto max-w-6xl text-center text-sm text-text-dim">
          <p className="font-medium text-text-secondary">HAWK Security — AKB Studios — Calgary, AB</p>
          <div className="mt-4 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-xs sm:text-sm">
            <a href="#how-it-works" className="hover:text-text-secondary">
              How It Works
            </a>
            <span aria-hidden>|</span>
            <a href="#pricing" className="hover:text-text-secondary">
              Pricing
            </a>
            <span aria-hidden>|</span>
            <a href="#hawk-certified" className="hover:text-text-secondary">
              HAWK Certified
            </a>
            <span aria-hidden>|</span>
            <Link href="/guarantee-terms" className="hover:text-text-secondary">
              Guarantee Terms
            </Link>
            <span aria-hidden>|</span>
            <Link href="/privacy" className="hover:text-text-secondary">
              Privacy Policy
            </Link>
          </div>
          <div className="mt-4 flex flex-col items-center gap-2">
            <Link href="/login" className="text-xs hover:text-text-secondary">
              Log In
            </Link>
            <a href="https://securedbyhawk.com" className="text-xs hover:text-text-secondary">
              securedbyhawk.com
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
