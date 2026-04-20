import type { Metadata } from "next";
import { DM_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/components/providers/auth-provider";
import { LiveRefreshBeacon } from "@/components/live-refresh-beacon";
import { LiveRealtimeBridge } from "@/components/live-realtime-bridge";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-cabinet",
  weight: ["400", "500", "600", "700", "800"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://hawk.akbstudios.com"),
  title: {
    default: "HAWK — Cybersecurity for Canadian Small Business",
    template: "%s | HAWK",
  },
  description:
    "HAWK scans your business for exposed attack surfaces, breached credentials, and lookalike domains. Built for Canadian SMBs. Start free.",
  keywords: [
    "cybersecurity canada",
    "attack surface management",
    "small business security",
    "domain monitoring canada",
    "breach detection",
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
    type: 'website',
    locale: 'en_CA',
    url: 'https://hawk.akbstudios.com',
    siteName: 'HAWK',
    title: 'HAWK — Cybersecurity for Canadian Small Business',
    description: 'HAWK scans your business for exposed attack surfaces, breached credentials, and lookalike domains. Built for Canadian SMBs.',
    images: [{ url: '/og-image.png', width: 1200, height: 630, alt: 'HAWK Cybersecurity' }]
  },
  twitter: {
    card: 'summary_large_image',
    title: 'HAWK — Cybersecurity for Canadian Small Business',
    description: 'Attack surface monitoring built for Canadian SMBs.',
    images: ['/og-image.png']
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true }
  },
  alternates: {
    canonical: 'https://hawk.akbstudios.com'
  }
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${dmSans.variable} ${jetbrainsMono.variable} font-sans antialiased`}>
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
