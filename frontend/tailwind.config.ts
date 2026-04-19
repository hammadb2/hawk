import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        /** Page canvas (light app shell) */
        background: "#f8fafc",
        surface: {
          1: "#ffffff",
          2: "#f1f5f9",
          3: "#e2e8f0",
        },
        accent: {
          DEFAULT: "#22C55E",
          light: "#BBF7D0",
        },
        red: "#F87171",
        orange: "#FB923C",
        green: "#34D399",
        blue: "#60A5FA",
        yellow: "#FBBF24",
        crmBg: "#0a0a0f",
        crmSurface: "#111118",
        crmBorder: "#1e1e2e",
        crmSurface2: "#16161f",
        "text-primary": "#0f172a",
        "text-secondary": "#475569",
        "text-dim": "#64748b",
      },
      fontFamily: {
        sans: ["var(--font-cabinet)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
      },
      fontWeight: {
        extrabold: "800",
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "fade-in-up": "fadeInUp 0.4s ease-out",
      },
      keyframes: {
        fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        fadeInUp: { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
      },
    },
  },
  plugins: [],
};

export default config;
