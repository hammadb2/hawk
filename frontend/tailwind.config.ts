import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#F8FAFC",
        surface: {
          1: "#FFFFFF",
          2: "#F1F5F9",
          3: "#E2E8F0",
        },
        accent: {
          DEFAULT: "#0052CC",
          light: "#E5EDF9",
          dark: "#0B1E40",
        },
        red: "#EF4444",
        orange: "#F97316",
        green: "#10B981",
        blue: "#3B82F6",
        yellow: "#F59E0B",
        "text-primary": "#0F172A",
        "text-secondary": "#475569",
        "text-dim": "#64748B",
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
