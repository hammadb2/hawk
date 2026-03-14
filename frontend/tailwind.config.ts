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
        background: "#07060C",
        surface: {
          1: "#0D0B14",
          2: "#13111E",
          3: "#1A1727",
        },
        accent: {
          DEFAULT: "#7B5CF5",
          light: "#9B80FF",
        },
        red: "#F87171",
        orange: "#FB923C",
        green: "#34D399",
        blue: "#60A5FA",
        yellow: "#FBBF24",
        "text-primary": "#F2F0FA",
        "text-secondary": "#9B98B4",
        "text-dim": "#5C5876",
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
