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
        /** Unified marketing scheme: graphite ink canvas + signal amber accent. */
        background: "#07070A",
        surface: {
          1: "#0B0B10",
          2: "#111117",
          3: "#16161E",
        },
        accent: {
          DEFAULT: "#FFB800",
          light: "#FFECB0",
        },
        ink: {
          950: "#07070A",
          900: "#0B0B10",
          800: "#111117",
          700: "#16161E",
          600: "#1C1C26",
          500: "#232330",
          400: "#3A3A48",
          300: "#5D5D6E",
          200: "#8A8A97",
          100: "#BDBDC6",
          50: "#E8E8EE",
          0: "#F5F5F7",
        },
        signal: {
          DEFAULT: "#FFB800",
          50: "#FFF8E1",
          100: "#FFECB0",
          200: "#FFD966",
          300: "#FFCC3B",
          400: "#FFBE1E",
          500: "#FFB800",
          600: "#E6A400",
          700: "#B38100",
          800: "#7F5C00",
          glow: "rgba(255, 184, 0, 0.18)",
        },
        red: "#F87171",
        orange: "#FB923C",
        green: "#34D399",
        blue: "#60A5FA",
        yellow: "#FBBF24",
        /** CRM + legacy dashboard now share the ink palette. */
        crmBg: "#07070A",
        crmSurface: "#111117",
        crmBorder: "#232330",
        crmSurface2: "#16161E",
        "text-primary": "#F5F5F7",
        "text-secondary": "#BDBDC6",
        "text-dim": "#8A8A97",
      },
      fontFamily: {
        sans: ["var(--font-cabinet)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-cabinet)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
      },
      fontWeight: {
        extrabold: "800",
      },
      letterSpacing: {
        tightest: "-0.04em",
      },
      backgroundImage: {
        "signal-sheen":
          "linear-gradient(135deg, rgba(255,184,0,0) 0%, rgba(255,184,0,0.22) 45%, rgba(255,184,0,0) 95%)",
        "ink-vignette":
          "radial-gradient(circle at 50% 0%, rgba(255,184,0,0.12) 0%, rgba(255,184,0,0) 55%)",
      },
      boxShadow: {
        signal: "0 10px 40px -12px rgba(255, 184, 0, 0.45)",
        "signal-sm": "0 6px 20px -8px rgba(255, 184, 0, 0.35)",
        ink: "0 24px 60px -20px rgba(0, 0, 0, 0.55)",
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
        "fade-in-up": "fadeInUp 0.4s ease-out",
        shimmer: "shimmer 1.6s ease-in-out infinite",
        "signal-pulse": "signalPulse 2.6s ease-in-out infinite",
        "subtle-float": "subtleFloat 8s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        fadeInUp: { "0%": { opacity: "0", transform: "translateY(8px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        signalPulse: {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(255,184,0,0.45)" },
          "50%": { boxShadow: "0 0 0 14px rgba(255,184,0,0)" },
        },
        subtleFloat: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
