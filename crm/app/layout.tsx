import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HAWK CRM",
  description: "HAWK Cybersecurity Sales CRM",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body
        style={{ background: "#07060C", color: "#F2F0FA" }}
        className="min-h-screen antialiased"
      >
        {children}
      </body>
    </html>
  );
}
