import type { Metadata } from "next";
import { DM_Sans, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/providers/auth-provider";
import { LiveRefreshBeacon } from "@/components/live-refresh-beacon";
import { LiveRealtimeBridge } from "@/components/live-realtime-bridge";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-cabinet",
  weight: ["400", "500", "600", "700", "800"],
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700", "800", "900"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://securedbyhawk.com"),
  title: {
    default: "HAWK. Cybersecurity for dental, legal, and CPA practices.",
    template: "%s | HAWK",
  },
  description:
    "Continuous external attack surface monitoring built for dental, legal, and CPA practices. HIPAA, FTC Safeguards, and ABA 2024 cyber ethics coverage, with a breach response guarantee in writing at signup.",
  keywords: [
    "cybersecurity for dental practices",
    "cybersecurity for law firms",
    "cybersecurity for CPA firms",
    "HIPAA external monitoring",
    "FTC Safeguards Rule compliance",
    "ABA formal opinion cybersecurity",
    "breach response guarantee",
    "attack surface management",
  ],
  authors: [{ name: "AKB Studios" }],
  creator: "AKB Studios",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "32x32" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://securedbyhawk.com",
    siteName: "HAWK",
    title: "HAWK. Cybersecurity for dental, legal, and CPA practices.",
    description:
      "Continuous external attack surface monitoring with a breach response guarantee up to $2.5M. Built for regulated US professional practices.",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "HAWK Cybersecurity" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "HAWK. Cybersecurity for dental, legal, and CPA practices.",
    description:
      "Continuous external monitoring with a breach response guarantee in writing. Built for HIPAA, FTC Safeguards, and ABA 2024 cyber ethics coverage.",
    images: ["/og-image.png"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true },
  },
  alternates: {
    canonical: "https://securedbyhawk.com",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${dmSans.variable} ${inter.variable} ${jetbrainsMono.variable} font-sans antialiased`}
    >
      <body>
        <AuthProvider>
          <LiveRefreshBeacon />
          <LiveRealtimeBridge />
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
