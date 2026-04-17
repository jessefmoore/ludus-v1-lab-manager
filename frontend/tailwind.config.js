/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#0A0B0E",
          surface: "#14161C",
          elevated: "#1C1F28",
        },
        border: {
          DEFAULT: "#262A36",
          subtle: "#1E2130",
        },
        text: {
          primary: "#E8EAF0",
          secondary: "#8B92A5",
          muted: "#5A6175",
        },
        accent: {
          success: "#00D4AA",
          "success-hover": "#00BD97",
          "success-active": "#00A683",
          warning: "#FFA94D",
          danger: "#FF5E5E",
          info: "#6C8EFF",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      backgroundImage: {
        "gradient-border":
          "linear-gradient(135deg, rgba(0,212,170,0.4), rgba(108,142,255,0.2), rgba(38,42,54,0.5))",
        "gradient-border-hover":
          "linear-gradient(135deg, rgba(0,212,170,0.6), rgba(108,142,255,0.35), rgba(38,42,54,0.5))",
        "gradient-glow":
          "radial-gradient(ellipse at 50% 0%, rgba(0,212,170,0.08) 0%, transparent 60%)",
        "gradient-surface":
          "linear-gradient(180deg, rgba(0,212,170,0.03) 0%, transparent 40%)",
      },
      boxShadow: {
        glow: "0 0 20px rgba(0,212,170,0.1)",
        "glow-sm": "0 0 10px rgba(0,212,170,0.08)",
        "glow-lg": "0 0 40px rgba(0,212,170,0.15)",
      },
      keyframes: {
        "slide-in": {
          from: { opacity: "0", transform: "translateX(100%)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.95)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          from: { backgroundPosition: "200% 0" },
          to: { backgroundPosition: "-200% 0" },
        },
      },
      animation: {
        "slide-in": "slide-in 200ms ease-out",
        "fade-in": "fade-in 150ms ease-out",
        "scale-in": "scale-in 150ms ease-out",
        "slide-up": "slide-up 200ms ease-out",
        shimmer: "shimmer 3s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
