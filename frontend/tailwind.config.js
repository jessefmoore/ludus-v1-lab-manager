/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "rgb(var(--color-bg-base) / <alpha-value>)",
          surface: "rgb(var(--color-bg-surface) / <alpha-value>)",
          elevated: "rgb(var(--color-bg-elevated) / <alpha-value>)",
        },
        border: {
          DEFAULT: "rgb(var(--color-border) / <alpha-value>)",
          subtle: "rgb(var(--color-border-subtle) / <alpha-value>)",
        },
        text: {
          primary: "rgb(var(--color-text-primary) / <alpha-value>)",
          secondary: "rgb(var(--color-text-secondary) / <alpha-value>)",
          muted: "rgb(var(--color-text-muted) / <alpha-value>)",
        },
        accent: {
          success: "rgb(var(--color-accent) / <alpha-value>)",
          "success-hover": "rgb(var(--color-accent-hover) / <alpha-value>)",
          "success-active": "rgb(var(--color-accent-active) / <alpha-value>)",
          warning: "rgb(var(--color-warning) / <alpha-value>)",
          danger: "rgb(var(--color-danger) / <alpha-value>)",
          info: "rgb(var(--color-info) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      backgroundImage: {
        "gradient-border":
          "linear-gradient(135deg, rgb(var(--color-accent) / 0.4), rgb(var(--color-info) / 0.2), rgb(var(--color-border) / 0.5))",
        "gradient-border-hover":
          "linear-gradient(135deg, rgb(var(--color-accent) / 0.6), rgb(var(--color-info) / 0.35), rgb(var(--color-border) / 0.5))",
        "gradient-glow":
          "radial-gradient(ellipse at 50% 0%, rgb(var(--color-accent) / 0.08) 0%, transparent 60%)",
        "gradient-surface":
          "linear-gradient(180deg, rgb(var(--color-accent) / 0.03) 0%, transparent 40%)",
        "gradient-surface-deep":
          "linear-gradient(180deg, rgb(var(--color-accent) / 0.05) 0%, rgb(var(--color-info) / 0.02) 50%, transparent 100%)",
      },
      boxShadow: {
        glow: "0 0 20px rgb(var(--color-accent) / 0.1)",
        "glow-sm": "0 0 10px rgb(var(--color-accent) / 0.08)",
        "glow-lg": "0 0 40px rgb(var(--color-accent) / 0.15)",
        "inner-glow":
          "inset 0 1px 0 rgb(var(--color-accent) / 0.06), 0 0 20px rgb(var(--color-accent) / 0.08)",
        "card-hover":
          "0 4px 24px rgba(0,0,0,0.3), 0 0 20px rgb(var(--color-accent) / 0.06)",
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
        "page-enter": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          from: { backgroundPosition: "200% 0" },
          to: { backgroundPosition: "-200% 0" },
        },
        "timeline-pulse": {
          "0%, 100%": {
            boxShadow: "0 0 0 0 rgb(var(--color-accent) / 0.4)",
          },
          "50%": { boxShadow: "0 0 0 6px rgb(var(--color-accent) / 0)" },
        },
        "glow-pulse": {
          "0%, 100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
      },
      animation: {
        "slide-in": "slide-in 200ms ease-out",
        "fade-in": "fade-in 150ms ease-out",
        "scale-in": "scale-in 150ms ease-out",
        "slide-up": "slide-up 200ms ease-out",
        "page-enter": "page-enter 200ms ease-out",
        shimmer: "shimmer 3s ease-in-out infinite",
        "timeline-pulse": "timeline-pulse 2s ease-in-out infinite",
        "glow-pulse": "glow-pulse 4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
